"""不可变用户上下文与 SessionService。

`UserContext` 是一次子进程运行期间不可变的身份快照；
`AuthSession` 在 launcher 内存中维护可刷新身份；
`SessionService` 把 AuthClient / CredentialStore / ConfigStore 编排起来，
对外提供 login / restore / renew / logout / whoami。

公共契约第 3 节、第 4.4 节定义本模块的全部行为。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from . import errors
from .auth_client import AuthClient, UserProfile
from .config import ClientConfig, ConfigStore
from .credential_store import CredentialKey, CredentialStore


# ============================================================================
# 公共数据类型
# ============================================================================


@dataclass(frozen=True)
class UserContext:
    """一次子进程运行期间不可变的用户身份快照。

    注意：
    - `access_token` 是秘密值，`repr=False` 防止默认 print/日志泄密。
    - `user_id`、`username`、`role` 必须来自 login / refresh / users/me 响应。
    - `role` 对 launcher 是不透明字符串，不得用于本地授予权限。
    """

    service_url: str
    user_id: str
    username: str
    role: str
    access_token: str = field(repr=False)


@dataclass(frozen=True)
class AuthSession:
    """launcher 本次运行内存中的可刷新身份。

    `refresh_token` 是秘密值，禁止输出到日志/argv/环境变量。
    `save_login` 控制本次会话是否允许写安全存储；
    若 refresh 成功但新 token 无法写回存储，可降级为 False 并显示警告。
    """

    context: UserContext
    refresh_token: str = field(repr=False)
    save_login: bool = True


# ============================================================================
# SessionService
# ============================================================================


class SessionService(Protocol):
    """会话编排协议。公共契约第 4.4 节定义其语义。"""

    def login(self, *, replace_existing: bool, save_login: bool) -> UserContext:
        """交互式登录。已有身份且 replace_existing=False 时不得静默覆盖。"""
        ...

    def restore(self) -> Optional[UserContext]:
        """后续启动时恢复登录态。无法恢复返回 None。"""
        ...

    def renew(self) -> UserContext:
        """运行中收到 REAUTH_REQUIRED 时由 launcher 调用。

        只使用本次内存 AuthSession.refresh_token；成功后原子替换内存 AuthSession。
        """
        ...

    def logout(self) -> None:
        """先尽力 refresh+logout，再无条件清理本地 refresh token。"""
        ...

    def whoami(self) -> UserProfile:
        """显示当前身份资料，不输出 token。"""
        ...


class SessionServiceImpl:
    """SessionService 的参考实现。

    为了便于后续调试，把所有副作用（auth_client/credential_store/config_store）
    通过构造参数注入，便于单元测试用 mock 替换。
    """

    def __init__(
        self,
        auth_client: AuthClient,
        credential_store: CredentialStore,
        config_store: ConfigStore,
    ) -> None:
        self._auth = auth_client
        self._cred = credential_store
        self._config = config_store
        # 本次 launcher 运行内存中的 AuthSession；登录/恢复成功后才不为 None。
        self._session: Optional[AuthSession] = None
        # CLI 注入的读取用户名/密码回调；默认 None，由 set_credential_input 设置。
        self._read_credentials_callback: Optional[
            Callable[[], tuple[str, str]]
        ] = None

    # ------------------------------------------------------------------
    # 内存 AuthSession 访问
    # ------------------------------------------------------------------

    @property
    def has_session(self) -> bool:
        """launcher 当前内存中是否持有可刷新 AuthSession。

        只有托管模式才允许调用 renew()。
        """
        return self._session is not None

    def current_user_id(self) -> Optional[str]:
        """返回当前内存身份的 user_id，供 CLI 校验与显式 --user-id 是否一致。"""
        if self._session is None:
            return None
        return self._session.context.user_id

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    def login(self, *, replace_existing: bool, save_login: bool) -> UserContext:
        """交互式登录流程。

        流程（设计文档 5.2 节）：
          1. 如果已有身份且不允许替换，抛 UsageError。
          2. 通过 CLI 注入的输入回调读取用户名/密码（关闭回显）。
          3. 调用 AuthClient.login()。
          4. save_login=True 时把 refresh token 写入安全存储。
          5. 更新配置中的 last_user_id / last_username。
          6. 把 AuthSession 保留在内存。
        """

        if self._session is not None and not replace_existing:
            raise errors.UsageError(
                "Already logged in; pass replace_existing=True or logout first."
            )

        # 如果已有旧 session 且要替换，先清理旧 session 的持久化凭据，
        # 避免旧用户的 refresh token 残留。
        if self._session is not None and replace_existing:
            old_key = CredentialKey(
                service_origin=_normalize_origin(self._session.context.service_url),
                user_id=self._session.context.user_id,
            )
            self._safe_delete_credential(old_key)

        # 读取输入；具体由 CLI 层负责关闭回显并注入回调。
        # 这里通过 _read_credentials 抽象，便于测试。
        username, password = self._read_credentials()

        # 读取当前配置以取得 service_url。
        cfg = self._config.load()
        service_url = self._require_service_url(cfg)

        # 调用 IAM 登录；AuthClient 会区分 InvalidCredentials / NetworkUnavailable 等。
        session = self._auth.login(service_url, username, password)

        # 仅在认证成功后才更新配置与安全凭据。
        if save_login:
            self._save_refresh_token(session, service_url)

        # 更新配置中的非敏感元数据，便于下次启动定位。
        self._config.save(
            ClientConfig(
                api_url=cfg.api_url or service_url,
                websocket_url=cfg.websocket_url,
                last_user_id=session.context.user_id,
                last_username=session.context.username,
                allow_insecure_http=cfg.allow_insecure_http,
                gateway_url=cfg.gateway_url,
            )
        )

        # 保留本次内存 AuthSession，供 renew() 使用。
        self._session = AuthSession(
            context=session.context,
            refresh_token=session.refresh_token,
            save_login=save_login,
        )
        return session.context

    # ------------------------------------------------------------------
    # 恢复登录态
    # ------------------------------------------------------------------

    def restore(self) -> Optional[UserContext]:
        """后续启动时尝试恢复登录态。

        只能使用安全存储中的 refresh token 调用 refresh；
        不得使用本地缓存的 user_id 直接恢复身份。
        """

        cfg = self._config.load()
        service_url = self._require_service_url(cfg)

        if not cfg.last_user_id:
            # 没有最近登录的用户元数据，无法定位凭据。
            return None

        key = CredentialKey(
            service_origin=_normalize_origin(service_url),
            user_id=cfg.last_user_id,
        )

        try:
            refresh_token = self._cred.get_refresh_token(key)
        except errors.CredentialStoreUnavailable:
            # 安全存储不可用：无法恢复，由上层进入登录流程。
            return None
        except errors.CredentialCorrupted:
            # 凭据损坏：删除并要求重新登录。
            try:
                self._cred.delete_refresh_token(key)
            except errors.CredentialStoreUnavailable:
                pass
            return None

        if not refresh_token:
            return None

        try:
            session = self._auth.refresh(service_url, refresh_token)
        except errors.AuthenticationExpired:
            # refresh 被拒绝或用户被禁用/删除：删除凭据，进入登录流程。
            self._safe_delete_credential(key)
            return None

        # refresh 成功：替换安全存储中的 refresh token。
        if session.refresh_token != refresh_token:
            try:
                self._cred.set_refresh_token(key, session.refresh_token)
            except errors.CredentialStoreUnavailable:
                # 无法写回存储：本次会话仍可使用内存 token，
                # 但不持久化，下次启动无法恢复。
                pass

        # 更新 last_user_id 以防服务端轮换 user_id（极少见）。
        self._config.save(
            ClientConfig(
                api_url=cfg.api_url or service_url,
                websocket_url=cfg.websocket_url,
                last_user_id=session.context.user_id,
                last_username=session.context.username,
                allow_insecure_http=cfg.allow_insecure_http,
                gateway_url=cfg.gateway_url,
            )
        )

        self._session = AuthSession(
            context=session.context,
            refresh_token=session.refresh_token,
            save_login=True,
        )
        return session.context

    # ------------------------------------------------------------------
    # 运行中重新认证
    # ------------------------------------------------------------------

    def renew(self) -> UserContext:
        """REAUTH_REQUIRED 触发时调用。

        - 只使用本次内存 AuthSession.refresh_token；
        - 成功后原子替换内存中的 AuthSession；
        - 仅在本次登录选择持久化时替换安全存储中的 refresh token；
        - refresh 被拒绝时删除持久化凭据并抛 AuthenticationExpired；
        - 网络暂时失败时保留 refresh token 并抛 NetworkUnavailable。
        """

        if self._session is None:
            raise errors.ReauthenticationUnavailable(
                "No active AuthSession; renew() is only valid in managed mode."
            )

        service_url = self._session.context.service_url
        old_refresh = self._session.refresh_token

        try:
            session = self._auth.refresh(service_url, old_refresh)
        except errors.AuthenticationExpired:
            # refresh 被拒绝：清理持久化凭据并抛错。
            key = CredentialKey(
                service_origin=_normalize_origin(service_url),
                user_id=self._session.context.user_id,
            )
            self._safe_delete_credential(key)
            self._session = None
            raise

        # refresh 成功；原子替换内存 AuthSession。
        save_login = self._session.save_login
        if save_login:
            key = CredentialKey(
                service_origin=_normalize_origin(service_url),
                user_id=session.context.user_id,
            )
            try:
                self._cred.set_refresh_token(key, session.refresh_token)
            except errors.CredentialStoreUnavailable:
                # 写回失败：保留新内存 AuthSession，但本次会话降级为不持久化。
                # 调用方必须显示脱敏的凭据存储警告。
                save_login = False

        self._session = AuthSession(
            context=session.context,
            refresh_token=session.refresh_token,
            save_login=save_login,
        )
        return session.context

    # ------------------------------------------------------------------
    # 登出
    # ------------------------------------------------------------------

    def logout(self) -> None:
        """logout 流程。

        先尽力 refresh 获得短期 access token 并调用服务端 logout，
        再无条件清理本地 refresh token。远端失败时报告但不阻断本地清理。
        """

        cfg = self._config.load()
        service_url = self._require_service_url(cfg)

        # 1. 先尝试用现有 access token 调用 logout。
        # 2. 如果 access token 失效，则尝试 refresh 后再 logout。
        # 3. 远端失败时本地仍要无条件清理。
        remote_ok = True
        if self._session is not None:
            session = self._session
            key = CredentialKey(
                service_origin=_normalize_origin(service_url),
                user_id=session.context.user_id,
            )
            try:
                self._auth.logout(
                    service_url,
                    session.context.access_token,
                    session.refresh_token,
                )
            except errors.AuthenticationExpired:
                # access token 失效：尝试 refresh 后再 logout。
                try:
                    refreshed = self._auth.refresh(service_url, session.refresh_token)
                    self._auth.logout(
                        service_url,
                        refreshed.context.access_token,
                        refreshed.refresh_token,
                    )
                except Exception:
                    remote_ok = False
            except Exception:
                # 网络/服务端错误：远端未确认吊销。
                remote_ok = False

            # 无条件删除本地凭据。
            self._safe_delete_credential(key)
        else:
            # 没有内存 AuthSession：尝试用 last_user_id 定位并删除持久化 refresh token。
            if cfg.last_user_id:
                key = CredentialKey(
                    service_origin=_normalize_origin(service_url),
                    user_id=cfg.last_user_id,
                )
                self._safe_delete_credential(key)

        # 清空内存会话与配置中的元数据。
        self._session = None
        self._config.save(
            ClientConfig(
                api_url=cfg.api_url,
                websocket_url=cfg.websocket_url,
                last_user_id=None,
                last_username=None,
                allow_insecure_http=cfg.allow_insecure_http,
                gateway_url=cfg.gateway_url,
            )
        )

        if not remote_ok:
            # 调用方应根据返回情况显示“本地已退出，远端吊销未确认”。
            raise errors.RemoteServiceError(
                "Local credentials cleared, remote revocation unconfirmed."
            )

    # ------------------------------------------------------------------
    # whoami
    # ------------------------------------------------------------------

    def whoami(self) -> UserProfile:
        """返回当前用户资料。

        必须通过 refresh 后的身份或 users/me 获取，不输出 token。
        """

        if self._session is None:
            # 尝试恢复一次；restore 内部会处理所有失败路径。
            restored = self.restore()
            if restored is None:
                raise errors.AuthenticationExpired(
                    "No active session; please login first."
                )

        if self._session is None:
            raise errors.AuthenticationExpired(
                "No active session; please login first."
            )
        service_url = self._session.context.service_url
        access_token = self._session.context.access_token

        try:
            return self._auth.get_current_user(service_url, access_token)
        except errors.AuthenticationExpired:
            # access token 失效：刷新一次后重试。
            renewed = self.renew()
            return self._auth.get_current_user(service_url, renewed.access_token)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _read_credentials(self) -> tuple[str, str]:
        """读取用户名和密码。

        本实现默认从 CLI 注入的回调读取，便于测试。
        实际由 LauncherCli 在调用 SessionService.login() 前设置回调。
        """
        if self._read_credentials_callback is None:
            raise errors.UsageError(
                "No credential input callback set; CLI must provide one."
            )
        return self._read_credentials_callback()

    def set_credential_input(self, callback: Callable[[], tuple[str, str]]) -> None:
        """由 CLI 调用，注入读取用户名/密码的回调。"""
        self._read_credentials_callback = callback

    @staticmethod
    def _require_service_url(cfg: ClientConfig) -> str:
        if not cfg.api_url:
            raise errors.ConfigError(
                "No service URL configured. Use --api-url or set it in config."
            )
        return cfg.api_url

    def _save_refresh_token(self, session: AuthSession, service_url: str) -> None:
        key = CredentialKey(
            service_origin=_normalize_origin(service_url),
            user_id=session.context.user_id,
        )
        self._cred.set_refresh_token(key, session.refresh_token)

    def _safe_delete_credential(self, key: CredentialKey) -> None:
        """删除持久化凭据；远端/存储失败也不抛错。"""
        try:
            self._cred.delete_refresh_token(key)
        except errors.CredentialStoreUnavailable:
            pass
        except errors.CredentialCorrupted:
            # 已经损坏：尝试删除一次即可。
            try:
                self._cred.delete_refresh_token(key)
            except errors.CredentialStoreUnavailable:
                pass


# ============================================================================
# 辅助函数
# ============================================================================


def _normalize_origin(service_url: str) -> str:
    """规范化服务 origin，作为 CredentialKey 的一部分。

    CredentialKey.service_origin 必须是规范化后的 API origin，
    不得包含查询串、片段、用户名或密码。
    """
    # 简单实现：去掉末尾斜杠、查询串和片段。
    # 完整实现应使用 urllib.parse 解析。
    from urllib.parse import urlsplit

    parts = urlsplit(service_url)
    # 不保留 query / fragment / username / password。
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
