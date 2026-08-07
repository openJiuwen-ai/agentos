"""SSH 隧道客户端。

新设计（tui-switch-cc-design-new.md 第 10.3 节）下，launcher 从 gateway 获取
SSH 端点后，通过 SSH 隧道连接三方 Agentos：

1. 使用返回的 SSH IP 和 Port 连接
2. SSH 连接成功后，发送 content 并回车（通过 invoke_shell 交互式 shell 执行，
   等价于 `ssh -t user@host claude`，远端 sandbox 要求交互式 shell 通道）
3. 进入交互模式，用户与三方 Agentos 交互
4. 三方 Agentos 退出后返回退出码

本模块使用 `paramiko` 库实现 SSH 通信。paramiko 为可选依赖，
缺失时在运行时抛出 SshTunnelError。

交互模式实现：
- POSIX：使用 tty.setraw() 设置原始模式，转发 stdin <-> SSH channel
- Windows：使用 ctypes 设置控制台原始模式
- 两个线程分别转发 stdin -> channel 和 channel -> stdout
"""

from __future__ import annotations

import os
import sys
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
    ) -> int:
        ...


class ParamikoSshTunnelClient:
    """基于 paramiko 库的 SshTunnelClient 实现。

    - 连接到指定 SSH 端点
    - 打开交互式 shell，发送 content 并回车（等价于 `ssh -t user@host <content>`）
    - 进入交互模式转发
    - 返回退出码
    """

    def connect_and_send(
        self,
        ssh_ip: str,
        ssh_port: int,
        content: str,
        username: Optional[str] = None,
    ) -> int:
        """连接 SSH 端点，发送 content，进入交互模式。

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

        try:
            client.connect(
                hostname=ssh_ip,
                port=ssh_port,
                username=username,
                timeout=15,
                allow_agent=True,
                look_for_keys=True,
                disabled_algorithms={"pubkeys": ["ssh-dss"]},
            )
        except TypeError:
            try:
                client.connect(
                    hostname=ssh_ip,
                    port=ssh_port,
                    username=username,
                    timeout=15,
                    allow_agent=True,
                    look_for_keys=True,
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

        channel = client.invoke_shell()

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
            # Windows：设置控制台为原始模式（禁用行缓冲和输入处理）。
            self._set_win_console_raw(True)

        try:
            channel_ready = True
            while channel_ready:
                # 使用 select 检查 stdin 和 channel 的可读状态。
                rlist = []
                if sys.stdin and not sys.stdin.closed:
                    rlist.append(sys.stdin)
                if channel.recv_ready():
                    rlist.append(channel)
                # paramiko Channel 在 Windows 上不支持 select；
                # 使用简单轮询 + 短超时。
                import time

                # 检查 channel 是否有数据可读。
                if channel.recv_ready():
                    data = channel.recv(4096)
                    if not data:
                        channel_ready = False
                        break
                    try:
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                    except Exception:
                        channel_ready = False
                        break

                # 检查 stdin 是否有数据可读（非阻塞）。
                stdin_data = self._read_stdin_nonblocking()
                if stdin_data:
                    channel.sendall(stdin_data)

                # 检查 channel 是否已关闭。
                if channel.exit_status_ready():
                    # 排空剩余输出。
                    while channel.recv_ready():
                        data = channel.recv(4096)
                        if not data:
                            break
                        try:
                            sys.stdout.buffer.write(data)
                            sys.stdout.buffer.flush()
                        except Exception:
                            break
                    break

                time.sleep(0.01)

            # 获取退出码。
            exit_code = channel.recv_exit_status()
            return exit_code if exit_code is not None else 0
        finally:
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
                self._set_win_console_raw(False)

    def _read_stdin_nonblocking(self) -> bytes:
        """非阻塞读取 stdin 数据。

        POSIX：使用 select 检查可读性。
        Windows：使用 msvcrt 检查键盘输入。
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

    @staticmethod
    def _read_stdin_win() -> bytes:
        """Windows 非阻塞读取 stdin。"""
        try:
            import msvcrt
            if msvcrt.kbhit():
                return msvcrt.getch()
        except (ImportError, OSError):
            pass
        return b""

    @staticmethod
    def _set_win_console_raw(raw: bool) -> None:
        """Windows 控制台原始模式切换。"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_uint32()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            if raw:
                # 禁用 ENABLE_ECHO_INPUT 和 ENABLE_LINE_INPUT
                new_mode = mode.value & ~0x0002 & ~0x0004
            else:
                # 恢复默认模式
                new_mode = mode.value | 0x0002 | 0x0004
            kernel32.SetConsoleMode(handle, new_mode)
        except (OSError, AttributeError):
            pass

    @staticmethod
    def _default_username() -> str:
        """获取当前系统用户名。"""
        try:
            import getpass
            return getpass.getuser()
        except Exception:
            return os.environ.get("USER") or os.environ.get("USERNAME") or "agentos"
