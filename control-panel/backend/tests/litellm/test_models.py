"""LitellmModelParams ORM CRUD 测试"""

import pytest

from app.models.litellm_model_params import LitellmModelParams, LocalModelExtension


class TestLitellmModelParams:
    """LitellmModelParams ORM 层 — Upsert / 查询 / 删除 / 唯一性"""

    async def test_upsert_insert(self, db_session):
        """
        场景: 首次 upsert 新 model_id.

        预期: 插入新行, 所有字段正确写入
        """
        row = await LitellmModelParams.upsert(
            db_session, "uuid-123", "deepseek-chat",
            LocalModelExtension(
                instance_url="https://example.com:8000/v1",
                extra_params={"region": "cn-east"},
            ),
        )
        assert row.id == "uuid-123"
        assert row.model_name == "deepseek-chat"
        assert row.instance_url == "https://example.com:8000/v1"
        assert row.extra_params == {"region": "cn-east"}

    async def test_upsert_update(self, db_session):
        """
        场景: 重复 upsert 同一 model_id, 只改 instance_url.

        预期: instance_url 更新为新值
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-123", "deepseek-chat",
            LocalModelExtension(
                instance_url="https://old-url.example.com/v1",
            ),
        )
        row = await LitellmModelParams.upsert(
            db_session, "uuid-123", "deepseek-chat",
            LocalModelExtension(instance_url="https://new-url.example.com/v1"),
        )
        assert row.instance_url == "https://new-url.example.com/v1"

    async def test_get_by_names(self, db_session):
        """
        场景: 批量查询 3 个模型中取 2 个.

        预期: 只返回匹配的记录, 不存在的忽略
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-a", "a",
            LocalModelExtension(),
        )
        await LitellmModelParams.upsert(
            db_session, "uuid-b", "b",
            LocalModelExtension(),
        )
        await LitellmModelParams.upsert(
            db_session, "uuid-c", "c",
            LocalModelExtension(),
        )
        result = await LitellmModelParams.get_by_names(db_session, ["a", "c"])
        assert len(result) == 2
        assert "a" in result
        assert "b" not in result
        # 每个名称对应一个列表
        assert len(result["a"]) == 1
        assert result["a"][0].id == "uuid-a"

    async def test_get_by_names_empty(self, db_session):
        """
        场景: 传入空列表查询.

        预期: 返回空字典
        """
        assert await LitellmModelParams.get_by_names(db_session, []) == {}

    async def test_get_by_names_multiple(self, db_session):
        """
        场景: 同名模型有多条记录.

        预期: get_by_names 返回同一名称下的多条记录
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-1", "same-name",
            LocalModelExtension(),
        )
        await LitellmModelParams.upsert(
            db_session, "uuid-2", "same-name",
            LocalModelExtension(),
        )
        result = await LitellmModelParams.get_by_names(db_session, ["same-name"])
        assert len(result["same-name"]) == 2

    async def test_get_by_id(self, db_session):
        """
        场景: 按 ID 查询.

        预期: 返回对应记录
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-123", "deepseek-chat",
            LocalModelExtension(),
        )
        row = await LitellmModelParams.get_by_id(db_session, "uuid-123")
        assert row is not None
        assert row.model_name == "deepseek-chat"

    async def test_get_by_id_not_found(self, db_session):
        """
        场景: 查询不存在的 ID.

        预期: 返回 None
        """
        row = await LitellmModelParams.get_by_id(db_session, "nonexistent")
        assert row is None

    async def test_get_first_model_name(self, db_session):
        """
        场景: 插入两条记录后获取最早创建的模型名称.

        预期: 返回第一条的 model_name, 空表返回 None
        """
        assert await LitellmModelParams.get_first_model_name(db_session) is None
        await LitellmModelParams.upsert(
            db_session, "uuid-1", "first",
            LocalModelExtension(),
        )
        await LitellmModelParams.upsert(
            db_session, "uuid-2", "second",
            LocalModelExtension(),
        )
        assert await LitellmModelParams.get_first_model_name(db_session) == "first"

    async def test_delete_by_id(self, db_session):
        """
        场景: 先创建再按 ID 删除同一条记录, 然后重复删除.

        预期: 首次删除返回 True, 重复删除返回 False
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-x", "x",
            LocalModelExtension(),
        )
        assert await LitellmModelParams.delete_by_id(db_session, "uuid-x") is True
        assert await LitellmModelParams.delete_by_id(db_session, "uuid-x") is False

    async def test_delete_by_name(self, db_session):
        """
        场景: 按名称删除，同名多条全部删除.

        预期: 返回删除行数
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-1", "same-name",
            LocalModelExtension(),
        )
        await LitellmModelParams.upsert(
            db_session, "uuid-2", "same-name",
            LocalModelExtension(),
        )
        count = await LitellmModelParams.delete_by_name(db_session, "same-name")
        assert count == 2

    async def test_same_name_different_ids(self, db_session):
        """
        场景: 同名模型使用不同 ID.

        预期: 两条记录都存在，可通过不同 ID 查询
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-1", "my-model",
            LocalModelExtension(),
        )
        await LitellmModelParams.upsert(
            db_session, "uuid-2", "my-model",
            LocalModelExtension(),
        )
        row1 = await LitellmModelParams.get_by_id(db_session, "uuid-1")
        row2 = await LitellmModelParams.get_by_id(db_session, "uuid-2")
        assert row1 is not None and row1.model_name == "my-model"
        assert row2 is not None and row2.model_name == "my-model"
        assert row1.id != row2.id
