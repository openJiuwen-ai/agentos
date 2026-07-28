"""测试 MemoryCredentialStore 与 CredentialKey 隔离。"""

from agentos_tui_launcher.credential_store import (
    CredentialKey,
    MemoryCredentialStore,
)


class TestCredentialKey:
    @staticmethod
    def test_backend_key_includes_origin_and_user():
        key = CredentialKey(
            service_origin="https://agentos.example.com",
            user_id="user-1",
        )
        backend = key.backend_key()
        assert "agentos.example.com" in backend
        assert "user-1" in backend

    @staticmethod
    def test_different_origins_different_keys():
        k1 = CredentialKey(service_origin="https://a.example.com", user_id="u")
        k2 = CredentialKey(service_origin="https://b.example.com", user_id="u")
        assert k1.backend_key() != k2.backend_key()

    @staticmethod
    def test_different_users_different_keys():
        k1 = CredentialKey(service_origin="https://a.example.com", user_id="u1")
        k2 = CredentialKey(service_origin="https://a.example.com", user_id="u2")
        assert k1.backend_key() != k2.backend_key()


class TestMemoryCredentialStore:
    @staticmethod
    def test_get_missing_returns_none(memory_credential_store):
        key = CredentialKey(service_origin="https://a.example.com", user_id="u")
        assert memory_credential_store.get_refresh_token(key) is None

    @staticmethod
    def test_set_and_get(memory_credential_store):
        key = CredentialKey(service_origin="https://a.example.com", user_id="u")
        memory_credential_store.set_refresh_token(key, "token-1")
        assert memory_credential_store.get_refresh_token(key) == "token-1"

    @staticmethod
    def test_set_overwrites(memory_credential_store):
        key = CredentialKey(service_origin="https://a.example.com", user_id="u")
        memory_credential_store.set_refresh_token(key, "token-1")
        memory_credential_store.set_refresh_token(key, "token-2")
        assert memory_credential_store.get_refresh_token(key) == "token-2"

    @staticmethod
    def test_delete_existing(memory_credential_store):
        key = CredentialKey(service_origin="https://a.example.com", user_id="u")
        memory_credential_store.set_refresh_token(key, "token-1")
        memory_credential_store.delete_refresh_token(key)
        assert memory_credential_store.get_refresh_token(key) is None

    @staticmethod
    def test_delete_missing_is_idempotent(memory_credential_store):
        key = CredentialKey(service_origin="https://a.example.com", user_id="u")
        # 不存在也应该成功。
        memory_credential_store.delete_refresh_token(key)
