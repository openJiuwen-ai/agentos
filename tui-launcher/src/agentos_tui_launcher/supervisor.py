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


class SubprocessRunner:
    """基于 subprocess 的 ProcessRunner 实现。

    - 使用参数数组创建进程；禁止 shell=True。
    - **POSIX**：使用 PTY（pty.openpty）启动子进程，stdin/stdout/stderr 均指向
      PTY slave 端。TUI 检测 isTTY 通过，launcher 从 master 端读取输出。
      这是 tui-switch-cc-launcher-interface.md 第 4 节的硬性要求。
    - **Windows**：Windows 没有 PTY，但 Windows 控制台本身对子进程表现为 TTY，
      因此子进程直接继承 launcher 的 stdin/stdout/stderr 句柄即可让 isTTY 通过。
      无法捕获 stdout（继承模式下没有管道），handoff JSON 通过 TUI 退出前的
      alternate screen 释放后输出到同一个控制台；launcher 在该模式下无法捕获。
      生产环境应在 POSIX 环境（Linux/macOS）运行 launcher 以获得完整 handoff 支持。
    - launcher 收到 SIGINT/SIGTERM 时转发给当前子进程并等待回收。
    - 返回实际退出码与捕获的 stdout（Windows 下 stdout 为空字符串）。
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
        """Windows：子进程继承控制台句柄。

        Windows 控制台本身对子进程表现为 TTY，Node.js 检测 isTTY 会通过。
        但继承模式下无法捕获 stdout，handoff JSON 会直接输出到控制台。
        返回 stdout=""，调用方需感知 Windows 下无法捕获 handoff。
        """
        try:
            proc = subprocess.Popen(
                [spec.executable.absolute_path, *spec.argv],
                env=spec.env,
                cwd=spec.cwd,
                # 继承父进程的控制台句柄；不使用 PIPE，否则 isTTY 检测失败。
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

        # Windows 继承模式下无法捕获 stdout
        return ProcessResult(exit_code=exit_code, stdout="")

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
