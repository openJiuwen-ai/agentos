"""稳定的错误类别。

公共契约第 10.1 节要求实现保留以下可区分语义：
UsageError / ConfigError / CredentialStoreUnavailable / CredentialCorrupted /
InvalidCredentials / AuthenticationExpired / PermissionDenied /
NetworkUnavailable / RemoteServiceError / RemoteContractError /
ExecutableUnavailable / CancelRejected / CancelTimeout /
HandoffUnavailable / ReauthenticationUnavailable / ReauthenticationLoop。

所有错误消息不得包含密码、token、Authorization 头、完整 argv、内部堆栈或
未经脱敏的用户敏感信息。
"""

from __future__ import annotations


class LauncherError(Exception):
    """所有 launcher 错误的基类。"""


# --------------------------------------------------------------------------
# CLI / 配置 / 凭据存储
# --------------------------------------------------------------------------


class UsageError(LauncherError):
    """CLI 或 /switch-claude 参数非法。"""


class ConfigError(LauncherError):
    """配置缺失、损坏或不安全 URL。"""


class CredentialStoreUnavailable(LauncherError):
    """OS 安全存储不可用；可改为本次会话登录。"""


class CredentialCorrupted(LauncherError):
    """安全存储中的凭据无法解码或损坏。"""


# --------------------------------------------------------------------------
# 认证相关
# --------------------------------------------------------------------------


class InvalidCredentials(LauncherError):
    """登录被拒绝；可重试登录。"""


class AuthenticationExpired(LauncherError):
    """refresh 被拒绝；清凭据后重新登录。"""


class PermissionDenied(LauncherError):
    """服务端 403；保持当前身份。"""


class NetworkUnavailable(LauncherError):
    """超时、DNS、连接失败；不得伪装成认证失败。"""


class RemoteServiceError(LauncherError):
    """服务端 5xx；可稍后重试。"""


class RemoteContractError(LauncherError):
    """成功响应字段不完整或非法；不得启动 TUI。"""


# --------------------------------------------------------------------------
# 可执行文件 / handoff / 取消
# --------------------------------------------------------------------------


class ExecutableUnavailable(LauncherError):
    """主或目标程序缺失。"""


class CancelRejected(LauncherError):
    """服务端拒绝中断。"""


class CancelTimeout(LauncherError):
    """未确认服务端停止。"""


class HandoffUnavailable(LauncherError):
    """非托管、协议非法、目标缺失。"""


class HandoffParseError(LauncherError):
    """子进程 stdout handoff JSON 解析失败。"""


class GatewayError(LauncherError):
    """gateway WebSocket 通信失败。"""


class SshTunnelError(LauncherError):
    """SSH 隧道建立或通信失败。"""


class ReauthenticationUnavailable(LauncherError):
    """非托管/显式模式、重新认证协议非法或无可刷新会话。"""


class ReauthenticationLoop(LauncherError):
    """60 秒窗口内重复收到重新认证动作。"""
