"""测试 SessionService 的 login/restore/renew/logout/whoami。

使用 fake AuthClient / CredentialStore / ConfigStore 避免真实网络。
"""

from typing import Optional

import pytest

from agentos_tui_launcher import errors
from agentos_tui_launcher.auth_client import UserProfile
from agentos_tui_launcher.config import ClientConfig, FileConfigStore
from agentos_tui_launcher.credential_store import CredentialKey, MemoryCredentialStore
from agentos_tui_launcher.user_context import (
    AuthSession,
    SessionServiceImpl,
    UserContext,
)


# ============================================================================
# Fake 依赖
# ============================================================================


class FakeAuthClient:
    """可控的 AuthClient 实现。"""

    def __init__(self) -> None:
        self.login_result: Optional[AuthSession] = None
        self.refresh_result: Optional[AuthSession] = None
        self.refresh_error: Optional[Exception] = None
        self.logout_called = False
        self.get_user_result: Optional[UserProfile] = None
        self.refresh_call_count = 0

    def login(self, service_url: str, username: str, password: str) -> AuthSession:
        if self.login_result is None:
            raise errors.InvalidCredentials("Invalid credentials.")
        return self.login_result

    def refresh(self, service_url: str, refresh_token: str) -> AuthSession:
        self.refresh_call_count += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        if self.refresh_result is None:
            raise errors.AuthenticationExpired("Refresh rejected.")
        return self.refresh_result

    def logout(self, service_url, access_token, refresh_token) -> None:
        self.logout_called = True

    def get_current_user(self, service_url, access_token) -> UserProfile:
        if self.get_user_result is None:
            raise errors.AuthenticationExpired("Expired.")
        return self.get_user_result


def make_context(user_id="user-1", username="alice", role="user", access_token="access-1") -> UserContext:
    return UserContext(
        service_url="https://agentos.example.com",
        user_id=user_id,
        username=username,
        role=role,
        access_token=access_token,
    )


def make_session(
    user_id="user-1",
    refresh_token="refresh-1",
    access_token="access-1",
) -> AuthSession:
    return AuthSession(
        context=make_context(user_id=user_id, access_token=access_token),
        refresh_token=refresh_token,
        save_login=True,
    )


@pytest.fixture
def fake_auth() -> FakeAuthClient:
    return FakeAuthClient()


@pytest.fixture
def cred_store() -> MemoryCredentialStore:
    return MemoryCredentialStore()


@pytest.fixture
def config_store(temp_config_dir) -> FileConfigStore:
    store = FileConfigStore()
    # 预置 service URL。
    store.save(
        ClientConfig(
            api_url="https://agentos.example.com",
            websocket_url=None,
            last_user_id=None,
            last_username=None,
        )
    )
    return store


@pytest.fixture
def session_service(fake_auth, cred_store, config_store) -> SessionServiceImpl:
    return SessionServiceImpl(
        auth_client=fake_auth,
        credential_store=cred_store,
        config_store=config_store,
    )


def set_login_input(session_service: SessionServiceImpl, username="alice", password="pass") -> None:
    session_service.set_credential_input(lambda: (username, password))


# ============================================================================
# login
# ============================================================================


class TestLogin:
    @staticmethod
    def test_login_success_persists_refresh_token(
        session_service, fake_auth, cred_store, config_store
    ):
        fake_auth.login_result = make_session()
        set_login_input(session_service)

        context = session_service.login(replace_existing=False, save_login=True)

        assert context.user_id == "user-1"
        # refresh token 已写入安全存储。
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        assert cred_store.get_refresh_token(key) == "refresh-1"
        # 配置中的元数据已更新。
        cfg = config_store.load()
        assert cfg.last_user_id == "user-1"
        assert cfg.last_username == "alice"

    @staticmethod
    def test_login_no_save_does_not_persist(
        session_service, fake_auth, cred_store
    ):
        fake_auth.login_result = make_session()
        set_login_input(session_service)

        session_service.login(replace_existing=False, save_login=False)

        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        assert cred_store.get_refresh_token(key) is None
        # 但内存 AuthSession 仍存在。
        assert session_service.has_session

    @staticmethod
    def test_login_rejects_silent_replace(session_service, fake_auth):
        fake_auth.login_result = make_session()
        set_login_input(session_service)
        session_service.login(replace_existing=False, save_login=False)

        # 第二次登录，replace_existing=False 应抛错。
        with pytest.raises(errors.UsageError):
            session_service.login(replace_existing=False, save_login=False)

    @staticmethod
    def test_login_invalid_credentials_raises(session_service, fake_auth):
        fake_auth.login_result = None  # FakeAuthClient.login 会抛 InvalidCredentials
        set_login_input(session_service)
        with pytest.raises(errors.InvalidCredentials):
            session_service.login(replace_existing=False, save_login=True)


# ============================================================================
# restore
# ============================================================================


