"""SSH 隧道客户端。

新设计（tui-switch-cc-design-new.md 第 10.3 节）下，launcher 从 gateway 获取
SSH 端点后，通过 SSH 隧道连接三方 Agentos：

1. 使用返回的 SSH IP 和 Port 连接
2. 若 3rdagent.switch 返回了 ssh_private_key，launcher 先临时写入文件，
   再以等价 `ssh -i <file>` 的方式（paramiko key_filename）使用该私钥认证
3. SSH 连接成功后，发送 content 并回车（通过 invoke_shell 交互式 shell 执行，
   等价于 `ssh -t user@host claude`，远端 sandbox 要求交互式 shell 通道）
4. 进入交互模式，用户与三方 Agentos 交互
5. 三方 Agentos 退出后返回退出码

本模块使用 `paramiko` 库实现 SSH 通信。paramiko 为可选依赖，
缺失时在运行时抛出 SshTunnelError。

交互模式实现：
- POSIX：使用 tty.setraw() 设置原始模式，转发 stdin <-> SSH channel
- Windows：使用 ctypes 设置控制台原始模式
- 两个线程分别转发 stdin -> channel 和 channel -> stdout
"""

from __future__ import annotations

import os
import queue
import sys
import threading
from typing import Optional, Protocol

from . import errors


class SshTunnelClient(Protocol):
    """SSH 隧道客户端协议。"""

    def connect_and_send(
        self,
        ssh_ip: str,
        ssh_port: int,
        content: str,
        username: Optional[str] = None,
        private_key_file: Optional[str] = None,
    ) -> int:
        ...


