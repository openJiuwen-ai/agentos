"""测试 LitellmService 全局注册表 + 生命周期钩子"""

# pylint: disable=protected-access
# 测试代码需要访问 _litellm_svc 以验证全局注册表内部状态

import json
import os
import shutil
import tempfile
import uuid as _uuid
from pathlib import Path

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.litellm_service import LitellmService
from app.services.local_users.backend import LocalUsersBackend


class TestLitellmServiceRegistry:
    """register_litellm_svc / get_litellm_svc — 全局单例注册与获取"""

    @staticmethod
    def test_get_returns_none_before_register():
        """
        场景: 启动前未注册时调用 get_litellm_svc.

        预期: 返回 None，不抛异常
        """
        from app.services import get_litellm_svc, _litellm_svc as _saved

        # 临时置空
        import app.services as _mod
        original = _mod._litellm_svc
        _mod._litellm_svc = None

        try:
            assert get_litellm_svc() is None
        finally:
            _mod._litellm_svc = original

    @staticmethod
    def test_register_then_get():
        """
        场景: 注册一个 LitellmService 后调用 get.

        预期: 返回同一个实例
        """
        from app.services import register_litellm_svc, get_litellm_svc, _litellm_svc as _saved

        import app.services as _mod
        original = _mod._litellm_svc

        svc = MagicMock(spec=LitellmService)
        try:
            register_litellm_svc(svc)
            assert get_litellm_svc() is svc
        finally:
            _mod._litellm_svc = original


