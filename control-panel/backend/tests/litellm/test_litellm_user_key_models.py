"""LitellmUserKey ORM CRUD 测试"""

import pytest

from app.models.litellm_user_key import LitellmUserKey, CreateKeyExtras
from app.services.litellm_service import encrypt_key, decrypt_key


class TestLitellmUserKeyCreate:
    """LitellmUserKey.create — 写入 Key 映射"""

    async def test_create_success(self, db_session):
        """
        场景: 创建一条 Key 映射记录.

        预期: 写入成功, 各字段与入参一致
        """
        encrypted = encrypt_key("sk-test-key-abc123")
        record = await LitellmUserKey.create(
            db_session, "user-1", "sk-alias-1", encrypted,
            extras=CreateKeyExtras(model="deepseek", key_name="key-1"),
        )
        assert record.uid == "user-1"
        assert record.key_alias == "sk-alias-1"
        assert record.bound_model == "deepseek"
        assert record.key == encrypted
        # 解密验证
        assert decrypt_key(record.key) == "sk-test-key-abc123"

    async def test_create_without_model(self, db_session):
        """
        场景: 不绑定模型 (model=None).

        预期: bound_model 为 None
        """
        encrypted = encrypt_key("sk-no-model")
        record = await LitellmUserKey.create(
            db_session, "user-2", "sk-alias-2", encrypted,
            extras=CreateKeyExtras(key_name="key-2"),
        )
        assert record.bound_model is None


class TestLitellmUserKeyQuery:
    """LitellmUserKey 查询方法"""

    async def test_count_by_uid(self, db_session):
        """
        场景: 为用户创建 3 个 Key, 另外用户创建 2 个 Key.

        预期: count 返回正确的数量, 不混入其他用户
        """
        for i in range(3):
            await LitellmUserKey.create(
                db_session, "alice", f"ak{i}", encrypt_key(f"pk{i}"),
                extras=CreateKeyExtras(key_name=f"ak-name-{i}"),
            )
        for i in range(2):
            await LitellmUserKey.create(
                db_session, "bob", f"bk{i}", encrypt_key(f"pk{i}"),
                extras=CreateKeyExtras(key_name=f"bk-name-{i}"),
            )
        assert await LitellmUserKey.count_by_uid(db_session, "alice") == 3
        assert await LitellmUserKey.count_by_uid(db_session, "bob") == 2
        assert await LitellmUserKey.count_by_uid(db_session, "nobody") == 0

    async def test_list_by_uid(self, db_session):
        """
        场景: 查询用户的 Key 列表.

        预期: 按 created_at DESC 排序
        """
        for i in [1, 2, 3]:
            await LitellmUserKey.create(
                db_session, "alice", f"k{i}", encrypt_key(f"pk{i}"),
                extras=CreateKeyExtras(key_name=f"k-name-{i}"),
            )
        records = await LitellmUserKey.list_by_uid(db_session, "alice")
        assert len(records) == 3
        assert records[0].key_alias == "k3"  # DESC order, newest first

    async def test_get_by_alias(self, db_session):
        """
        场景: 按 key_alias 查询.

        预期: 返回匹配的记录, 不匹配返回 None
        """
        await LitellmUserKey.create(
            db_session, "alice", "my-key", encrypt_key("pk"),
            extras=CreateKeyExtras(key_name="my-key-name"),
        )
        found = await LitellmUserKey.get_by_alias(db_session, "my-key")
        assert found is not None
        assert found.uid == "alice"

        not_found = await LitellmUserKey.get_by_alias(db_session, "nope")
        assert not_found is None

    async def test_get_by_uid_and_alias(self, db_session):
        """
        场景: 同时按 uid 和 key_alias 精准查询.

        预期: uid 和 alias 双匹配时返回记录, 单匹配不返回
        """
        await LitellmUserKey.create(
            db_session, "alice", "shared-key", encrypt_key("pk-a"),
            extras=CreateKeyExtras(key_name="shared-key-name-a"),
        )
        await LitellmUserKey.create(
            db_session, "bob", "shared-key", encrypt_key("pk-b"),
            extras=CreateKeyExtras(key_name="shared-key-name-b"),
        )

        alice_key = await LitellmUserKey.get_by_uid_and_alias(
            db_session, "alice", "shared-key",
        )
        assert alice_key is not None
        assert alice_key.uid == "alice"

        bob_key = await LitellmUserKey.get_by_uid_and_alias(
            db_session, "bob", "shared-key",
        )
        assert bob_key is not None
        assert bob_key.uid == "bob"

    async def test_exists_by_uid(self, db_session):
        """
        场景: 检查用户是否存在 Key 记录.

        预期: 有记录返回 True, 无记录返回 False
        """
        assert await LitellmUserKey.exists_by_uid(db_session, "nobody") is False
        await LitellmUserKey.create(
            db_session, "alice", "k1", encrypt_key("pk"),
            extras=CreateKeyExtras(key_name="k1-name"),
        )
        assert await LitellmUserKey.exists_by_uid(db_session, "alice") is True