class ParamikoSshTunnelClient:
    """基于 paramiko 库的 SshTunnelClient 实现。

    - 连接到指定 SSH 端点
    - 若提供 private_key_file，以等价 `ssh -i <file>` 的方式（paramiko
      key_filename）使用该私钥认证；否则沿用默认凭据探测行为
    - 打开交互式 shell，发送 content 并回车（等价于 `ssh -t user@host <content>`）
    - 进入交互模式转发
    - 返回退出码
    """

    def __init__(self) -> None:
        """初始化 SSH 隧道客户端。"""
        self._stdin_fd: Optional[int] = None
        self._stdin_opened_here = False
        self._saved_console_mode: Optional[int] = None
        # 启动交互会话前保存控制台输出代码页，会话结束后精确还原。
        # 中文系统默认 936/GBK；若不切到 65001(UTF-8)，远端 claude 等
        # TUI 发来的 UTF-8 多字节字符（如 ❯ U+276F = E2 9D AF）会被
        # conhost 按 GBK 解释 → 显示为方框 □ 或乱码。
        self._saved_output_cp: Optional[int] = None

    def connect_and_send(
        self,
        ssh_ip: str,
        ssh_port: int,
        content: str,
        username: Optional[str] = None,
        private_key_file: Optional[str] = None,
    ) -> int:
        """连接 SSH 端点，发送 content，进入交互模式。

        Args:
            ssh_ip: SSH 主机地址。
            ssh_port: SSH 端口。
            content: 发送给远端 Agentos 的内容（如 "claude"）。
            username: SSH 登录用户名；默认当前系统用户。
            private_key_file: 私钥文件路径（等价于 `ssh -i <file>`）；
                提供时使用该私钥认证，并停止探测 ssh-agent 与默认密钥。

        Raises:
            SshTunnelError: SSH 连接失败、paramiko 未安装或交互异常。
        """
        try:
            import paramiko
        except ImportError as exc:
            raise errors.SshTunnelError(
                "paramiko 库未安装，无法建立 SSH 隧道。"
            ) from exc

        # 默认用户名：当前系统用户。
        if username is None:
            username = self._default_username()

        client = paramiko.SSHClient()
        # 自动添加主机密钥（gateway 中转，信任 gateway）。
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 指定私钥时只使用该私钥认证；未指定时保留 agent / 默认密钥探测。
        use_key = private_key_file is not None

        try:
            client.connect(
                hostname=ssh_ip,
                port=ssh_port,
                username=username,
                timeout=15,
                allow_agent=not use_key,
                look_for_keys=not use_key,
                key_filename=private_key_file,
                disabled_algorithms={"pubkeys": ["ssh-dss"]},
            )
        except TypeError:
            try:
                client.connect(
                    hostname=ssh_ip,
                    port=ssh_port,
                    username=username,
                    timeout=15,
                    allow_agent=not use_key,
                    look_for_keys=not use_key,
                    key_filename=private_key_file,
                )
            except Exception as exc:
                raise errors.SshTunnelError(
                    f"SSH 连接失败 ({ssh_ip}:{ssh_port}, user={username}): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        except Exception as exc:
            raise errors.SshTunnelError(
                f"SSH 连接失败 ({ssh_ip}:{ssh_port}, user={username}): "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        try:
            return self._interactive_session(client, content)
        finally:
            client.close()

    def _interactive_session(self, client, content: str) -> int:
        """建立交互式 shell 会话，发送 content，转发 IO。

        返回 shell 退出码。
        """
        import socket

        import paramiko

        # 使用本地终端类型（默认 xterm-256color），避免 vt100 导致
        # vi 中 Delete 键失效、粘贴丢失前两行等问题。
        term = os.environ.get("TERM", "xterm-256color")
        channel = client.invoke_shell(term=term)

        # 立即发送内容，不要等待——sandbox 可能快速关闭 channel。
        # 如果 channel 已关闭，send 会抛出 OSError。
        try:
            channel.send(content + "\n")
        except (OSError, socket.error) as exc:
            raise errors.SshTunnelError(
                f"SSH channel send failed: {exc}. "
                f"Sandbox may have rejected the SSH connection."
            ) from exc

        # 进入交互模式：转发 stdin <-> channel。
        return self._forward_io(channel)

    def _forward_io(self, channel) -> int:
        """转发 stdin <-> SSH channel，直到 channel 关闭。

        返回退出码（如果可获取，否则返回 0）。
        """
        import select
        import time

        # 注册 SIGWINCH：终端大小变化时通知 SSH channel 的 PTY。
        # 若不转发 resize，TUI 应用（claude、opencode 等）不知道终端尺寸变化，
        # 会导致渲染错乱、对话框消失、输入异常。
        resize_flag = [False]
        old_sigwinch = None
        if os.name != "nt":
            import signal
            old_sigwinch = signal.signal(
                signal.SIGWINCH,
                lambda signum, frame: resize_flag.__setitem__(0, True),
            )

        old_tty = None
        if os.name != "nt":
            # POSIX：设置终端为原始模式。
            import termios
            import tty
            try:
                old_tty = termios.tcgetattr(sys.stdin.fileno())
                tty.setraw(sys.stdin.fileno())
            except (termios.error, OSError):
                old_tty = None
        else:
            # Windows：设置控制台为原始模式。
            # 启用输出句柄的 VT 处理，否则 TUI 输出的 ANSI 转义序列
            #（颜色、光标移动等）会被当作普通文本原样显示，导致乱码。
            self._enable_win_vt_processing()
            # 设置前先保存原始模式，确保恢复时精确还原。
            self._save_console_mode()
            # 排空输入缓冲区，防止残留字节被读取后误发送到 SSH 通道。
            self._flush_stdin()
            self._set_win_console_raw(True)
            self._flush_stdin()
            # 初始化 stdin 文件描述符（用于读取完整 DBCS 字符）。
            self._init_stdin_fd()
            # 记录初始控制台尺寸，用于轮询检测 resize（Windows 无 SIGWINCH）。
            last_console_size = self._get_console_size()
            # Windows resize 轮询计数器（每 10 次检查一次，即 ~100ms 间隔）。
            resize_poll_counter = 0

        # 初始设置 SSH channel PTY 尺寸与本地终端一致。
        self._resize_channel(channel)
        # 延迟第二次 resize 计数器：等待远程 TUI 启动后再次同步尺寸。
        # 对于 opencode 等 TUI 应用，初始 resize 可能发生在远程命令
        # 启动之前，导致远程 PTY 仍使用默认尺寸（80x24）。
        delayed_resize_counter = 30  # ~300ms 后执行第二次 resize

        # Windows：输入转发放在独立线程中，使用阻塞 os.read。
        # 不要用 msvcrt.kbhit() 非阻塞轮询——kbhit() 在 raw 模式 +
        # ENABLE_VIRTUAL_TERMINAL_INPUT 下可能永远返回 False，
        # 导致键盘输入完全无响应（终端卡死）。
        # 线程为 daemon：SSH 会话结束后 join 超时即可，
        # 进程退出时被强制终止，阻塞读取不会阻塞进程退出。
        stdin_thread = None
        if os.name == "nt":
            def _win_stdin_forwarder() -> None:
                """阻塞读取 stdin 并转发到 channel（daemon 线程）。"""
                # 确保 stdin fd 已初始化（DuplicateHandle 副本，避免
                # os.close 销毁原始 stdin 句柄）。
                if self._stdin_fd is None:
                    self._init_stdin_fd()
                while True:
                    if self._stdin_fd is None:
                        return
                    try:
                        data = os.read(self._stdin_fd, 1024)
                    except OSError:
                        break
                    if not data:
                        break
                    # 拦截 Ctrl+V (0x16)：从剪贴板读取并替换为剪贴板内容，
                    # 让 cmd/powershell 在 QuickEdit 禁用时仍可通过 Ctrl+V 粘贴。
                    # 0x16 在所有常见代码页（CP437/GBK/UTF-8）中均为单字节，
                    # 可在字节流阶段直接 split。
                    if b"\x16" in data:
                        parts = data.split(b"\x16")
                        # 非 Ctrl+V 片段仍需按控制台代码页转换
                        converted_parts = []
                        for p in parts:
                            converted_parts.append(
                                self._convert_cp_to_utf8(p)
                            )
                        clip = self._read_win_clipboard()
                        data = clip.join(converted_parts)
                    else:
                        # 从控制台代码页（如 936/GBK）转换为 UTF-8。
                        data = self._convert_cp_to_utf8(data)
                    try:
                        channel.sendall(data)
                    except (OSError, EOFError):
                        break

            stdin_thread = threading.Thread(
                target=_win_stdin_forwarder, daemon=True
            )
            stdin_thread.start()

        # 输出队列：解耦"channel 读取"与"控制台写入"。
        # 详见主循环注释——SSH channel 的流控机制要求本地持续 drain
        # recv 缓冲区，否则远端 write() 阻塞 → claude 事件循环卡死 →
        # 全屏下无法输入。把 stdout 写入挪到独立线程后，主循环只负责
        # 立即把 recv 的数据塞进队列，channel 缓冲区永远被快速清空。
        output_queue: "queue.Queue[Optional[bytes]]" = queue.Queue()

        def _output_writer() -> None:
            """后台线程：从 output_queue 取出 channel 数据写入 stdout。

            与 supervisor 的 _console_writer 同模式：以独立线程节奏
            消费队列，慢一点也无害，反正不会反过来阻塞主循环 drain
            SSH channel。
            """
            stdout_buffer = sys.stdout.buffer
            try:
                while True:
                    data = output_queue.get()
                    if data is None:
                        break
                    try:
                        stdout_buffer.write(data)
                        stdout_buffer.flush()
                    except (OSError, ValueError):
                        break
            except (OSError, ValueError):
                pass

        output_writer_thread = threading.Thread(
            target=_output_writer, daemon=True
        )
        output_writer_thread.start()

        try:
            channel_ready = True
            while channel_ready:
                # --- Resize 检测 ---
                if os.name != "nt":
                    if resize_flag[0]:
                        resize_flag[0] = False
                        self._resize_channel(channel)
                else:
                    # Windows：每 10 次迭代（~100ms）检查一次 resize，
                    # 避免频繁 Win32 API 调用导致卡顿。
                    resize_poll_counter += 1
                    if resize_poll_counter >= 10:
                        resize_poll_counter = 0
                        cur_size = self._get_console_size()
                        if cur_size is not None and cur_size != last_console_size:
                            last_console_size = cur_size
                            self._resize_channel(channel)

                # 延迟第二次 resize：等待远程 TUI 启动后同步尺寸，
                # 确保 opencode 等应用获得正确的终端尺寸全屏显示。
                if delayed_resize_counter > 0:
                    delayed_resize_counter -= 1
                    if delayed_resize_counter == 0:
                        self._resize_channel(channel)

                # 检查 channel 是否有数据可读。
                # **关键**：只入队，绝不在此处 write/flush——否则
                # 全屏 TUI 输出洪峰会让 conhost 渲染阻塞主循环 →
                # channel.recv 不再被调用 → SSH 流控触发 → 远端
                # claude write() 阻塞 → 事件循环卡死 → 输入冻结。
                if channel.recv_ready():
                    data = channel.recv(65536)
                    if not data:
                        channel_ready = False
                        break
                    output_queue.put(data)

                # 检查 stdin 是否有数据可读（非阻塞）。
                # POSIX：主循环内联转发；Windows：已由独立线程
                # _win_stdin_forwarder 处理（阻塞 os.read 更可靠）。
                if os.name != "nt":
                    stdin_data = self._read_stdin_nonblocking()
                    if stdin_data:
                        channel.sendall(stdin_data)

                # 检查 channel 是否已关闭。
                if channel.exit_status_ready():
                    # 排空剩余输出。
                    while channel.recv_ready():
                        data = channel.recv(65536)
                        if not data:
                            break
                        output_queue.put(data)
                    break

                time.sleep(0.01)

            # 获取退出码。
            exit_code = channel.recv_exit_status()
            return exit_code if exit_code is not None else 0
        finally:
            # 通知 _output_writer 收尾：主循环退出后投递哨兵，
            # writer 处理完队列中剩余数据后即可退出。
            output_queue.put(None)
            # 等待 stdin 转发线程退出（daemon，超时不阻塞进程退出）。
            # 线程可能阻塞在 os.read 上；先 join 再关闭 fd，
            # fd 关闭后 os.read 抛 OSError 线程随即退出。
            if stdin_thread is not None:
                stdin_thread.join(timeout=1)
            # 等待 output writer 线程排空剩余 channel 数据并写入 stdout。
            # 必须在投递 None 哨兵之后；writer 收到哨兵即收尾。
            output_writer_thread.join(timeout=3)
            # 关闭在本模块打开的 stdin fd。
            self._close_stdin_fd()
            # 恢复 SIGWINCH 处理器。
            if old_sigwinch is not None:
                import signal
                signal.signal(signal.SIGWINCH, old_sigwinch)
            # 恢复终端模式。
            if old_tty is not None:
                import termios
                try:
                    termios.tcsetattr(
                        sys.stdin.fileno(),
                        termios.TCSADRAIN,
                        old_tty,
                    )
                except (termios.error, OSError):
                    pass
            if os.name == "nt":
                self._restore_console_mode()

    def _resize_channel(self, channel) -> None:
        """查询本地终端尺寸并同步到 SSH channel 的 PTY。"""
        if os.name != "nt":
            try:
                import fcntl
                import termios
                import struct
                s = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
                rows, cols, xpix, ypix = struct.unpack("HHHH", s)
                if rows > 0 and cols > 0:
                    channel.resize_pty(
                        width=cols, height=rows,
                        width_pixels=xpix, height_pixels=ypix,
                    )
            except (OSError, struct.error, IOError):
                pass
        else:
            size = self._get_console_size()
            if size is not None:
                cols, rows = size
                if cols > 0 and rows > 0:
                    channel.resize_pty(width=cols, height=rows)

    @staticmethod
    def _get_console_size():
        """Windows：获取控制台窗口尺寸 (cols, rows)。"""
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            class COORD(ctypes.Structure):
                _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

            class SmallRect(ctypes.Structure):  # noqa: N801 - 对应 Win32 SMALL_RECT 结构体
                _fields_ = [
                    ("Left", wintypes.SHORT),
                    ("Top", wintypes.SHORT),
                    ("Right", wintypes.SHORT),
                    ("Bottom", wintypes.SHORT),
                ]

            class ConsoleScreenBufferInfo(ctypes.Structure):
                _fields_ = [
                    ("dwSize", COORD),
                    ("dwCursorPosition", COORD),
                    ("wAttributes", wintypes.WORD),
                    ("srWindow", SmallRect),
                    ("dwMaximumWindowSize", COORD),
                ]

            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            csbi = ConsoleScreenBufferInfo()
            if kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi)):
                sr = csbi.srWindow
                cols = sr.Right - sr.Left + 1
                rows = sr.Bottom - sr.Top + 1
                return (cols, rows)
        except (ImportError, OSError, AttributeError, ctypes.WinError):
            pass
        return None

    def _read_stdin_nonblocking(self) -> bytes:
        """非阻塞读取 stdin 数据。

        POSIX：使用 select 检查可读性。
        Windows：使用 msvcrt.kbhit() 检查键盘输入，然后用 os.read 读取
        完整字节（包括 DBCS 多字节字符），避免 msvcrt.getch() 逐个字节
        返回导致中文乱码。
        """
        if os.name == "nt":
            return self._read_stdin_win()
        # POSIX
        import select
        try:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if readable:
                data = os.read(sys.stdin.fileno(), 4096)
                return data
        except (OSError, ValueError):
            pass
        return b""

    def _read_stdin_win(self) -> bytes:
        """Windows 非阻塞读取 stdin，使用 os.read 读取完整 DBCS 字符。

        不再使用 msvcrt.getch()（逐个字节返回，DBCS 字符会被拆开导致乱码），
        改用 os.read 从 stdin 文件描述符读取，一次读取完整的多字节字符。
        然后从控制台代码页（如 936/GBK）转换为 UTF-8。
        """
        try:
            import msvcrt
            if msvcrt.kbhit():
                # 确保 stdin fd 已初始化
                if self._stdin_fd is None:
                    self._init_stdin_fd()
                if self._stdin_fd is not None:
                    data = os.read(self._stdin_fd, 1024)
                    if data:
                        try:
                            import ctypes
                            kernel32 = ctypes.WinDLL(
                                "kernel32", use_last_error=True
                            )
                            input_cp = kernel32.GetConsoleCP()
                            if input_cp != 65001:
                                # 从控制台代码页解码为 Unicode 再编码为 UTF-8
                                text = data.decode(
                                    f"cp{input_cp}", errors="replace"
                                )
                                return text.encode("utf-8")
                        except (ImportError, OSError, AttributeError):
                            # 控制台代码页查询失败，跳过转换，使用原始数据
                            pass
                    return data
        except (ImportError, OSError):
            pass
        return b""

    def _init_stdin_fd(self) -> None:
        """初始化 Windows 控制台 stdin 文件描述符。

        使用 msvcrt.open_osfhandle 将控制台句柄包装为 Python fd，
        以便 os.read 能读取完整的 DBCS 字符（与 ConPTY _input_forwarder
        相同的模式）。

        **关键**：必须先 DuplicateHandle 复制 stdin 句柄，再用副本创建 fd。
        因为 os.close(fd) 会同时 CloseHandle 底层句柄，若直接使用
        GetStdHandle(STD_INPUT_HANDLE) 的原始句柄，close 后 stdin 句柄
        被永久销毁，后续 TUI 检测 isTTY 失败（"requires an interactive TTY"）。
        """
        if self._stdin_fd is not None:
            return
        try:
            import ctypes
            import _winapi
            import msvcrt
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.DuplicateHandle.argtypes = [
                wintypes.HANDLE, wintypes.HANDLE,
                wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE),
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
            ]
            kernel32.DuplicateHandle.restype = wintypes.BOOL

            current_process = kernel32.GetCurrentProcess()
            original_handle = _winapi.GetStdHandle(_winapi.STD_INPUT_HANDLE)
            duplicate = wintypes.HANDLE()
            # DUPLICATE_SAME_ACCESS = 2
            if not kernel32.DuplicateHandle(
                current_process, wintypes.HANDLE(original_handle),
                current_process, ctypes.byref(duplicate),
                0, False, 2,
            ):
                self._stdin_fd = None
                self._stdin_opened_here = False
                return

            self._stdin_fd = msvcrt.open_osfhandle(
                duplicate.value, os.O_RDONLY,
            )
            self._stdin_opened_here = True
        except Exception:
            self._stdin_fd = None
            self._stdin_opened_here = False

    def _close_stdin_fd(self) -> None:
        """关闭在本模块打开的 stdin 文件描述符。"""
        if self._stdin_fd is not None and self._stdin_opened_here:
            try:
                os.close(self._stdin_fd)
            except OSError:
                pass
        self._stdin_fd = None
        self._stdin_opened_here = False

    @staticmethod
    def _flush_stdin() -> None:
        """排空 Windows 控制台输入缓冲区中的残留字节。"""
        try:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
        except (ImportError, OSError):
            pass

    def _enable_win_vt_processing(self) -> None:
        """启用 Windows 控制台输出句柄的 ANSI/VT 转义序列处理，并把输出代码页切到 UTF-8。

        不设置 VT 处理标志时，WriteFile/WriteConsole 会将 ANSI 转义码
       （颜色、光标移动、清屏等）当作普通文本原样输出，导致 TUI 乱码。
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        同时把输出代码页设为 65001(UTF-8)：
        远端 claude 等 TUI 应用通过 SSH channel 发送的字节流是 UTF-8。
        本地 launcher 用 sys.stdout.buffer.write 原样写出后，conhost 按
        "当前活动输出代码页"解释字节——中文系统默认 936/GBK，会把
        UTF-8 多字节字符（如 ❯ U+276F = E2 9D AF）按 GBK 错误解码 →
        显示为方框 □ 或乱码。切到 65001 后 conhost 按 UTF-8 解码，
        配合支持 Unicode 的字体（如 Windows Terminal Cascadia Mono、
        cmd.exe 旧版 Consolas）即可正确渲染。

        会话前保存原代码页到 self._saved_output_cp，退出时由
        _restore_console_mode 精确还原（避免污染用户 cmd 环境）。
        """
        try:
            import ctypes
            from ctypes import wintypes
            import _winapi

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # 1) 保存并设置输出代码页为 UTF-8。
            kernel32.GetConsoleOutputCP.restype = wintypes.UINT
            kernel32.SetConsoleOutputCP.argtypes = [wintypes.UINT]
            kernel32.SetConsoleOutputCP.restype = wintypes.BOOL
            original_cp = kernel32.GetConsoleOutputCP()
            if original_cp != 65001:
                self._saved_output_cp = original_cp
                kernel32.SetConsoleOutputCP(65001)
            # 2) 启用 ENABLE_VIRTUAL_TERMINAL_PROCESSING。
            handle = kernel32.GetStdHandle(_winapi.STD_OUTPUT_HANDLE)
            mode = wintypes.DWORD()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return
            new_mode = mode.value | 0x0004
            kernel32.SetConsoleMode(handle, new_mode)
        except (OSError, AttributeError):
            pass

    @staticmethod
    def _set_win_console_raw(raw: bool) -> None:
        """Windows 控制台原始模式切换。

        必须启用 ENABLE_VIRTUAL_TERMINAL_INPUT（0x0200），否则：
        - 终端输出的 VT 转义序列（颜色、光标移动、清屏等）不会被正确渲染
        - 鼠标事件（TUI 应用如 opencode 启用鼠标追踪后）不会生成 VT 序列
        - 远程 TUI 应用的输出会显示为原始转义码乱码

        必须清除 ENABLE_PROCESSED_INPUT（0x0001），否则 Ctrl+C 被本地控制台
        拦截为 CTRL_C_EVENT 信号，不会转发到 SSH channel，导致无法退出
        远程 TUI 应用（opencode 等）。

        raw=True 时**保留 ENABLE_QUICK_EDIT_MODE（0x0040）**：
        让用户可以用鼠标选中控制台中的历史消息进行复制。QuickEdit
        开启后，鼠标点击控制台客户区会进入"选择模式"，期间键盘输入
        会被截留，但用户可以通过 Enter 或单击退出选择模式，键盘输入
        即可恢复。
        """
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_uint32()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            if raw:
                # 禁用 ENABLE_PROCESSED_INPUT(0x0001, Ctrl+C 信号拦截)、
                # ENABLE_LINE_INPUT(0x0002) 和 ENABLE_ECHO_INPUT(0x0004)，
                # 启用 ENABLE_VIRTUAL_TERMINAL_INPUT(0x0200) 以支持 VT 序列。
                # 保留 ENABLE_QUICK_EDIT_MODE(0x0040)，允许鼠标选中复制历史消息
                new_mode = (
                    mode.value
                    & ~0x0001  # 清 PROCESSED_INPUT
                    & ~0x0002  # 清 LINE_INPUT
                    & ~0x0004  # 清 ECHO_INPUT
                    # 保留 QUICK_EDIT_MODE，允许鼠标选中复制历史消息
                ) | 0x0080 | 0x0200  # 置 EXTENDED_FLAGS | VIRTUAL_TERMINAL_INPUT
            else:
                # 恢复默认模式
                new_mode = (mode.value | 0x0001 | 0x0002 | 0x0004) & ~0x0200
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
        本函数配合 _win_stdin_forwarder 拦截 ``\\x16``，主动从剪贴板取出
        文本转发到 SSH channel，恢复 cmd/powershell 下的粘贴能力。
        Windows Terminal 自身处理粘贴，不依赖此机制。

        Returns:
            剪贴板文本的 UTF-8 字节；剪贴板不可用或无文本时返回 ``b""``。
        """
        try:
            import ctypes
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
    def _convert_cp_to_utf8(data: bytes) -> bytes:
        """从控制台活动代码页（如 936/GBK）转换为 UTF-8。

        代码页查询失败或无需转换时返回原始字节。
        """
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            input_cp = kernel32.GetConsoleCP()
            if input_cp != 65001:
                text = data.decode(f"cp{input_cp}", errors="replace")
                return text.encode("utf-8")
        except (ImportError, OSError, AttributeError):
            pass
        return data

    def _save_console_mode(self) -> None:
        """保存当前控制台输入模式，用于后续精确恢复。"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-10)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                self._saved_console_mode = mode.value
        except (OSError, AttributeError):
            self._saved_console_mode = None

    def _restore_console_mode(self) -> None:
        """精确恢复之前保存的控制台输入模式与输出代码页。

        使用保存的原始模式精确还原，避免 read-modify-write 模式
        在多次调用间丢失或引入额外标志位。

        同时恢复输出代码页（_enable_win_vt_processing 切到 65001 之前
        保存的原值，中文系统通常为 936/GBK），避免污染用户的 cmd 环境。
        """
        if self._saved_console_mode is None:
            # 没有保存过模式，回退到 _set_win_console_raw(False) 的默认恢复。
            self._set_win_console_raw(False)
        else:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-10)
                kernel32.SetConsoleMode(handle, self._saved_console_mode)
            except (OSError, AttributeError):
                pass
        # 恢复输出代码页（无论上面模式恢复是否成功都尝试恢复 CP）。
        if self._saved_output_cp is not None:
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.SetConsoleOutputCP.argtypes = [wintypes.UINT]
                kernel32.SetConsoleOutputCP.restype = wintypes.BOOL
                kernel32.SetConsoleOutputCP(self._saved_output_cp)
            except (OSError, AttributeError):
                pass
            self._saved_output_cp = None

    @staticmethod
    def _default_username() -> str:
        """获取当前系统用户名。"""
        try:
            import getpass
            return getpass.getuser()
        except Exception:
            return os.environ.get("USER") or os.environ.get("USERNAME") or "agentos"
