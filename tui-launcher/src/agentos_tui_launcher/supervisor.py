"""前台子进程监督：启动主 TUI，处理信号与退出码分类，捕获 stdout handoff。

新设计（tui-switch-cc-design-new.md）下，SWITCH_CC 不再启动本地 cc-tui 子进程。
launcher 从主 TUI 的 stdout 读取 handoff JSON，通过 gateway WS + SSH 隧道完成切换。

关键约束（tui-switch-cc-launcher-interface.md 第 4 节）：
- 同一时刻最多运行一个前台子进程，并同步等待其完全退出和回收。
- **必须使用 PTY（伪终端）启动子进程**：TUI 启动时检测 process.stdout.isTTY，
  若 stdout 不是 TTY（如被重定向为 PIPE）会直接拒绝启动。
  PTY 同时满足两个需求：
  1. TUI 检测 isTTY 通过（PTY slave 对子进程表现为 TTY）
  2. launcher 从 PTY master 端读取输出（运行期间为绘制序列，最后一行是 handoff JSON）
- 子进程 stdin/stdout/stderr 均指向 PTY slave 端。
- launcher 不得向子进程 stdin 写入数据。
- 默认继承 launcher 的 cwd；不得创建新的终端窗口。
- launcher 收到 SIGINT、SIGTERM 或 Windows 等价终止事件时，将终止传递给当前子进程并等待回收。
- 返回实际退出码，不把未知非零退出码改写为 handoff。
- 只有退出码与本次协议快照精确匹配时才返回对应 HandoffAction。
- REAUTH_REQUIRED 只有在 reauth_enabled=True 且快照包含合法重新认证变量时才能分类为动作。
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Optional, Protocol

from . import errors
from .protocol import (
    ENV_CC_TUI_EXECUTABLE,
    ENV_REAUTH_EXIT_CODE,
    ENV_SUPERVISED,
    ENV_SUPERVISED_VALUE,
    ENV_SWITCH_CC_EXIT_CODE,
    HandoffAction,
    ProtocolSnapshot,
    REAUTH_EXIT_CODE,
    SWITCH_CC_EXIT_CODE,
)
from .resolver import ExecutableResolver, ResolvedExecutable


def _win_wintypes_fallback(name: str, base_type) -> None:
    """为缺失的 ctypes.wintypes 属性提供兜底定义（仅 Windows）。"""
    if not hasattr(wintypes, name):
        setattr(wintypes, name, base_type)


if sys.platform == "win32":
    from ctypes import wintypes

    # 兼容旧版 Python 缺失的类型
    _win_wintypes_fallback("HRESULT", wintypes.LONG)
    _win_wintypes_fallback("DWORD_PTR", ctypes.c_ulonglong)
    _win_wintypes_fallback("SIZE_T", ctypes.c_size_t)
    _win_wintypes_fallback(
        "LPSECURITY_ATTRIBUTES",
        ctypes.c_void_p,
    )


# ============================================================================
# 公共数据类型
# ============================================================================


@dataclass(frozen=True)
class ProcessSpec:
    """启动子进程所需参数。

    子进程的 stdin/stdout/stderr 均通过 PTY slave 端连接：
    TUI 检测 isTTY 通过，launcher 从 PTY master 端读取输出捕获 handoff JSON。
    """

    executable: ResolvedExecutable
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: str
    inherit_stdio: bool = True


@dataclass(frozen=True)
class ProcessResult:
    """ProcessRunner.run_foreground() 的返回值。

    `stdout` 为 PTY master 端捕获的输出内容（UTF-8 解码）。
    运行期间为 TUI 绘制序列；退出前最后一行是 handoff JSON。
    """

    exit_code: int
    stdout: str = ""


@dataclass(frozen=True)
class SupervisedProcessResult:
    """TuiSupervisor.run_primary() 的返回值。

    - `action` 为 None 表示普通退出；否则为 SWITCH_CC 或 REAUTH_REQUIRED。
    - `stdout` 为主 TUI stdout 的完整捕获，用于解析 handoff JSON。
    """

    exit_code: int
    action: Optional[HandoffAction]
    stdout: str = ""


# ============================================================================
# ProcessRunner 协议
# ============================================================================


class ProcessRunner(Protocol):
    """进程执行协议。"""

    def run_foreground(self, spec: ProcessSpec) -> ProcessResult:
        ...

    def forward_termination(self) -> None:
        ...


# ============================================================================
# 协议构造器
# ============================================================================


class SupervisionProtocol:
    """父子进程监督协议实现。

    每次启动主 TUI 时通过 `build_primary_env()` 形成不可变的协议快照，
    退出分类时使用该快照，不重新读取已变化的外部配置。

    新设计下不再包含 cc-tui 本地执行协议（build_cc_env / classify_cc_exit 等）；
    SWITCH_CC 的后续处理由 CLI 层通过 gateway WS + SSH 完成。
    """

    @staticmethod
    def build_primary_env(
        base_env: dict[str, str],
        reauth_enabled: bool = False,
    ) -> dict[str, str]:
        """构造主 TUI 的环境变量。

        - 永远注入 AGENTOS_TUI_SUPERVISED=1 与 AGENTOS_TUI_SWITCH_CC_EXIT_CODE=88。
        - reauth_enabled=True 时额外注入 AGENTOS_TUI_REAUTH_EXIT_CODE=89。
        - 注入 AGENTOS_CC_TUI_EXECUTABLE：TUI 端 checkHandoff() 预检要求此变量存在，
          否则 /switch 命令会拒绝执行。新设计下 cc-tui 不再本地执行，
          优先使用 base_env 中用户预设的值；缺失时用 /usr/bin/true 占位（通过预检即可）。
        - 不放 access token / refresh token / 密码 / UserContext / argv。
        """
        env = dict(base_env)
        env[ENV_SUPERVISED] = ENV_SUPERVISED_VALUE
        env[ENV_SWITCH_CC_EXIT_CODE] = str(SWITCH_CC_EXIT_CODE)
        if reauth_enabled:
            env[ENV_REAUTH_EXIT_CODE] = str(REAUTH_EXIT_CODE)
        # TUI 预检要求：checkHandoff() 检查此变量存在性。
        # 优先用 base_env 预设值；缺失时用 /usr/bin/true（POSIX）/ cmd /c（Windows）占位。
        if ENV_CC_TUI_EXECUTABLE not in env:
            env[ENV_CC_TUI_EXECUTABLE] = (
                "/usr/bin/true" if os.name != "nt" else "cmd"
            )
        return env

    @staticmethod
    def make_snapshot(
        reauth_enabled: bool,
    ) -> ProtocolSnapshot:
        """构造本次启动主 TUI 的协议快照。

        退出分类必须基于该快照，不重新读取外部配置。
        """
        return ProtocolSnapshot(
            supervised=True,
            switch_cc_exit_code=SWITCH_CC_EXIT_CODE,
            reauth_exit_code=REAUTH_EXIT_CODE if reauth_enabled else None,
        )

    @staticmethod
    def classify_exit(
        exit_code: int,
        snapshot: ProtocolSnapshot,
    ) -> Optional[HandoffAction]:
        """根据本次快照分类主 TUI 退出码。

        - 88 + 快照包含 SWITCH_CC 退出码 -> SWITCH_CC
        - 89 + 快照包含 reauth 退出码 -> REAUTH_REQUIRED
        - 其它：返回 None（普通退出码）
        """
        if exit_code == snapshot.switch_cc_exit_code:
            return HandoffAction.SWITCH_CC
        if (
            snapshot.reauth_exit_code is not None
            and exit_code == snapshot.reauth_exit_code
        ):
            return HandoffAction.REAUTH_REQUIRED
        return None


# ============================================================================
# ProcessRunner 实现
# ============================================================================


class _ConptyPopenProxy:
    """ConPTY 进程的轻量代理，提供与 subprocess.Popen 兼容的接口。

    SubprocessRunner.forward_termination() 依赖 _current_proc 的
    send_signal() 和 wait() 方法。本代理将 ConPTY 的原始 HANDLE
    包装为兼容接口，避免对 SubprocessRunner 做侵入式改动。
    """

    def __init__(self, handle: int, pid: int) -> None:
        self._handle = handle
        self.pid = pid

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._terminate_process = kernel32.TerminateProcess
        self._terminate_process.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._terminate_process.restype = wintypes.BOOL

        self._wait_for_single_object = kernel32.WaitForSingleObject
        self._wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._wait_for_single_object.restype = wintypes.DWORD

    def send_signal(self, sig: int) -> None:
        """发送信号；ConPTY 不支持 CTRL_BREAK_EVENT 转发，统一终止进程。"""
        self._terminate_process(wintypes.HANDLE(self._handle), 1)

    def wait(self, timeout: Optional[float] = None) -> int:
        """等待进程退出，返回退出码。"""
        infinite = 0xFFFFFFFF
        wait_object_0 = 0

        if timeout is None:
            ms = infinite
        else:
            ms = int(timeout * 1000)

        rc = self._wait_for_single_object(
            wintypes.HANDLE(self._handle), wintypes.DWORD(ms)
        )
        if rc == wait_object_0:
            # 获取退出码
            exit_code = wintypes.DWORD()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_exit_code_process = kernel32.GetExitCodeProcess
            get_exit_code_process.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
            ]
            get_exit_code_process.restype = wintypes.BOOL
            get_exit_code_process(
                wintypes.HANDLE(self._handle), ctypes.byref(exit_code)
            )
            return exit_code.value
        raise subprocess.TimeoutExpired(
            cmd="<ConPTY process>", timeout=timeout or 0
        )

    def poll(self) -> Optional[int]:
        """非阻塞检查进程是否退出。"""
        rc = self._wait_for_single_object(
            wintypes.HANDLE(self._handle), wintypes.DWORD(0)
        )
        if rc == 0:  # WAIT_OBJECT_0
            return self.wait()
        return None

    def kill(self) -> None:
        """强制终止进程。"""
        self._terminate_process(wintypes.HANDLE(self._handle), 9)


class SubprocessRunner:
    """基于 subprocess 的 ProcessRunner 实现。

    - 使用参数数组创建进程；禁止 shell=True。
    - **POSIX**：使用 PTY（pty.openpty）启动子进程，stdin/stdout/stderr 均指向
      PTY slave 端。TUI 检测 isTTY 通过，launcher 从 master 端读取输出。
      这是 tui-switch-cc-launcher-interface.md 第 4 节的硬性要求。
    - **Windows**：使用 ConPTY（Windows 10 1809+）启动子进程，同时满足
      isTTY 检测和 stdout 捕获。若 ConPTY 不可用则回退到控制台继承模式。
    - launcher 收到 SIGINT/SIGTERM 时转发给当前子进程并等待回收。
    - 返回实际退出码与捕获的 stdout。
    """

    def __init__(self) -> None:
        self._current_proc: Optional[subprocess.Popen] = None
        self._current_master_fd: Optional[int] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stdout_chunks: list[bytes] = []
        self._install_signal_handlers()

    def run_foreground(self, spec: ProcessSpec) -> ProcessResult:
        """启动子进程并阻塞等待其退出。

        POSIX：通过 PTY 启动，从 master 端捕获完整输出（含 handoff JSON）。
        Windows：子进程继承控制台句柄，无法捕获 stdout，返回 stdout=""。
        """
        # 启动前再次校验可执行文件，缩小检查与使用之间的竞态窗口。
        if not os.path.isfile(spec.executable.absolute_path):
            raise errors.ExecutableUnavailable(
                f"Executable missing: {spec.executable.absolute_path}"
            )

        # 重置状态
        self._stdout_chunks = []
        self._current_master_fd = None
        self._reader_thread = None

        if os.name == "nt":
            return self._run_foreground_windows(spec)
        return self._run_foreground_posix(spec)

    def _run_foreground_posix(self, spec: ProcessSpec) -> ProcessResult:
        """POSIX：使用 PTY 启动子进程，完整转发 IO。

        - 子进程 stdin/stdout/stderr 均指向 PTY slave 端（isTTY=true）
        - launcher 终端设为 raw 模式，通过 select() 双向转发：
          用户键盘 → PTY master → TUI stdin
          TUI stdout → PTY master → 用户终端（同时捕获用于 handoff JSON）
        - TUI 退出后恢复终端设置
        """
        import errno
        import fcntl
        import pty
        import select
        import struct
        import termios
        import tty

        try:
            master_fd, slave_fd = pty.openpty()
        except OSError as exc:
            raise errors.LauncherError(
                "Failed to create PTY for child process."
            ) from exc

        # 设置 PTY 窗口大小与当前终端一致
        try:
            stdin_fd = sys.stdin.fileno()
            stdout_fd = sys.stdout.fileno()
            winsize = fcntl.ioctl(stdin_fd, termios.TIOCGWINSZ, b"\x00" * 8)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        except (OSError, ValueError):
            stdin_fd = -1
            stdout_fd = -1

        try:
            proc = subprocess.Popen(
                [spec.executable.absolute_path, *spec.argv],
                env=spec.env,
                cwd=spec.cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
        except FileNotFoundError as exc:
            os.close(master_fd)
            os.close(slave_fd)
            raise errors.ExecutableUnavailable(
                "Executable missing at launch time."
            ) from exc
        except OSError as exc:
            os.close(master_fd)
            os.close(slave_fd)
            raise errors.LauncherError(
                "Failed to start child process."
            ) from exc

        os.close(slave_fd)
        self._current_proc = proc
        self._current_master_fd = master_fd

        # 保存终端原始设置，切换到 raw 模式（键盘逐字节透传，不缓冲不回显）
        old_tty_settings = None
        if stdin_fd >= 0:
            try:
                old_tty_settings = termios.tcgetattr(stdin_fd)
                tty.setraw(stdin_fd)
            except (termios.error, OSError):
                old_tty_settings = None

        self._stdout_chunks = []

        try:
            exit_code = self._relay_io(proc, master_fd, stdin_fd, stdout_fd)
        finally:
            # 恢复终端设置
            if old_tty_settings is not None and stdin_fd >= 0:
                try:
                    termios.tcsetattr(
                        stdin_fd, termios.TCSADRAIN, old_tty_settings
                    )
                except (termios.error, OSError):
                    pass
            # 关闭 master 端
            if self._current_master_fd is not None:
                try:
                    os.close(self._current_master_fd)
                except OSError:
                    pass
                self._current_master_fd = None
            self._current_proc = None

        raw_stdout = b"".join(self._stdout_chunks)
        captured_stdout = raw_stdout.decode("utf-8", errors="replace")
        return ProcessResult(exit_code=exit_code, stdout=captured_stdout)

    def _relay_io(
        self,
        proc: subprocess.Popen,
        master_fd: int,
        stdin_fd: int,
        stdout_fd: int,
    ) -> int:
        """通过 select() 双向转发 IO，直到子进程退出。

        用户键盘 → PTY master → TUI stdin
        TUI stdout → PTY master → 用户终端 + 捕获缓冲区
        """
        import errno
        import select

        while True:
            # 检查子进程是否已退出
            if proc.poll() is not None:
                # 子进程已退出，排空 PTY master 剩余数据
                self._drain_master(master_fd, stdout_fd)
                break

            # 构建 readable fd 列表
            rlist = [master_fd]
            if stdin_fd >= 0:
                rlist.append(stdin_fd)

            try:
                ready, _, _ = select.select(rlist, [], [], 0.1)
            except (OSError, select.error) as exc:
                # 信号中断 select 是正常现象
                if getattr(exc, "errno", None) == errno.EINTR:
                    continue
                break

            # 用户键盘输入 → PTY master → TUI
            if stdin_fd >= 0 and stdin_fd in ready:
                try:
                    data = os.read(stdin_fd, 1024)
                    if data:
                        os.write(master_fd, data)
                except OSError:
                    pass

            # TUI 输出 → PTY master → 用户终端 + 捕获
            if master_fd in ready:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        # master 端已关闭（TUI 退出）
                        break
                    self._stdout_chunks.append(data)
                    # 转发到用户终端
                    if stdout_fd >= 0:
                        try:
                            os.write(stdout_fd, data)
                        except OSError:
                            pass
                except OSError:
                    break

        # 等待子进程完全退出，获取退出码
        proc.wait()
        return proc.returncode if proc.returncode is not None else 0

    def _drain_master(self, master_fd: int, stdout_fd: int) -> None:
        """排空 PTY master 端剩余数据（子进程退出后的残留输出）。"""
        import select

        while True:
            try:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if not ready:
                    break
                data = os.read(master_fd, 4096)
                if not data:
                    break
                self._stdout_chunks.append(data)
                if stdout_fd >= 0:
                    try:
                        os.write(stdout_fd, data)
                    except OSError:
                        pass
            except OSError:
                break

    def _run_foreground_windows(self, spec: ProcessSpec) -> ProcessResult:
        """Windows：使用 ConPTY 启动子进程，提供 TTY 同时捕获 stdout。

        ConPTY（Windows 10 1809+）是 Windows 版的 PTY，同时满足：
        1. 子进程检测 isTTY 通过
        2. launcher 可捕获 stdout（含 handoff JSON）
        """
        import logging

        _logger = logging.getLogger(__name__)
        try:
            _logger.info("Attempting ConPTY mode for Windows child process.")
            return self._run_foreground_windows_conpty(spec)
        except Exception as exc:
            # ConPTY 不可用（< Windows 10 1809 或初始化失败），回退到继承模式。
            _logger.warning(
                f"ConPTY failed: {exc} - falling back to legacy console-inherit mode."
            )
            # 输出完整 traceback，便于诊断 ConPTY 路径的具体失败点。
            _logger.debug("ConPTY failure traceback:", exc_info=True)
            return self._run_foreground_windows_legacy(spec)

    def _run_foreground_windows_legacy(self, spec: ProcessSpec) -> ProcessResult:
        """Windows 继承模式：子进程继承控制台句柄，无法捕获 stdout。"""
        # 启用控制台 ANSI 处理，否则 TUI 输出的转义码会原样显示为乱码。
        self._enable_win_vt_processing()
        try:
            proc = subprocess.Popen(
                [spec.executable.absolute_path, *spec.argv],
                env=spec.env,
                cwd=spec.cwd,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
                creationflags=self._win_creation_flags(),
            )
        except FileNotFoundError as exc:
            raise errors.ExecutableUnavailable(
                "Executable missing at launch time."
            ) from exc
        except OSError as exc:
            raise errors.LauncherError(
                "Failed to start child process."
            ) from exc

        self._current_proc = proc
        try:
            exit_code = proc.wait()
        finally:
            self._current_proc = None
        return ProcessResult(exit_code=exit_code, stdout="")

    # ------------------------------------------------------------------
    # Windows ConPTY helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _conpty_create_pipes() -> tuple[int, int, int, int]:
        """创建 ConPTY 所需的输入/输出管道。

        Returns (input_read, input_write, output_read, output_write) 均为 Win32 HANDLE。
        """
        import _winapi

        input_read, input_write = _winapi.CreatePipe(None, 0)
        output_read, output_write = _winapi.CreatePipe(None, 0)
        return input_read, input_write, output_read, output_write

    @staticmethod
    def _conpty_get_console_size() -> tuple[int, int]:
        """获取当前控制台窗口尺寸（列, 行）。"""
        import _winapi

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class ConsoleScreenBufferInfo(ctypes.Structure):
            _fields_ = [
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD),
                ("srWindow", wintypes.SMALL_RECT),
                ("dwMaximumWindowSize", COORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_console_screen_buffer_info = kernel32.GetConsoleScreenBufferInfo
        get_console_screen_buffer_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ConsoleScreenBufferInfo),
        ]
        get_console_screen_buffer_info.restype = wintypes.BOOL

        conout = wintypes.HANDLE(_winapi.GetStdHandle(_winapi.STD_OUTPUT_HANDLE))
        csbi = ConsoleScreenBufferInfo()
        if not get_console_screen_buffer_info(conout, ctypes.byref(csbi)):
            # 获取失败时使用默认 80×24
            return 80, 24

        sr = csbi.srWindow
        cols = max(1, sr.Right - sr.Left + 1)
        rows = max(1, sr.Bottom - sr.Top + 1)
        return cols, rows

    def _run_foreground_windows_conpty(self, spec: ProcessSpec) -> ProcessResult:
        """Windows ConPTY 模式：创建伪控制台并双向转发 I/O。"""
        import _winapi
        import msvcrt
        import logging

        _logger = logging.getLogger(__name__)

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # --- 数据类型定义 ---

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", wintypes.LPBYTE),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class ProcessInformation(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        # STARTUPINFOEXW：扩展的 STARTUPINFO，携带 ConPTY 属性。
        extended_startupinfo_present = 0x00080000

        class STARTUPINFOEXW(ctypes.Structure):
            _fields_ = [
                ("StartupInfo", STARTUPINFOW),
                ("lp_attribute_list", ctypes.c_void_p),
            ]

        # --- 1. 管道 ---
        input_read, input_write, output_read, output_write = self._conpty_create_pipes()
        _logger.debug(
            f"ConPTY pipes created: in_r={input_read} in_w={input_write} "
            f"out_r={output_read} out_w={output_write}"
        )
        h_input_read = wintypes.HANDLE(input_read)
        h_output_write = wintypes.HANDLE(output_write)

        # --- 2. 控制台尺寸 ---
        cols, rows = self._conpty_get_console_size()

        # --- 3. CreatePseudoConsole ---
        create_pseudo_console = kernel32.CreatePseudoConsole
        create_pseudo_console.argtypes = [
            COORD,
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        create_pseudo_console.restype = wintypes.LONG

        close_pseudo_console = kernel32.ClosePseudoConsole
        close_pseudo_console.argtypes = [wintypes.HANDLE]
        close_pseudo_console.restype = None

        hpc = wintypes.HANDLE()
        hr = create_pseudo_console(
            COORD(cols, rows), h_input_read, h_output_write, 0, ctypes.byref(hpc)
        )
        _logger.info(f"CreatePseudoConsole HR=0x{hr & 0xFFFFFFFF:08x} cols={cols} rows={rows}")
        if hr != 0:
            self._conpty_close_pipes_silent(
                input_read, input_write, output_read, output_write
            )
            raise OSError(f"CreatePseudoConsole failed: 0x{hr & 0xFFFFFFFF:08x}")

        # --- 4. 属性列表（把 ConPTY 句柄注入子进程） ---
        proc_thread_attribute_pseudoconsole = 0x00020016

        initialize_proc_thread_attribute_list = kernel32.InitializeProcThreadAttributeList
        # 注意：最后一个参数是 PSIZE_T（SIZE_T*），不是 POINTER(LPSIZE)。
        # ctypes.wintypes.LPSIZE 本身就是指针类型（LP_SIZE），
        # 若写成 POINTER(LPSIZE) 会得到 LP_LP_SIZE，与 byref() 传入的
        # SIZE_T* 不匹配，导致 "expected LP_LP_SIZE instance instead of
        # pointer to c_ulonglong" 的 TypeError。
        initialize_proc_thread_attribute_list.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        initialize_proc_thread_attribute_list.restype = wintypes.BOOL

        update_proc_thread_attribute = kernel32.UpdateProcThreadAttribute
        update_proc_thread_attribute.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD_PTR,
            ctypes.c_void_p,
            wintypes.SIZE_T,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        update_proc_thread_attribute.restype = wintypes.BOOL

        delete_proc_thread_attribute_list = kernel32.DeleteProcThreadAttributeList
        delete_proc_thread_attribute_list.argtypes = [ctypes.c_void_p]
        delete_proc_thread_attribute_list.restype = None

        # 第一步：获取所需大小
        size_needed = wintypes.SIZE_T()
        initialize_proc_thread_attribute_list(None, 1, 0, ctypes.byref(size_needed))

        attr_buf = ctypes.create_string_buffer(size_needed.value)
        if not initialize_proc_thread_attribute_list(
            attr_buf, 1, 0, ctypes.byref(size_needed)
        ):
            close_pseudo_console(hpc)
            self._conpty_close_pipes_silent(
                input_read, input_write, output_read, output_write
            )
            raise OSError("InitializeProcThreadAttributeList failed")

        if not update_proc_thread_attribute(
            attr_buf,
            0,
            proc_thread_attribute_pseudoconsole,
            hpc,
            ctypes.sizeof(wintypes.HANDLE),
            None,
            None,
        ):
            delete_proc_thread_attribute_list(attr_buf)
            close_pseudo_console(hpc)
            self._conpty_close_pipes_silent(
                input_read, input_write, output_read, output_write
            )
            raise OSError("UpdateProcThreadAttribute failed")

        # --- 5. STARTUPINFOEX ---
        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.StartupInfo.dwFlags = extended_startupinfo_present
        si.lp_attribute_list = ctypes.cast(attr_buf, ctypes.c_void_p)

        # --- 6. CreateProcess ---
        create_process_w = kernel32.CreateProcessW
        create_process_w.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(STARTUPINFOEXW),
            ctypes.POINTER(ProcessInformation),
        ]
        create_process_w.restype = wintypes.BOOL

        cmdline = subprocess.list2cmdline(
            [spec.executable.absolute_path, *spec.argv]
        )

        # 子进程环境：必须显式传入 spec.env（含 AGENTOS_TUI_SUPERVISED、
        # AGENTOS_TUI_SWITCH_CC_EXIT_CODE 等协议变量）。lpEnvironment=None 只会
        # 继承 launcher 的 os.environ，协议变量会全部丢失，导致 TUI 不识别托管状态。
        create_unicode_environment = 0x00000400
        env_block = self._conpty_build_env_block(spec.env)
        env_buf = ctypes.create_string_buffer(env_block)
        lp_environment = ctypes.cast(env_buf, ctypes.c_void_p)

        creation_flags = self._win_creation_flags() | create_unicode_environment

        pi = ProcessInformation()
        if not create_process_w(
            None,               # lpApplicationName
            cmdline,            # lpCommandLine
            None,               # lpProcessAttributes
            None,               # lpThreadAttributes
            False,              # bInheritHandles
            creation_flags | 0x00080000,  # EXTENDED_STARTUPINFO_PRESENT
            lp_environment,     # lpEnvironment（Unicode 环境块）
            spec.cwd,           # lpCurrentDirectory
            ctypes.byref(si),   # lpStartupInfo
            ctypes.byref(pi),   # lpProcessInformation
        ):
            err = ctypes.get_last_error()
            delete_proc_thread_attribute_list(attr_buf)
            close_pseudo_console(hpc)
            self._conpty_close_pipes_silent(
                input_read, input_write, output_read, output_write
            )
            raise OSError(f"CreateProcessW failed: error {err}")

        # 不需要的属性列表和 ConPTY 输出写端可以关闭
        delete_proc_thread_attribute_list(attr_buf)
        _winapi.CloseHandle(output_write)
        _winapi.CloseHandle(pi.hThread)

        _logger.info(f"ConPTY process created: pid={pi.dwProcessId} handle={pi.hProcess} cmd={cmdline}")

        # 创建 subprocess.Popen 封装以便统一 forward_termination
        proc_handle_value = pi.hProcess
        proc_handle = wintypes.HANDLE(proc_handle_value)
        self._current_proc = _ConptyPopenProxy(proc_handle_value, pi.dwProcessId)

        # --- 7. I/O 转发 ---
        self._stdout_chunks = []

        input_write_fd = msvcrt.open_osfhandle(input_write, os.O_WRONLY)

        def _output_reader() -> None:
            """后台线程：从 ConPTY 输出管道读取，转发到控制台并捕获。

            不依赖外部 stop 事件；持续读到管道关闭（EOF）为止，
            确保进程退出前的最后输出（handoff JSON）也不会丢失。
            """
            try:
                read_fd = msvcrt.open_osfhandle(output_read, os.O_RDONLY)
                # 通过 Python 的 stdout 写入：控制台场景走 WriteConsoleW（UTF-8
                # 字节转 UTF-16 渲染，不受控制台活动代码页影响），重定向到文件时
                # 按 UTF-8 原始字节写入。不能直接 WriteFile 到控制台句柄——
                # 那会按活动代码页（中文系统常为 936/GBK）解释字节，
                # UTF-8 多字节字符（█、╗、中文等）会乱码。
                stdout_buffer = sys.stdout.buffer
                while True:
                    try:
                        data = os.read(read_fd, 4096)
                        if not data:
                            break
                        self._stdout_chunks.append(data)
                        stdout_buffer.write(data)
                        stdout_buffer.flush()
                    except OSError:
                        break
            except Exception as exc:
                _logger.debug("ConPTY output reader stopped: %s", exc)

        def _input_forwarder() -> None:
            """后台线程：从 stdin 读取并转发到 ConPTY 输入管道。

            Windows 控制台输入编码为活动代码页（如 936/GBK），
            而 ConPTY 中的 TUI 期望 UTF-8，需做编码转换。
            """
            # 获取控制台输入代码页，用于解码输入字节
            input_cp = kernel32.GetConsoleCP()
            try:
                stdin_fd = msvcrt.open_osfhandle(
                    _winapi.GetStdHandle(_winapi.STD_INPUT_HANDLE), os.O_RDONLY
                )
                while True:
                    try:
                        data = os.read(stdin_fd, 1024)
                        if not data:
                            break
                        if input_cp != 65001:
                            # 从代码页解码为 Unicode 再编码为 UTF-8
                            text = data.decode(f"cp{input_cp}", errors="replace")
                            os.write(input_write_fd, text.encode("utf-8"))
                        else:
                            os.write(input_write_fd, data)
                    except OSError:
                        break
            except Exception as exc:
                _logger.debug("ConPTY input forwarder stopped: %s", exc)

        output_thread = threading.Thread(target=_output_reader, daemon=True)
        input_thread = threading.Thread(target=_input_forwarder, daemon=True)

        # 启用控制台输出句柄的 ANSI 处理，否则 ConPTY 输出的转义码会原样显示乱码。
        self._enable_win_vt_processing()

        # 启动转发前把 launcher 控制台切到 raw 模式（逐键读取 VT 序列），
        # 结束后恢复。若 stdin 非控制台则静默跳过。
        raw_console = False
        try:
            self._set_win_console_raw(True)
            raw_console = True
        except Exception as exc:
            # raw 模式切换失败（非控制台等）时静默降级，仅记录不阻断。
            _logger.debug("Failed to enable raw console mode: %s", exc)

        output_thread.start()
        input_thread.start()

        try:
            # 主线程：等待子进程退出
            wait_for_single_object = kernel32.WaitForSingleObject
            wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            wait_for_single_object.restype = wintypes.DWORD
            wait_for_single_object(proc_handle, 0xFFFFFFFF)
        finally:
            if raw_console:
                self._set_win_console_raw(False)
            # 关闭输入写端 → ConPTY 感知 EOF → 刷新输出 → reader 收到 EOF
            os.close(input_write_fd)
            output_thread.join(timeout=3)
            input_thread.join(timeout=2)

        # --- 8. 获取退出码 ---
        exit_code_proc = wintypes.DWORD()
        get_exit_code_process = kernel32.GetExitCodeProcess
        get_exit_code_process.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        get_exit_code_process.restype = wintypes.BOOL
        get_exit_code_process(proc_handle, ctypes.byref(exit_code_proc))

        # --- 9. 清理 ---
        close_pseudo_console(hpc)
        _winapi.CloseHandle(input_read)
        # input_write 已通过 os.close(input_write_fd) 关闭
        # output_read 可能已被输出线程的 fd 关闭（线程读到 EOF 退出时，
        # fd 会被 GC close 底层句柄），这里要容忍无效句柄，避免再次触发
        # 回退到 legacy 模式。
        try:
            _winapi.CloseHandle(output_read)
        except OSError:
            pass
        _winapi.CloseHandle(proc_handle_value)
        self._current_proc = None

        raw_stdout = b"".join(self._stdout_chunks)
        captured_stdout = raw_stdout.decode("utf-8", errors="replace")
        _logger.info(
            f"ConPTY stdout captured: chunks={len(self._stdout_chunks)} bytes={len(raw_stdout)} "
            f"exit_code={exit_code_proc.value} first_200={captured_stdout[:200]!r}"
        )
        return ProcessResult(
            exit_code=exit_code_proc.value,
            stdout=captured_stdout,
        )

    @staticmethod
    def _conpty_build_env_block(env: dict[str, str]) -> bytes:
        """构建 CreateProcessW 的 Unicode 环境块（CREATE_UNICODE_ENVIRONMENT）。

        环境块格式：一串 "KEY=VALUE\\0" 条目后跟一个额外 "\\0" 结束符，
        整体以 UTF-16LE 编码。
        """
        entries = "".join(f"{k}={v}\0" for k, v in env.items())
        return (entries + "\0").encode("utf-16-le")

    @staticmethod
    def _set_win_console_raw(raw: bool) -> None:
        """切换 launcher 真实控制台的输入模式（ConPTY 转发期间使用）。

        raw=True：禁用 ENABLE_LINE_INPUT / ENABLE_ECHO_INPUT，启用
        ENABLE_VIRTUAL_TERMINAL_INPUT，使 os.read 能逐键读取 VT 序列
        （全屏 TUI 需要原始按键流；默认行缓冲模式下按键会被缓存到回车）。
        raw=False：恢复默认模式。

        若 stdin 不是真实控制台（如被重定向为管道），GetConsoleMode 失败，
        静默跳过。
        """
        try:
            import _winapi

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.GetStdHandle(_winapi.STD_INPUT_HANDLE)
            mode = wintypes.DWORD()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return
            # ENABLE_LINE_INPUT=0x0002, ENABLE_ECHO_INPUT=0x0004,
            # ENABLE_VIRTUAL_TERMINAL_INPUT=0x0200
            if raw:
                new_mode = (mode.value & ~0x0002 & ~0x0004) | 0x0200
            else:
                new_mode = mode.value | 0x0002 | 0x0004
            kernel32.SetConsoleMode(handle, new_mode)
        except (OSError, AttributeError):
            pass

    @staticmethod
    def _enable_win_vt_processing() -> None:
        """启用 Windows 控制台输出句柄的 ANSI/VT 转义序列处理。

        不设置此标志时，WriteFile / WriteConsole 会将 ANSI 转义码
        （如 ``[38;2;255;208;0m`` 设置颜色、``[H`` 移动光标等）
        当作普通文本原样输出，导致 TUI 渲染乱码。
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        """
        try:
            import _winapi

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.GetStdHandle(_winapi.STD_OUTPUT_HANDLE)
            mode = wintypes.DWORD()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return
            new_mode = mode.value | 0x0004
            kernel32.SetConsoleMode(handle, new_mode)
        except (OSError, AttributeError):
            pass

    @staticmethod
    def _conpty_close_pipes_silent(
        input_read: int,
        input_write: int,
        output_read: int,
        output_write: int,
    ) -> None:
        """安全关闭 ConPTY 管道句柄。"""
        import _winapi

        for h in (input_read, input_write, output_read, output_write):
            try:
                _winapi.CloseHandle(h)
            except OSError:
                pass

    def forward_termination(self) -> None:
        """把终止信号转发给当前子进程并等待回收。"""
        proc = self._current_proc
        if proc is None:
            return
        try:
            if os.name == "nt":
                # Windows：使用 CTRL_BREAK_EVENT 转发给子进程组。
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                proc.send_signal(signal.SIGTERM)
            # 等待最多 5 秒；超时则 SIGKILL。
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        except Exception:
            # 已经退出或无法发送：尽力 kill。
            proc.kill()
            proc.wait()
        finally:
            # 清理 PTY master 端（如有）
            if self._current_master_fd is not None:
                try:
                    os.close(self._current_master_fd)
                except OSError:
                    pass
                self._current_master_fd = None

    def _install_signal_handlers(self) -> None:
        """安装信号处理器，把 SIGINT/SIGTERM 转发给当前子进程。"""
        # 仅在主线程安装；子线程调用会抛 ValueError。
        try:
            if os.name != "nt":
                signal.signal(signal.SIGINT, self._handle_signal)
                signal.signal(signal.SIGTERM, self._handle_signal)
            else:
                # Windows：SIGINT 来自 Ctrl+C；SIGTERM 不能被拦截。
                signal.signal(signal.SIGINT, self._handle_signal)
        except (ValueError, OSError):
            # 非主线程或受限环境：忽略，不阻断启动。
            pass

    def _handle_signal(self, signum, frame) -> None:  # noqa: ANN001
        """信号处理回调：转发终止并等待回收。"""
        self.forward_termination()

    @staticmethod
    def _win_creation_flags() -> int:
        """Windows 子进程 creation flags。"""
        if os.name != "nt":
            return 0
        # CREATE_NEW_PROCESS_GROUP：允许 send_signal(CTRL_BREAK_EVENT)。
        # 不使用 CREATE_NEW_CONSOLE，避免弹出新的终端窗口。
        return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


# ============================================================================
# TuiSupervisor
# ============================================================================


class TuiSupervisor:
    """前台子进程监督器。

    新设计下只负责启动主 TUI 并捕获 stdout。SWITCH_CC 的后续处理
    （gateway WS 调用、SSH 隧道建立）由 CLI 层完成。
    """

    def __init__(
        self,
        runner: ProcessRunner,
        protocol: SupervisionProtocol,
        resolver: ExecutableResolver,
    ) -> None:
        self.runner = runner
        self._protocol = protocol
        self._resolver = resolver

    # ------------------------------------------------------------------
    # run_primary
    # ------------------------------------------------------------------

    def run_primary(
        self,
        primary: ResolvedExecutable,
        primary_argv: tuple[str, ...],
        reauth_enabled: bool,
        base_env: dict[str, str],
        cwd: str,
    ) -> SupervisedProcessResult:
        """启动主 TUI 并等待退出。

        返回 SupervisedProcessResult：
        - action=None 表示普通退出；exit_code 为原始退出码。
        - action=SWITCH_CC：子进程请求切换到三方 Agentos；
          stdout 包含 handoff JSON，由 CLI 层解析并执行 gateway + SSH 流程。
        - action=REAUTH_REQUIRED：子进程请求重新认证。
        """
        # 启动前再次校验主 TUI 可执行文件。
        if not self._resolver.revalidate(primary):
            raise errors.ExecutableUnavailable(
                "Primary executable not revalidatable before launch."
            )

        # 构造协议环境（不可变快照）。
        injected_env = self._protocol.build_primary_env(
            base_env=base_env,
            reauth_enabled=reauth_enabled,
        )
        snapshot = self._protocol.make_snapshot(
            reauth_enabled=reauth_enabled,
        )

        spec = ProcessSpec(
            executable=primary,
            argv=primary_argv,
            env=injected_env,
            cwd=cwd,
            inherit_stdio=True,
        )

        result = self.runner.run_foreground(spec)
        action = self._protocol.classify_exit(result.exit_code, snapshot)
        return SupervisedProcessResult(
            exit_code=result.exit_code,
            action=action,
            stdout=result.stdout,
        )

    # ------------------------------------------------------------------
    # run（兼容入口）
    # ------------------------------------------------------------------

    def run(
        self,
        primary: ResolvedExecutable,
        primary_argv: tuple[str, ...],
        base_env: dict[str, str],
        cwd: str,
    ) -> int:
        """兼容入口；等价于 reauth_enabled=False 的 run_primary()。

        - 89 在该入口中按未知普通退出码透传。
        - SWITCH_CC 在该入口中按退出码 88 透传（不执行 gateway + SSH 流程）；
          需要完整切换流程请使用 run_primary() 并在 CLI 层处理。
        """
        result = self.run_primary(
            primary=primary,
            primary_argv=primary_argv,
            reauth_enabled=False,
            base_env=base_env,
            cwd=cwd,
        )
        return result.exit_code