class _HookTestBase:
    """生命周期钩子测试基类 — 统一环境配置"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.config import settings
        from app.database import init_engine

        saved_db = settings.AGENTOS_DATABASE_URL
        saved_home = settings.AGENTOS_HOME_BASE
        saved_jwt = settings.AGENTOS_JWT_SECRET_KEY
        saved_admin_user = settings.AGENTOS_ADMIN_USERNAME
        saved_admin_pass = settings.AGENTOS_ADMIN_PASSWORD

        settings.AGENTOS_DATABASE_URL = "sqlite+aiosqlite://"
        settings.AGENTOS_JWT_SECRET_KEY = "test-jwt-secret-key-for-testing"
        settings.AGENTOS_ADMIN_USERNAME = "admin"
        settings.AGENTOS_ADMIN_PASSWORD = json.loads(
            (Path(__file__).resolve().parent.parent / "test_data.json").read_text("utf-8")
        )["admin"]["password"]
        tmpdir = tempfile.mkdtemp(prefix="agentos_test_")
        settings.AGENTOS_HOME_BASE = tmpdir

        init_engine()

        yield

        # 清理共享引擎
        import app.database as _db
        if _db.engine is not None:
            import asyncio
            asyncio.run(_db.engine.dispose())
            _db.engine = None
            _db.async_session_maker = None

        settings.AGENTOS_DATABASE_URL = saved_db
        settings.AGENTOS_HOME_BASE = saved_home
        settings.AGENTOS_JWT_SECRET_KEY = saved_jwt
        settings.AGENTOS_ADMIN_USERNAME = saved_admin_user
        settings.AGENTOS_ADMIN_PASSWORD = saved_admin_pass
        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.fixture
    def backend(self):
        return LocalUsersBackend()


class TestCreateUserHook(_HookTestBase):
    """LocalUsersBackend.create_user — LiteLLM 同步钩子"""

    async def test_hook_skipped_when_svc_not_registered(self, backend):
        """
        场景: LitellmService 未注册时创建用户.

        预期: 用户正常创建，LiteLLM 同步跳过不报错
        """
        import app.services as _mod

        original = _mod._litellm_svc
        _mod._litellm_svc = None

        try:
            await backend.on_startup()
            await backend.seed_initial_admin()

            record, pwd = await backend.create_user("testuser1", "TestPass123")
            assert record.username == "testuser1"
        finally:
            _mod._litellm_svc = original
            await backend.on_shutdown()

    async def test_hook_calls_create_user_when_registered(self, backend):
        """
        场景: LitellmService 已注册时创建用户.

        预期: svc.create_user 被调用，参数 uid 为面板用户的 UUID 字符串
        """
        import app.services as _mod

        original = _mod._litellm_svc
        mock_svc = AsyncMock(spec=LitellmService)
        _mod._litellm_svc = mock_svc

        try:
            await backend.on_startup()
            record, pwd = await backend.create_user("testuser2", "TestPass123")

            mock_svc.create_user.assert_called_once()
            call_uid = mock_svc.create_user.call_args.kwargs["uid"]
            assert call_uid == record.user_id
        finally:
            _mod._litellm_svc = original
            await backend.on_shutdown()

    async def test_hook_does_not_block_on_failure(self, backend):
        """
        场景: LiteLLM 同步失败时.

        预期: 面板用户仍创建成功，异常被吞下不传播
        """
        import app.services as _mod

        original = _mod._litellm_svc
        mock_svc = AsyncMock(spec=LitellmService)
        mock_svc.create_user.side_effect = RuntimeError("LiteLLM down")
        _mod._litellm_svc = mock_svc

        try:
            await backend.on_startup()
            record, pwd = await backend.create_user("testuser3", "TestPass123")
            assert record.username == "testuser3"
            mock_svc.create_user.assert_called_once()
        finally:
            _mod._litellm_svc = original
            await backend.on_shutdown()


class TestDeleteUserHook(_HookTestBase):
    """LocalUsersBackend.delete_user — LiteLLM 清理钩子"""

    async def test_hook_skipped_when_svc_not_registered(self, backend):
        """
        场景: LitellmService 未注册时删除用户.

        预期: 用户正常删除，不报错
        """
        import app.services as _mod

        original = _mod._litellm_svc
        _mod._litellm_svc = None

        try:
            await backend.on_startup()
            record, _ = await backend.create_user("deluser1", "TestPass123")
            uid = _uuid.UUID(record.user_id)
            await backend.delete_user(uid)
            assert await backend.get_user_by_id(uid) is None
        finally:
            _mod._litellm_svc = original
            await backend.on_shutdown()

    async def test_hook_calls_delete_user_when_registered(self, backend):
        """
        场景: LitellmService 已注册时删除用户.

        预期: svc.delete_user 被调用，参数包含 session 和 uid
        """
        import app.services as _mod

        original = _mod._litellm_svc
        mock_svc = AsyncMock(spec=LitellmService)
        _mod._litellm_svc = mock_svc

        try:
            await backend.on_startup()
            record, _ = await backend.create_user("deluser2", "TestPass123")

            mock_svc.delete_user.reset_mock()
            await backend.delete_user(_uuid.UUID(record.user_id))

            mock_svc.delete_user.assert_called_once()
            call_uid = mock_svc.delete_user.call_args.kwargs["uid"]
            assert call_uid == str(record.user_id)
        finally:
            _mod._litellm_svc = original
            await backend.on_shutdown()

    async def test_hook_does_not_block_on_failure(self, backend):
        """
        场景: LiteLLM 清理失败时.

        预期: 面板用户仍删除成功，异常被吞下
        """
        import app.services as _mod

        original = _mod._litellm_svc
        mock_svc = AsyncMock(spec=LitellmService)
        mock_svc.delete_user.side_effect = RuntimeError("LiteLLM down")
        _mod._litellm_svc = mock_svc

        try:
            await backend.on_startup()
            record, _ = await backend.create_user("deluser3", "TestPass123")

            uid = _uuid.UUID(record.user_id)
            await backend.delete_user(uid)
            assert await backend.get_user_by_id(uid) is None
            mock_svc.delete_user.assert_called_once()
        finally:
            _mod._litellm_svc = original
            await backend.on_shutdown()
