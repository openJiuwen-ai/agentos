"""测试 LitellmService 用户管理方法 (create_user / delete_user)"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.litellm_service import (
    LitellmService, LitellmUpstreamError, LitellmConnectionError,
    KeyNotFoundError, CreateUserExtras, encrypt_key,
)
from app.models.litellm_user_key import LitellmUserKey, CreateKeyExtras


class TestCreateUserMethod:
    """create_user 方法测试"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_create_user_basic(self, svc):
        """
        场景: 传入基本 uid, mock LiteLLM 返回创建成功.

        预期: 返回 {"ok": True, "user_id": "newuser"}
        """
        mock_response = {"user_id": "newuser", "created": True}

        with patch.object(svc, "request", new=AsyncMock(return_value=mock_response)):
            result = await svc.create_user(uid="newuser")

        assert result == {"ok": True, "user_id": "newuser"}

    async def test_create_user_with_all_limits(self, svc):
        """
        场景: 创建用户时透传 rpm/tpm/并行限制参数.

        预期: LiteLLM 请求的 json_data 中包含所有限制参数, 值正确
        """
        mock_response = {"user_id": "user003"}

        with patch.object(svc, "request") as mock_req:
            mock_req.return_value = mock_response
            await svc.create_user(
                uid="user003",
                extras=CreateUserExtras(
                    auto_create_key=False,
                    rpm_limit=60,
                    max_parallel_requests=5,
                    tpm_limit=50000,
                ),
            )

            json_data = mock_req.call_args.kwargs["json_data"]
            assert json_data["auto_create_key"] is False
            assert json_data["rpm_limit"] == 60
            assert json_data["max_parallel_requests"] == 5
            assert json_data["tpm_limit"] == 50000

    async def test_create_user_upstream_error(self, svc):
        """
        场景: mock LiteLLM 返回 400 错误.

        预期: 抛出 LitellmUpstreamError
        """
        with patch.object(
            svc, "request",
            new=AsyncMock(side_effect=LitellmUpstreamError(400, "Bad Request")),
        ):
            with pytest.raises(LitellmUpstreamError):
                await svc.create_user(uid="baduser")


    async def test_create_user_defaults(self, svc):
        """
        场景: 不传 extras, 使用默认值.

        预期: body 中 auto_create_key=False, 无 rpm/tpm 限制
        """
        mock_response = {"user_id": "newuser"}
        with patch.object(svc, "request") as mock_req:
            mock_req.return_value = mock_response
            result = await svc.create_user(uid="newuser")
        assert result == {"ok": True, "user_id": "newuser"}
        json_data = mock_req.call_args.kwargs["json_data"]
        assert json_data["auto_create_key"] is False
        assert "rpm_limit" not in json_data

    async def test_create_user_connection_error(self, svc):
        """
        场景: LiteLLM 不可达时创建用户.

        预期: 抛出 LitellmConnectionError
        """
        with patch.object(
            svc, "request",
            new=AsyncMock(side_effect=LitellmConnectionError("timeout")),
        ):
            with pytest.raises(LitellmConnectionError):
                await svc.create_user(uid="newuser")


