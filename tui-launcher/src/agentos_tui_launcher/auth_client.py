"""IAM HTTP 客户端：登录 / 刷新 / 登出 / users/me。

公共契约第 8 节定义本模块的 HTTP 协议。

要求：
- 严格实现第 8 节 IAM HTTP 契约，并设置独立的连接超时与读取超时。
- 生产远程地址只接受 HTTPS。HTTP 仅可在显式的本地开发配置下使用。
- 校验成功响应包含所有必需字段，缺失/空值/类型不符时抛 RemoteContractError。
- 将错误稳定映射为：
    InvalidCredentials / AuthenticationExpired / PermissionDenied /
    NetworkUnavailable / RemoteServiceError / RemoteContractError
- 不在异常文本、日志、trace、HTTP 调试输出中包含密码、token 或完整 Authorization 头。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, TYPE_CHECKING

from . import errors


# ============================================================================
# 公共数据类型
# ============================================================================


@dataclass(frozen=True)
class UserProfile:
    """users/me 返回的用户资料。"""

    user_id: str
    username: str
    role: str
    is_active: bool


# ============================================================================
# AuthClient 协议
# ============================================================================


class AuthClient(Protocol):
    """IAM HTTP 客户端协议。"""

    def login(self, service_url: str, username: str, password: str) -> "AuthSession":
        """POST /api/v1/auth/login。"""
        ...

    def refresh(self, service_url: str, refresh_token: str) -> "AuthSession":
        """POST /api/v1/auth/refresh。"""
        ...

    def logout(
        self,
        service_url: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        """POST /api/v1/auth/logout。"""
        ...

    def get_current_user(self, service_url: str, access_token: str) -> UserProfile:
        """GET /api/v1/users/me。"""
        ...


# ============================================================================
# AuthSession（避免循环导入）
# ============================================================================

# 引入 AuthSession 会形成 user_context -> auth_client 循环；
# 因此在 user_context.py 中单独定义 AuthSession，本模块只是从那里 import 使用。
# 但本模块需要返回 AuthSession，且 user_context 需要导入本模块的 UserProfile；
# 为打破循环，这里通过 TYPE_CHECKING 引用。

if TYPE_CHECKING:
    from .user_context import AuthSession  # noqa: F401


# ============================================================================
# HTTP 错误映射辅助
# ============================================================================


def _map_http_error(status_code: int, *, is_auth_context: bool) -> errors.LauncherError:
    """将 HTTP 状态码稳定映射为 LauncherError 子类。

    - 400 / 401 / 422：认证或参数错误
    - 403：权限不足
    - 404 / 5xx：远端服务错误
    - 其它：按范围归类
    """
    if status_code == 401:
        # 登录被拒绝（用户名/密码错误）或 token 失效，由调用方区分。
        if is_auth_context:
            return errors.AuthenticationExpired("Authentication expired.")
        return errors.InvalidCredentials("Invalid credentials.")
    if status_code in (400, 422):
        # 客户端请求格式错误：通常是契约问题。
        return errors.RemoteContractError("Request rejected by server.")
    if status_code == 403:
        return errors.PermissionDenied("Permission denied.")
    if 500 <= status_code < 600:
        return errors.RemoteServiceError("Remote service error.")
    return errors.RemoteServiceError(f"Unexpected HTTP status: {status_code}")


# ============================================================================
# Requests 实现
# ============================================================================


class RequestsAuthClient:
    """基于 `requests` 库的 AuthClient 实现。

    设计文档允许实现使用不同的 HTTP 库；本实现选用 requests 因为：
      - 跨平台
      - 公开契约要求的行为与 requests 的异常模型对应较好
      - 后续调试时容易理解

    实现注意：
    - 所有 HTTP 调用必须设置超时。
    - 不得在异常文本/日志中包含密码、token 或完整 Authorization 头。
    - HTTPS 是生产默认；HTTP 仅在显式 allow_insecure_http 时允许。
    """

    # 独立的连接超时与读取超时（公共契约 4.3 节）。
    CONNECT_TIMEOUT = 5.0
    READ_TIMEOUT = 15.0

    def __init__(self, *, allow_insecure_http: bool = False) -> None:
        # 延迟导入 requests，避免在不需要时强制依赖。
        try:
            import requests  # type: ignore
        except ImportError as exc:  # pragma: no cover - 应在依赖中预装
            raise errors.LauncherError(
                "requests library not installed; cannot make HTTP calls."
            ) from exc

        self._requests = requests
        self._allow_insecure_http = allow_insecure_http

    # ------------------------------------------------------------------
    # login
    # ------------------------------------------------------------------

    def login(self, service_url: str, username: str, password: str) -> "AuthSession":
        url = self._build_url(service_url, "/api/v1/auth/login")
        body = {"username": username, "password": password}

        # 不在异常文本中包含密码或 username。
        try:
            resp = self._requests.post(
                url,
                json=body,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
            )
        except self._requests.exceptions.ConnectionError as exc:
            raise errors.NetworkUnavailable("Cannot connect to service.") from exc
        except self._requests.exceptions.Timeout as exc:
            raise errors.NetworkUnavailable("Request timed out.") from exc
        except self._requests.exceptions.RequestException as exc:
            raise errors.NetworkUnavailable("Network request failed.") from exc

        if resp.status_code != 200:
            raise _map_http_error(resp.status_code, is_auth_context=False)

        data = self._parse_envelope(resp)
        return self._build_session_from_login(service_url, data)

    # ------------------------------------------------------------------
    # refresh
    # ------------------------------------------------------------------

    def refresh(self, service_url: str, refresh_token: str) -> "AuthSession":
        url = self._build_url(service_url, "/api/v1/auth/refresh")
        body = {"refresh_token": refresh_token}

        try:
            resp = self._requests.post(
                url,
                json=body,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
            )
        except self._requests.exceptions.ConnectionError as exc:
            raise errors.NetworkUnavailable("Cannot connect to service.") from exc
        except self._requests.exceptions.Timeout as exc:
            raise errors.NetworkUnavailable("Request timed out.") from exc
        except self._requests.exceptions.RequestException as exc:
            raise errors.NetworkUnavailable("Network request failed.") from exc

        if resp.status_code != 200:
            # refresh 被拒绝、用户被禁用/删除/token 过期：401 -> AuthenticationExpired
            raise _map_http_error(resp.status_code, is_auth_context=True)

        data = self._parse_envelope(resp)
        return self._build_session_from_login(service_url, data)

    # ------------------------------------------------------------------
    # logout
    # ------------------------------------------------------------------

    def logout(
        self,
        service_url: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        url = self._build_url(service_url, "/api/v1/auth/logout")
        body = {"refresh_token": refresh_token}
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = self._requests.post(
                url,
                json=body,
                headers=headers,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
            )
        except self._requests.exceptions.RequestException as exc:
            # 网络/服务端失败：调用方应继续本地清理。
            raise errors.NetworkUnavailable("Network request failed.") from exc

        if resp.status_code != 200:
            raise _map_http_error(resp.status_code, is_auth_context=True)

    # ------------------------------------------------------------------
    # users/me
    # ------------------------------------------------------------------

    def get_current_user(self, service_url: str, access_token: str) -> UserProfile:
        url = self._build_url(service_url, "/api/v1/users/me")
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = self._requests.get(
                url,
                headers=headers,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
            )
        except self._requests.exceptions.RequestException as exc:
            raise errors.NetworkUnavailable("Network request failed.") from exc

        if resp.status_code != 200:
            raise _map_http_error(resp.status_code, is_auth_context=True)

        data = self._parse_envelope(resp)
        return self._build_user_profile(data)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _build_url(self, service_url: str, path: str) -> str:
        """构造请求 URL，校验 HTTPS。"""
        # 简单实现：拼接；公共契约要求规范化 origin 后再拼接。
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(service_url)
        if parts.scheme == "http" and not self._allow_insecure_http:
            raise errors.ConfigError(
                "HTTP is not allowed in production; set allow_insecure_http explicitly."
            )
        if parts.scheme not in ("http", "https"):
            raise errors.ConfigError(f"Unsupported scheme: {parts.scheme}")

        # 去掉末尾斜杠，避免拼出 //
        base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    @staticmethod
    def _parse_envelope(resp) -> dict:
        """解析成功响应外层 envelope。"""
        # {"code": 200, "message": "success", "data": {...}}
        # FastAPI 校验或 HTTP 错误可能使用 {"detail": ...}，按结构判断。
        try:
            payload = resp.json()
        except ValueError as exc:
            raise errors.RemoteContractError("Response is not JSON.") from exc

        if not isinstance(payload, dict):
            raise errors.RemoteContractError("Response is not a JSON object.")

        # 兼容 {"detail": ...} 形式
        if "detail" in payload and "data" not in payload:
            # 服务端错误格式：交由调用方映射。
            raise errors.RemoteServiceError(
                f"Server rejected request: {payload.get('detail')}"
            )

        data = payload.get("data")
        if data is None:
            raise errors.RemoteContractError("Response missing 'data' field.")
        if not isinstance(data, dict):
            raise errors.RemoteContractError("Response 'data' is not an object.")
        return data

    @staticmethod
    def _build_session_from_login(service_url: str, data: dict) -> "AuthSession":
        """从 login/refresh 响应构造 AuthSession。

        校验所有必需字段；缺失/空值抛 RemoteContractError。
        """
        # 必需字段：access_token / refresh_token / user_id / username / role
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        user_id = data.get("user_id")
        username = data.get("username")
        role = data.get("role")

        missing = []
        if not access_token:
            missing.append("access_token")
        if not refresh_token:
            missing.append("refresh_token")
        if not user_id:
            missing.append("user_id")
        if not username:
            missing.append("username")
        if not role:
            missing.append("role")
        if missing:
            raise errors.RemoteContractError(
                f"Login response missing required fields: {', '.join(missing)}."
            )

        # 延迟导入以打破循环。
        from .user_context import AuthSession, UserContext

        context = UserContext(
            service_url=service_url,
            user_id=user_id,
            username=username,
            role=role,
            access_token=access_token,
        )
        return AuthSession(
            context=context,
            refresh_token=refresh_token,
            save_login=True,  # 由 SessionService 在 login() 中根据用户选择覆盖
        )

    @staticmethod
    def _build_user_profile(data: dict) -> UserProfile:
        """从 users/me 响应构造 UserProfile。"""
        user_id = data.get("user_id")
        username = data.get("username")
        role = data.get("role")
        is_active = data.get("is_active")

        if not user_id:
            raise errors.RemoteContractError(
                "users/me response missing 'user_id'."
            )
        if not username:
            raise errors.RemoteContractError(
                "users/me response missing 'username'."
            )
        if not role:
            raise errors.RemoteContractError(
                "users/me response missing 'role'."
            )
        if is_active is None:
            raise errors.RemoteContractError(
                "users/me response missing 'is_active'."
            )
        if not isinstance(is_active, bool):
            raise errors.RemoteContractError(
                "users/me response 'is_active' is not a boolean."
            )
        return UserProfile(
            user_id=user_id,
            username=username,
            role=role,
            is_active=is_active,
        )
