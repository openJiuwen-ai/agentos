"""测试 LauncherArgvAdapter 的参数解析与构造。"""

import pytest

from agentos_tui_launcher import errors
from agentos_tui_launcher.argv_adapter import LauncherArgvAdapterImpl
from agentos_tui_launcher.protocol import LaunchMode
from agentos_tui_launcher.user_context import UserContext


@pytest.fixture
def adapter() -> LauncherArgvAdapterImpl:
    return LauncherArgvAdapterImpl()


@pytest.fixture
def context() -> UserContext:
    return UserContext(
        service_url="https://agentos.example.com",
        user_id="user-123",
        username="alice",
        role="user",
        access_token="access-token-secret",
    )


# ============================================================================
# analyze()
# ============================================================================


class TestAnalyze:
    @staticmethod
    def test_empty_argv(adapter):
        result = adapter.analyze(())
        assert result.user_id is None
        assert result.has_access_token is False

    @staticmethod
    def test_user_id_space_separated(adapter):
        result = adapter.analyze(("--user-id", "abc"))
        assert result.user_id == "abc"

    @staticmethod
    def test_user_id_equal_separated(adapter):
        result = adapter.analyze(("--user-id=abc",))
        assert result.user_id == "abc"

    @staticmethod
    def test_token_space_separated(adapter):
        result = adapter.analyze(("--token", "secret"))
        assert result.has_access_token is True

    @staticmethod
    def test_token_equal_separated(adapter):
        result = adapter.analyze(("--token=secret",))
        assert result.has_access_token is True

    @staticmethod
    def test_unknown_args_preserved(adapter):
        result = adapter.analyze(("--url", "ws://localhost", "--session", "s1"))
        assert result.user_id is None
        assert result.has_access_token is False

    @staticmethod
    def test_user_id_missing_value(adapter):
        with pytest.raises(errors.UsageError):
            adapter.analyze(("--user-id",))

    @staticmethod
    def test_user_id_empty_value_space(adapter):
        with pytest.raises(errors.UsageError):
            adapter.analyze(("--user-id", ""))

    @staticmethod
    def test_user_id_empty_value_equal(adapter):
        with pytest.raises(errors.UsageError):
            adapter.analyze(("--user-id=",))

    @staticmethod
    def test_user_id_duplicate_space(adapter):
        with pytest.raises(errors.UsageError):
            adapter.analyze(("--user-id", "a", "--user-id", "b"))

    @staticmethod
    def test_user_id_duplicate_mixed(adapter):
        with pytest.raises(errors.UsageError):
            adapter.analyze(("--user-id", "a", "--user-id=b"))

    @staticmethod
    def test_token_missing_value(adapter):
        with pytest.raises(errors.UsageError):
            adapter.analyze(("--token",))


# ============================================================================
# build_primary_argv()
# ============================================================================


class TestBuildExplicitMode:
    @staticmethod
    def test_explicit_mode_preserves_user_id(adapter):
        argv = ("--url", "ws://localhost", "--user-id", "abc", "--token", "secret")
        result = adapter.build_primary_argv(argv, LaunchMode.EXPLICIT, None)
        assert "--user-id" in result
        assert "abc" in result
        assert "--token" in result

    @staticmethod
    def test_explicit_mode_rejects_context(adapter, context):
        with pytest.raises(errors.UsageError):
            adapter.build_primary_argv((), LaunchMode.EXPLICIT, context)


class TestBuildManagedMode:
    @staticmethod
    def test_managed_injects_identity(adapter, context):
        argv = ("--url", "ws://localhost")
        result = adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)
        assert "--user-id" in result
        assert "alice" in result
        assert "--token" in result
        # 原始参数仍存在。
        assert "--url" in result
        assert "ws://localhost" in result

    @staticmethod
    def test_managed_requires_context(adapter):
        with pytest.raises(errors.UsageError):
            adapter.build_primary_argv((), LaunchMode.MANAGED, None)

    @staticmethod
    def test_managed_rejects_explicit_user_id_mismatch(adapter, context):
        argv = ("--user-id", "different-id",)
        with pytest.raises(errors.UsageError):
            adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)

    @staticmethod
    def test_managed_rejects_explicit_user_id_same(adapter, context):
        # 即使一致也不允许；要求用户去掉冲突参数。
        argv = ("--user-id", context.user_id)
        with pytest.raises(errors.UsageError):
            adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)

    @staticmethod
    def test_managed_rejects_explicit_token(adapter, context):
        argv = ("--token", "explicit-token",)
        with pytest.raises(errors.UsageError):
            adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)


class TestBuildFiltering:
    @staticmethod
    def test_launcher_args_filtered(adapter, context):
        argv = ("--api-url", "https://api.example.com", "--no-save-login", "--url", "ws://localhost")
        result = adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)
        # launcher 自有参数不传递给 JiuwenSwarm。
        assert "--api-url" not in result
        assert "https://api.example.com" not in result
        assert "--no-save-login" not in result
        # 但 TUI 参数保留。
        assert "--url" in result
        assert "ws://localhost" in result

    @staticmethod
    def test_separator_removed(adapter, context):
        argv = ("--", "--url", "ws://localhost")
        result = adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)
        assert "--" not in result
        assert "--url" in result

    @staticmethod
    def test_api_url_equal_form_filtered(adapter, context):
        argv = ("--api-url=https://api.example.com", "--url", "ws://localhost")
        result = adapter.build_primary_argv(argv, LaunchMode.MANAGED, context)
        assert "--api-url=https://api.example.com" not in result
        assert "--url" in result