class TestLitellmUserKeyDelete:
    """LitellmUserKey 删除方法"""

    async def test_delete_by_uid(self, db_session):
        """
        场景: 删除用户的所有 Key.

        预期: 返回删除行数, 该用户 Key 被清空, 其他用户不受影响
        """
        for i in range(2):
            await LitellmUserKey.create(
                db_session, "alice", f"ak{i}", encrypt_key(f"pk{i}"),
                extras=CreateKeyExtras(key_name=f"del-ak-name-{i}"),
            )
        await LitellmUserKey.create(
            db_session, "bob", "bk0", encrypt_key("pk"),
            extras=CreateKeyExtras(key_name="del-bk-name-0"),
        )

        deleted = await LitellmUserKey.delete_by_uid(db_session, "alice")
        assert deleted == 2
        assert await LitellmUserKey.count_by_uid(db_session, "alice") == 0
        assert await LitellmUserKey.count_by_uid(db_session, "bob") == 1

    async def test_delete_nonexistent_uid(self, db_session):
        """
        场景: 删除不存在的用户.

        预期: 返回 0, 不报错
        """
        deleted = await LitellmUserKey.delete_by_uid(db_session, "nobody")
        assert deleted == 0

    async def test_delete_by_uid_and_alias(self, db_session):
        """
        场景: 删除指定用户的指定 Key.

        预期: 返回 True, 仅删除匹配的记录
        """
        await LitellmUserKey.create(
            db_session, "alice", "k1", encrypt_key("pk1"),
            extras=CreateKeyExtras(key_name="del-k1-name"),
        )
        await LitellmUserKey.create(
            db_session, "alice", "k2", encrypt_key("pk2"),
            extras=CreateKeyExtras(key_name="del-k2-name"),
        )

        result = await LitellmUserKey.delete_by_uid_and_alias(
            db_session, "alice", "k1",
        )
        assert result is True
        assert await LitellmUserKey.count_by_uid(db_session, "alice") == 1

    async def test_delete_by_uid_and_alias_not_found(self, db_session):
        """
        场景: 删除不存在的 Key.

        预期: 返回 False, 不报错
        """
        result = await LitellmUserKey.delete_by_uid_and_alias(
            db_session, "alice", "nope",
        )
        assert result is False


class TestLitellmUserKeyUnique:
    """litellm_user_key 唯一约束"""

    async def test_unique_uid_alias(self, db_session):
        """
        场景: 同一 uid 下创建重复的 key_alias.

        预期: 抛出 IntegrityError
        """
        from sqlalchemy.exc import IntegrityError
        await LitellmUserKey.create(
            db_session, "alice", "dup-key", encrypt_key("pk1"),
            extras=CreateKeyExtras(key_name="dup-name-1"),
        )
        with pytest.raises(IntegrityError):
            await LitellmUserKey.create(
                db_session, "alice", "dup-key", encrypt_key("pk2"),
                extras=CreateKeyExtras(key_name="dup-name-2"),
            )
            await db_session.flush()

    async def test_same_alias_different_uid_allowed(self, db_session):
        """
        场景: 不同 uid 下可以使用相同的 key_alias.

        预期: 两个记录都创建成功
        """
        await LitellmUserKey.create(
            db_session, "alice", "shared-alias", encrypt_key("pk-a"),
            extras=CreateKeyExtras(key_name="shared-alias-name-a"),
        )
        await LitellmUserKey.create(
            db_session, "bob", "shared-alias", encrypt_key("pk-b"),
            extras=CreateKeyExtras(key_name="shared-alias-name-b"),
        )
        assert await LitellmUserKey.count_by_uid(db_session, "alice") == 1
        assert await LitellmUserKey.count_by_uid(db_session, "bob") == 1
