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
import queue
import re
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

# 匹配 DEC 私有模式集/复位序列（\x1b[?数字 h 或 l），
# 范围 1000-1099，这些是鼠标追踪相关的 VT 序列。
# TUI 写入这些序列到 ConPTY 以启用鼠标交互，但 launcher 将
# ConPTY 输出原样转发到真实控制台时，真实控制台也会处理这些
# 序列并启用 ENABLE_MOUSE_INPUT，导致鼠标点击被截获为 TUI 的
# 输入事件，而非用于 QuickEdit 文本选择。
# 我们在转发到真实控制台前过滤掉这些序列，保留真实控制台的
# QuickEdit 文本选中能力。
_MOUSE_TRACKING_RE = re.compile(b"\x1b\\[\\?10\\d{2}[hl]")


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
        self._saved_console_mode: Optional[int] = None
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

        def _acquire_pty_ctty() -> None:
            """子进程 preexec_fn：获取 PTY 为控制终端。

            start_new_session=True 调用 setsid() 创建新会话并脱离原控制终端，
            但不会自动绑定 PTY。需手动 TIOCSCTTY 才能使：
            1. TIOCSWINSZ(master_fd) 发送的 SIGWINCH 到达本进程
            2. 本进程的 ioctl(TIOCGWINSZ) 读取 PTY 尺寸（而非真实终端）
            """
            try:
                import fcntl as _f
                import termios as _t
                _f.ioctl(0, _t.TIOCSCTTY, 0)
            except (ImportError, OSError):
                pass

        try:
            proc = subprocess.Popen(
                [spec.executable.absolute_path, *spec.argv],
                env=spec.env,
                cwd=spec.cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                start_new_session=True,
                preexec_fn=_acquire_pty_ctty,
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

        注册 SIGWINCH 处理器：终端尺寸变化时同步 PTY 尺寸，让子进程
        （jiuwenswarm-tui / 三方 agent-tui）收到 SIGWINCH 后正确重绘。
        若不转发 resize，TUI 不知道终端尺寸变化，缩放后渲染仍按启动
        尺寸，对话框/输入框可能错位或消失。
        """
        import errno
        import fcntl
        import select
        import termios

        # 注册 SIGWINCH：终端大小变化时设置 flag，在循环中同步 PTY 尺寸。
        resize_flag = [False]
        old_sigwinch = signal.signal(
            signal.SIGWINCH,
            lambda signum, frame: resize_flag.__setitem__(0, True),
        )

        try:
            while True:
                # 检查子进程是否已退出
                if proc.poll() is not None:
                    # 子进程已退出，排空 PTY master 剩余数据
                    self._drain_master(master_fd, stdout_fd)
                    break

                # --- Resize 检测 ---
                if resize_flag[0]:
                    resize_flag[0] = False
                    try:
                        winsize = fcntl.ioctl(
                            stdin_fd, termios.TIOCGWINSZ, b"\x00" * 8
                        )
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    except (OSError, ValueError):
                        pass

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
        finally:
            # 恢复 SIGWINCH 处理器
            signal.signal(signal.SIGWINCH, old_sigwinch)

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

        管道缓冲区设为 0 时使用系统默认值（通常仅 4096 字节）。
        全屏 TUI 输出大量 VT 序列时，若 output pipe 填满，
        ConPTY 会阻塞在写管道 → TUI 阻塞在 I/O → 整个系统死锁。
        使用 64KB 缓冲区确保高吞吐场景下不背压。
        """
        import _winapi

        pipe_buffer_size = 65536  # 64KB
        input_read, input_write = _winapi.CreatePipe(None, pipe_buffer_size)
        output_read, output_write = _winapi.CreatePipe(None, pipe_buffer_size)
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

        # 输出队列：解耦"管道读取"与"控制台写入"。详见 _output_reader 注释。
        output_queue: "queue.Queue[Optional[bytes]]" = queue.Queue()

        def _output_reader() -> None:
            """后台线程：从 ConPTY 输出管道**快速**读取并放入 output_queue。

            本线程只负责尽快清空管道，**绝不**在此处做控制台写入或 flush。
            控制台写入由独立的 _console_writer 线程异步消费 output_queue 完成。

            关键背景（Windows 全屏卡死的根因）：
            Microsoft 官方文档
            (https://learn.microsoft.com/zh-cn/windows/console/creating-a-pseudoconsole-session)
            明确警告："若不充分排空输出管道，可能导致 ResizePseudoConsole
            及 ClosePseudoConsole 死锁"。ConPTY 输出管道缓冲区仅 4-64KB，
            而全屏 TUI（240x60 ≈ 14k cells）单次重绘可能产出数十 KB VT
            序列。若"读取→写入控制台→flush"在同一线程串行执行，当
            stdout_buffer.flush() 因 conhost 大缓冲区渲染或 GIL 竞争而
            变慢时，管道会被填满 → 子进程 write() 阻塞 → 子进程事件循环
            卡死，无法处理键盘输入 → 表现为 TUI 全屏下"界面卡死、无法输入
            文字或命令"，而小屏下输出量小、管道不会满，故一切正常。

            解耦后：
            - 本线程 os.read 后立即入队（仅受 GIL 短暂加锁影响），管道始终被
              快速清空，子进程 write() 永不阻塞 → 事件循环持续运转 →
              ResizePseudoConsole 也不会死锁。
            - _console_writer 以自己的节奏消费队列，慢一点也无害。
            """
            try:
                read_fd = msvcrt.open_osfhandle(output_read, os.O_RDONLY)
                while True:
                    try:
                        # 增大单次读取量到 16KB，减少 syscall 次数，配合
                        # 64KB 管道缓冲区可在 4 次 read 内清空一轮。
                        data = os.read(read_fd, 16384)
                        if not data:
                            break
                        self._stdout_chunks.append(data)
                        output_queue.put(data)
                    except OSError:
                        break
            except Exception as exc:
                _logger.debug("ConPTY output reader stopped: %s", exc)
            finally:
                # 哨兵：通知 _console_writer 管道已 EOF，可退出。
                output_queue.put(None)

        def _console_writer() -> None:
            """后台线程：从 output_queue 取出 ConPTY 输出并写入 launcher 真实 stdout。

            通过 Python 的 stdout 写入：控制台场景走 WriteConsoleW（UTF-8
            字节转 UTF-16 渲染，不受控制台活动代码页影响），重定向到文件时
            按 UTF-8 原始字节写入。不能直接 WriteFile 到控制台句柄——
            那会按活动代码页（中文系统常为 936/GBK）解释字节，
            UTF-8 多字节字符（█、╗、中文等）会乱码。

            以独立线程运行，即使此处的 write/flush 较慢，也不会反过来
            阻塞 _output_reader 对管道的排空，从而避免 ConPTY 死锁。
            """
            stdout_buffer = sys.stdout.buffer
            try:
                while True:
                    data = output_queue.get()
                    if data is None:
                        break
                    # 过滤掉鼠标追踪 VT 序列，防止真实控制台启用
                    # ENABLE_MOUSE_INPUT 导致 QuickEdit 文本选中失效。
                    # TUI 在 ConPTY 内仍可正常使用鼠标交互。
                    data = _MOUSE_TRACKING_RE.sub(b"", data)
                    if data:
                        try:
                            stdout_buffer.write(data)
                            stdout_buffer.flush()
                        except OSError:
                            break
            except Exception as exc:
                _logger.debug("ConPTY console writer stopped: %s", exc)

        def _input_forwarder() -> None:
            """后台线程：从 stdin 读取并转发到 ConPTY 输入管道。

            **关键**：
            1. 必须用 DuplicateHandle 复制 stdin 句柄再创建 fd。
               os.close(fd) 会 CloseHandle 底层句柄，若直接用
               GetStdHandle(STD_INPUT_HANDLE) 的原始句柄，close 后
               stdin 被永久销毁，后续 TUI isTTY 检测失败。
            2. 使用阻塞 os.read 读取输入（经实测验证可靠）。
               不要改成 msvcrt.kbhit() 轮询——kbhit() 在 raw 模式 +
               ENABLE_VIRTUAL_TERMINAL_INPUT 下可能永远返回 False，
               导致键盘输入完全无响应（终端卡死）。
               本线程为 daemon，子进程退出后 join 超时即可，
               进程退出时会被强制终止，阻塞读取不会阻塞进程退出。
            3. stdin_fd 必须在 finally 中关闭，否则 fd 泄漏。
            """
            # 获取控制台输入代码页，用于解码输入字节
            input_cp = kernel32.GetConsoleCP()
            stdin_fd = None
            try:
                # 复制 stdin 句柄，避免 os.close 销毁原始句柄
                from ctypes import wintypes as _wt
                kernel32.DuplicateHandle.argtypes = [
                    _wt.HANDLE, _wt.HANDLE,
                    _wt.HANDLE, ctypes.POINTER(_wt.HANDLE),
                    _wt.DWORD, _wt.BOOL, _wt.DWORD,
                ]
                kernel32.DuplicateHandle.restype = _wt.BOOL
                current_proc = kernel32.GetCurrentProcess()
                orig_stdin = _winapi.GetStdHandle(_winapi.STD_INPUT_HANDLE)
                dup_handle = _wt.HANDLE()
                if not kernel32.DuplicateHandle(
                    current_proc, _wt.HANDLE(orig_stdin),
                    current_proc, ctypes.byref(dup_handle),
                    0, False, 2,  # DUPLICATE_SAME_ACCESS
                ):
                    return
                stdin_fd = msvcrt.open_osfhandle(dup_handle.value, os.O_RDONLY)
                while True:
                    try:
                        data = os.read(stdin_fd, 1024)
                        if not data:
                            break
                        # 拦截 Ctrl+V (0x16)：从剪贴板读取并替换为剪贴板内容，
                        # 让 cmd/powershell 在 QuickEdit 禁用时仍可通过 Ctrl+V 粘贴。
                        # 0x16 在所有常见代码页（CP437/GBK/UTF-8）中均为单字节，
                        # 可在字节流阶段直接 split。
                        if b"\x16" in data:
                            parts = data.split(b"\x16")
                            # 非 Ctrl+V 片段仍需按控制台代码页转换
                            if input_cp != 65001:
                                parts = [
                                    p.decode(f"cp{input_cp}", errors="replace")
                                    .encode("utf-8")
                                    for p in parts
                                ]
                            clip = self._read_win_clipboard()
                            os.write(input_write_fd, clip.join(parts))
                        elif input_cp != 65001:
                            # 从代码页解码为 Unicode 再编码为 UTF-8
                            text = data.decode(f"cp{input_cp}", errors="replace")
                            os.write(input_write_fd, text.encode("utf-8"))
                        else:
                            os.write(input_write_fd, data)
                    except OSError:
                        break
            except Exception as exc:
                _logger.debug("ConPTY input forwarder stopped: %s", exc)
            finally:
                if stdin_fd is not None:
                    try:
                        os.close(stdin_fd)
                    except OSError:
                        pass

        output_thread = threading.Thread(target=_output_reader, daemon=True)
        writer_thread = threading.Thread(target=_console_writer, daemon=True)
        input_thread = threading.Thread(target=_input_forwarder, daemon=True)

        # 启用控制台输出句柄的 ANSI 处理，否则 ConPTY 输出的转义码会原样显示乱码。
        self._enable_win_vt_processing()

        # 启动转发前把 launcher 控制台切到 raw 模式（逐键读取 VT 序列），
        # 结束后恢复。若 stdin 非控制台则静默跳过。
        raw_console = False
        try:
            self._save_win_console_mode()
            self._set_win_console_raw(True)
            raw_console = True
        except Exception as exc:
            # raw 模式切换失败（非控制台等）时静默降级，仅记录不阻断。
            _logger.debug("Failed to enable raw console mode: %s", exc)

        output_thread.start()
        writer_thread.start()
        input_thread.start()

        # 绑定 ResizePseudoConsole 用于终端缩放时同步 ConPTY 尺寸。
        resize_pseudo_console = kernel32.ResizePseudoConsole
        resize_pseudo_console.argtypes = [wintypes.HANDLE, COORD]
        resize_pseudo_console.restype = ctypes.c_long  # HRESULT

        # 记录初始控制台尺寸，用于轮询检测 resize。
        last_size = self._conpty_get_console_size()

        try:
            # 主线程：轮询等待子进程退出，同时检测终端 resize。
            # 不能用 INFINITE 阻塞等待，否则无法响应窗口缩放。
            wait_for_single_object = kernel32.WaitForSingleObject
            wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            wait_for_single_object.restype = wintypes.DWORD
            wait_timeout = 100  # 100ms 轮询间隔
            while True:
                rc = wait_for_single_object(
                    wintypes.HANDLE(proc_handle_value),
                    wintypes.DWORD(wait_timeout),
                )
                if rc == 0:  # WAIT_OBJECT_0：子进程已退出
                    break
                # rc == 258 (WAIT_TIMEOUT)：继续轮询，检查 resize
                cur_size = self._conpty_get_console_size()
                if cur_size != last_size:
                    last_size = cur_size
                    cols, rows = cur_size
                    hr = resize_pseudo_console(
                        wintypes.HANDLE(hpc.value), COORD(cols, rows)
                    )
                    _logger.debug(
                        f"ResizePseudoConsole HR=0x{hr & 0xFFFFFFFF:08x} "
                        f"cols={cols} rows={rows}"
                    )
        finally:
            if raw_console:
                self._restore_win_console_mode()
            # 关闭输入写端 → ConPTY 感知 EOF
            os.close(input_write_fd)
            # 先关闭 ConPTY，释放其对 output pipe 的引用，
            # 使 _output_reader 收到 EOF 并退出。
            # 若在 join 之后再关闭，output_thread 会因等不到 EOF 而超时，
            # 导致最后的 handoff JSON 丢失。
            close_pseudo_console(hpc)
            output_thread.join(timeout=3)
            # output_thread 退出后会向 output_queue 投递 None 哨兵，
            # _console_writer 收到后即可收尾；join 必须在 output_thread 之后，
            # 否则 writer 会因等不到哨兵而 hang 至超时。
            writer_thread.join(timeout=3)
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

    def _save_win_console_mode(self) -> None:
        """保存当前控制台输入模式，用于后续精确恢复。"""
        try:
            import _winapi

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.GetStdHandle(_winapi.STD_INPUT_HANDLE)
            mode = wintypes.DWORD()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                self._saved_console_mode = mode.value
        except (OSError, AttributeError):
            self._saved_console_mode = None

    def _restore_win_console_mode(self) -> None:
        """精确恢复之前保存的控制台输入模式。

        使用保存的原始模式精确还原，避免 read-modify-write 模式
        在多次调用间丢失或引入额外标志位。
        """
        if self._saved_console_mode is None:
            # 没有保存过模式，回退到 _set_win_console_raw(False) 的默认恢复。
            self._set_win_console_raw(False)
            return
        try:
            import _winapi

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.GetStdHandle(_winapi.STD_INPUT_HANDLE)
            kernel32.SetConsoleMode(handle, self._saved_console_mode)
        except (OSError, AttributeError):
            pass

    @staticmethod
    def _set_win_console_raw(raw: bool) -> None:
        """切换 launcher 真实控制台的输入模式（ConPTY 转发期间使用）。

        raw=True：禁用 ENABLE_LINE_INPUT / ENABLE_ECHO_INPUT，启用
        ENABLE_VIRTUAL_TERMINAL_INPUT，使 os.read 能逐键读取 VT 序列
        （全屏 TUI 需要原始按键流；默认行缓冲模式下按键会被缓存到回车）。
        raw=False：恢复默认模式（移除 ENABLE_VIRTUAL_TERMINAL_INPUT）。

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
            # ENABLE_PROCESSED_INPUT=0x0001, ENABLE_LINE_INPUT=0x0002,
            # ENABLE_ECHO_INPUT=0x0004, ENABLE_WINDOW_INPUT=0x0008,
            # ENABLE_MOUSE_INPUT=0x0010, ENABLE_INSERT_MODE=0x0020,
            # ENABLE_QUICK_EDIT_MODE=0x0040, ENABLE_EXTENDED_FLAGS=0x0080,
            # ENABLE_VIRTUAL_TERMINAL_INPUT=0x0200
            if raw:
                # 清除 PROCESSED_INPUT 使 Ctrl+C 不被本地拦截为信号，
                # 而是作为 \x03 转发到 ConPTY 子进程。
                #
                # **保留 ENABLE_QUICK_EDIT_MODE**：让用户可以用鼠标选中
                # 控制台中的历史消息进行复制。QuickEdit 开启后，鼠标
                # 点击控制台客户区会进入"选择模式"，期间键盘输入会
                # 被截留，但用户可以通过 Enter 或单击退出选择模式，
                # 键盘输入即可恢复。
                new_mode = (
                    mode.value
                    & ~0x0001  # 清 PROCESSED_INPUT
                    & ~0x0002  # 清 LINE_INPUT
                    & ~0x0004  # 清 ECHO_INPUT
                    # 保留 QUICK_EDIT_MODE，允许鼠标选中复制历史消息
                ) | 0x0080 | 0x0200  # 置 EXTENDED_FLAGS | VIRTUAL_TERMINAL_INPUT
            else:
                new_mode = (mode.value | 0x0001 | 0x0002 | 0x0004) & ~0x0200
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
    def _read_win_clipboard() -> bytes:
        """从 Windows 剪贴板读取文本，转换为 UTF-8 字节。

        在 raw VT 输入模式下，传统 conhost（cmd.exe / powershell.exe）：
        - QuickEdit 被显式禁用（避免选择模式冻结输入），右键粘贴随之失效
        - Shift+Insert 不触发 conhost 自动粘贴
        - Ctrl+V 生成控制字符 ``\\x16`` 传到 ReadFile
        本函数配合 _input_forwarder 拦截 ``\\x16``，主动从剪贴板取出
        文本转发到子进程，恢复 cmd/powershell 下的粘贴能力。
        Windows Terminal 自身处理粘贴，不依赖此机制。

        Returns:
            剪贴板文本的 UTF-8 字节；剪贴板不可用或无文本时返回 ``b""``。
        """
        try:
            from ctypes import wintypes as _wt

            cf_unicode_text = 13
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            user32.OpenClipboard.argtypes = [_wt.HWND]
            user32.OpenClipboard.restype = _wt.BOOL
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = _wt.BOOL
            user32.IsClipboardFormatAvailable.argtypes = [_wt.UINT]
            user32.IsClipboardFormatAvailable.restype = _wt.BOOL
            user32.GetClipboardData.argtypes = [_wt.UINT]
            user32.GetClipboardData.restype = _wt.HANDLE
            kernel32.GlobalLock.argtypes = [_wt.HGLOBAL]
            kernel32.GlobalLock.restype = _wt.LPVOID
            kernel32.GlobalUnlock.argtypes = [_wt.HGLOBAL]
            kernel32.GlobalUnlock.restype = _wt.BOOL

            if not user32.OpenClipboard(None):
                return b""
            try:
                if not user32.IsClipboardFormatAvailable(cf_unicode_text):
                    return b""
                handle = user32.GetClipboardData(cf_unicode_text)
                if not handle:
                    return b""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return b""
                try:
                    text = ctypes.wstring_at(ptr)
                    return text.encode("utf-8")
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except (OSError, AttributeError, ValueError):
            return b""

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