class TestDeleteUserMethod:
    """delete_user 方法测试"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_delete_user_clears_keys(self, svc, db_session):
        """
        场景: 删除有 2 个 Key 的用户, 同时存在另一用户的其他 Key.

        预期: 被删用户的 Key 全部清除, 另一用户不受影响
        """

        await LitellmUserKey.create(
            db_session, "userToDelete", "key1", encrypt_key("pk1"),
            extras=CreateKeyExtras(key_name="key-1"))
        await LitellmUserKey.create(
            db_session, "userToDelete", "key2", encrypt_key("pk2"),
            extras=CreateKeyExtras(key_name="key-2"))
        await LitellmUserKey.create(
            db_session, "otherUser", "key3", encrypt_key("pk3"),
            extras=CreateKeyExtras(key_name="key-3"))

        assert await LitellmUserKey.count_by_uid(db_session, "userToDelete") == 2

        mock_response = {"deleted": True}
        with patch.object(svc, "request", new=AsyncMock(return_value=mock_response)):
            result = await svc.delete_user(db_session, uid="userToDelete")

        assert result == {"ok": True}
        assert await LitellmUserKey.count_by_uid(db_session, "userToDelete") == 0
        assert await LitellmUserKey.count_by_uid(db_session, "otherUser") == 1

    async def test_delete_user_404_clears_keys(self, svc, db_session):
        """
        场景: LiteLLM 返回 404 (用户不存在), 但本地仍有该用户的 Key 映射.

        预期: 返回 ok, 本地 Key 仍被清除 (幂等处理)
        """
        await LitellmUserKey.create(
            db_session, "ghost", "k1", encrypt_key("pk1"),
            extras=CreateKeyExtras(key_name="ghost-key"))

        async def mock_404(*args, **kwargs):
            raise LitellmUpstreamError(404, "Not Found")

        with patch.object(svc, "request", new=mock_404):
            result = await svc.delete_user(db_session, uid="ghost")

        assert result == {"ok": True}
        assert await LitellmUserKey.count_by_uid(db_session, "ghost") == 0

    async def test_delete_user_no_keys(self, svc, db_session):
        """
        场景: 用户没有 Key 映射时删除.

        预期: 返回 ok, 不报错
        """
        mock_response = {"deleted": True}
        with patch.object(svc, "request", new=AsyncMock(return_value=mock_response)):
            result = await svc.delete_user(db_session, uid="emptyuser")
        assert result == {"ok": True}

    async def test_delete_user_upstream_error_not_404(self, svc, db_session):
        """
        场景: LiteLLM 返回 500 错误 (非 404).

        预期: 抛出 LitellmUpstreamError, 本地 Key 不被清除
        """
        await LitellmUserKey.create(
            db_session, "user1", "k1", encrypt_key("pk1"),
            extras=CreateKeyExtras(key_name="user1-key"))

        with patch.object(
            svc, "request",
            new=AsyncMock(side_effect=LitellmUpstreamError(500, "Server Error")),
        ):
            with pytest.raises(LitellmUpstreamError):
                await svc.delete_user(db_session, uid="user1")

        assert await LitellmUserKey.count_by_uid(db_session, "user1") == 1


class TestDeleteKeyMethod:
    """delete_key 方法测试 — 覆盖 decrypt_key + LiteLLM /key/delete 真实调用链"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_delete_key_success(self, svc, db_session):
        """
        场景: 创建加密 Key 记录后通过 delete_key 删除.

        预期: LiteLLM 收到原始 Key 字符串(解密后), 本地记录被删除
        """

        encrypted = encrypt_key("sk-raw-key-for-delete-test")
        await LitellmUserKey.create(
            db_session, "user-del", "alias-del", encrypted,
            extras=CreateKeyExtras(key_name="test-key"),
        )
        assert await LitellmUserKey.count_by_uid(db_session, "user-del") == 1

        mock_response = {"deleted_keys": ["sk-raw-key-for-delete-test"]}
        mock_req = AsyncMock(return_value=mock_response)
        with patch.object(svc, "request", new=mock_req):
            result = await svc.delete_key(db_session, "user-del", "alias-del")

        assert result == {"ok": True}
        assert await LitellmUserKey.count_by_uid(db_session, "user-del") == 0

        # 验证 LiteLLM 收到的是解密后的原始 Key
        body = mock_req.call_args.kwargs["json_data"]
        assert body["keys"] == ["sk-raw-key-for-delete-test"]

    async def test_delete_key_not_found(self, svc, db_session):
        """
        场景: key_alias 不存在.

        预期: 抛出 KeyNotFoundError
        """
        with pytest.raises(KeyNotFoundError):
            await svc.delete_key(db_session, "anyone", "no-such-alias")

    async def test_delete_key_wrong_owner(self, svc, db_session):
        """
        场景: key_alias 存在但 uid 不匹配.

        预期: 抛出 KeyNotFoundError (统一 404 防泄漏)
        """

        await LitellmUserKey.create(
            db_session, "alice", "my-key", encrypt_key("sk-alice"),
            extras=CreateKeyExtras(key_name="alice-key"),
        )
        with pytest.raises(KeyNotFoundError):
            await svc.delete_key(db_session, "bob", "my-key")

    async def test_delete_key_404_idempotent(self, svc, db_session):
        """
        场景: LiteLLM 返回 404, 本地仍有记录.

        预期: 返回 ok, 本地记录被清除
        """

        encrypted = encrypt_key("sk-ghost-key")
        await LitellmUserKey.create(
            db_session, "ghost", "ghost-alias", encrypted,
            extras=CreateKeyExtras(key_name="ghost-alias-key"),
        )

        with patch.object(
            svc, "request",
            new=AsyncMock(side_effect=LitellmUpstreamError(404, "Not Found")),
        ):
            result = await svc.delete_key(db_session, "ghost", "ghost-alias")

        assert result == {"ok": True}
        assert await LitellmUserKey.count_by_uid(db_session, "ghost") == 0