class TestRestore:
    @staticmethod
    def test_restore_no_last_user_returns_none(session_service, config_store):
        # 配置中没有 last_user_id。
        assert session_service.restore() is None

    @staticmethod
    def test_restore_no_refresh_token_returns_none(
        session_service, config_store, fake_auth
    ):
        # 配置中有 last_user_id，但安全存储中没有 token。
        cfg = config_store.load()
        config_store.save(
            ClientConfig(
                api_url=cfg.api_url,
                websocket_url=cfg.websocket_url,
                last_user_id="user-1",
                last_username="alice",
                allow_insecure_http=cfg.allow_insecure_http,
            )
        )
        assert session_service.restore() is None

    @staticmethod
    def test_restore_success_replaces_refresh_token(
        session_service, config_store, cred_store, fake_auth
    ):
        # 预置 refresh token。
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        cred_store.set_refresh_token(key, "old-refresh")
        cfg = config_store.load()
        config_store.save(
            ClientConfig(
                api_url=cfg.api_url,
                websocket_url=cfg.websocket_url,
                last_user_id="user-1",
                last_username="alice",
                allow_insecure_http=cfg.allow_insecure_http,
            )
        )
        fake_auth.refresh_result = make_session(refresh_token="new-refresh")

        context = session_service.restore()

        assert context is not None
        assert context.user_id == "user-1"
        # refresh token 已被替换。
        assert cred_store.get_refresh_token(key) == "new-refresh"

    @staticmethod
    def test_restore_refresh_rejected_returns_none(
        session_service, config_store, cred_store, fake_auth
    ):
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        cred_store.set_refresh_token(key, "old-refresh")
        cfg = config_store.load()
        config_store.save(
            ClientConfig(
                api_url=cfg.api_url,
                websocket_url=cfg.websocket_url,
                last_user_id="user-1",
                last_username="alice",
                allow_insecure_http=cfg.allow_insecure_http,
            )
        )
        # refresh 被拒绝。
        fake_auth.refresh_error = errors.AuthenticationExpired("rejected")

        # 应删除凭据并返回 None。
        assert session_service.restore() is None
        assert cred_store.get_refresh_token(key) is None


# ============================================================================
# renew
# ============================================================================


class TestRenew:
    @staticmethod
    def test_renew_success_replaces_session(
        session_service, fake_auth, cred_store
    ):
        # 先登录。
        fake_auth.login_result = make_session(
            refresh_token="old-refresh", access_token="old-access"
        )
        set_login_input(session_service)
        session_service.login(replace_existing=False, save_login=True)

        # 然后 renew。
        fake_auth.refresh_result = make_session(
            refresh_token="new-refresh", access_token="new-access"
        )
        new_context = session_service.renew()

        assert new_context.access_token == "new-access"
        # 内存 AuthSession 已替换。
        assert session_service.current_user_id() == "user-1"
        # 安全存储中的 refresh token 已替换。
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        assert cred_store.get_refresh_token(key) == "new-refresh"

    @staticmethod
    def test_renew_without_session_raises(session_service):
        with pytest.raises(errors.ReauthenticationUnavailable):
            session_service.renew()

    @staticmethod
    def test_renew_refresh_rejected_clears_session(
        session_service, fake_auth
    ):
        # 先登录。
        fake_auth.login_result = make_session()
        set_login_input(session_service)
        session_service.login(replace_existing=False, save_login=True)

        # renew 时 refresh 被拒绝。
        fake_auth.refresh_error = errors.AuthenticationExpired("rejected")
        with pytest.raises(errors.AuthenticationExpired):
            session_service.renew()

        # 内存 AuthSession 已清空。
        assert not session_service.has_session


# ============================================================================
# logout
# ============================================================================


class TestLogout:
    @staticmethod
    def test_logout_clears_local_credentials(
        session_service, fake_auth, cred_store, config_store
    ):
        # 先登录。
        fake_auth.login_result = make_session()
        set_login_input(session_service)
        session_service.login(replace_existing=False, save_login=True)

        # 然后 logout。
        session_service.logout()

        # refresh token 已删除。
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        assert cred_store.get_refresh_token(key) is None
        # 配置中的 last_user_id 已清空。
        cfg = config_store.load()
        assert cfg.last_user_id is None
        # 内存 AuthSession 已清空。
        assert not session_service.has_session

    @staticmethod
    def test_logout_remote_failure_still_clears_local(
        session_service, fake_auth, cred_store
    ):
        # 先登录。
        fake_auth.login_result = make_session()
        set_login_input(session_service)
        session_service.login(replace_existing=False, save_login=True)

        # 让 logout 远端失败。
        # FakeAuthClient.logout 不会抛错；模拟抛错的方法是把 logout 替换掉。
        def raise_logout(*args, **kwargs):
            raise errors.NetworkUnavailable("network down")

        fake_auth.logout = raise_logout  # type: ignore[assignment]

        # 公共契约：远端失败时报告"本地已退出，远端吊销未确认"。
        # 实现统一抛 RemoteServiceError，而不是原 NetworkUnavailable。
        with pytest.raises(errors.RemoteServiceError):
            session_service.logout()

        # 本地凭据已清空。
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        assert cred_store.get_refresh_token(key) is None
        assert not session_service.has_session
