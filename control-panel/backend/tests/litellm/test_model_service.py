"""LitellmService 模型管理方法测试 — mock httpx"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.litellm_service import (
    CreateModelExtras,
    LitellmService,
    LitellmConnectionError,
    LitellmUpstreamError,
    LitellmServiceError,
    _fetch_model_detail,
)
from app.models.litellm_model_params import LitellmModelParams, LocalModelExtension


class TestExceptions:
    """异常类构造与属性"""

    @staticmethod
    def test_upstream_error():
        """
        场景: 构造 LitellmUpstreamError(500, 'Err').

        预期: status_code=500, detail='Err'
        """
        e = LitellmUpstreamError(500, "Err")
        assert e.status_code == 500

    @staticmethod
    def test_connection_error():
        """
        场景: 构造 LitellmConnectionError('timeout').

        预期: 消息字符串包含 'timeout'
        """
        assert "timeout" in str(LitellmConnectionError("timeout"))


class TestListModels:
    """list_models — 合并 LiteLLM + 本地扩展字段"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_basic(self, svc, db_session):
        """
        场景: LiteLLM 返回 2 个模型, 本地有 1 个的扩展字段.

        预期: 合并后 total=2, 本地记录 instance_url 正确注入
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-1", "deepseek-chat",
            LocalModelExtension(
                instance_url="https://example.com:8000/v1",
            ),
        )
        llm = {
            "data": [
                {"model_name": "deepseek-chat", "litellm_params": {"model": "ds"},
                 "model_info": {}},
                {"model_name": "gpt-4o", "litellm_params": {"model": "gpt"},
                 "model_info": {}},
            ]
        }
        call_count = [0]

        async def mock_req(method, path, **kw):
            call_count[0] += 1
            return llm if call_count[0] == 1 else {}

        with patch.object(svc, "request", new=mock_req):
            result = await svc.list_models(db_session)
        assert result["total"] == 2
        ds = next(i for i in result["items"] if i["model_name"] == "deepseek-chat")
        assert ds["instance_url"] == "https://example.com:8000/v1"

    async def test_pagination(self, svc, db_session):
        """
        场景: 25 条模型数据, 分页 10 条/页.

        预期: 第 1 页 10 条, 第 3 页 5 条, total=25
        """
        models = {"data": [{"model_name": f"m-{i}"} for i in range(25)]}
        with patch.object(svc, "request", new=AsyncMock(return_value=models)):
            r1 = await svc.list_models(db_session, page=1, page_size=10)
            assert r1["total"] == 25 and len(r1["items"]) == 10
            r3 = await svc.list_models(db_session, page=3, page_size=10)
            assert len(r3["items"]) == 5

    async def test_skips_empty_ids(self, svc, db_session):
        """
        场景: LiteLLM 返回含无 model_name 项的模型列表.

        预期: 只统计有 model_name 的有效条目
        """
        models = {"data": [
            {"model_name": "valid"}, {}, {"model_name": "also-valid"}, {},
        ]}
        with patch.object(svc, "request", new=AsyncMock(return_value=models)):
            result = await svc.list_models(db_session)
        assert result["total"] == 2

    async def test_name_filter(self, svc, db_session):
        """
        场景: 通过 model_name 过滤，同名返回多条.

        预期: 只返回名称匹配的模型
        """
        models = {"data": [
            {"model_name": "gpt-4o", "litellm_params": {}, "model_info": {}},
            {"model_name": "deepseek-chat", "litellm_params": {}, "model_info": {}},
        ]}
        with patch.object(svc, "request", new=AsyncMock(return_value=models)):
            result = await svc.list_models(
                db_session, model_name="gpt-4o",
            )
        assert result["total"] == 1
        assert result["items"][0]["model_name"] == "gpt-4o"


class TestFetchModelDetail:
    """_fetch_model_detail — 合并 LiteLLM 信息与本地扩展字段"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_with_local(self, svc):
        """
        场景: 本地有记录.

        预期: 合并 litellm_params 和 model_info, instance_url 来自本地
        """
        m = {"model_name": "gpt-4o", "litellm_params": {"model": "gpt"},
             "model_info": {"id": "hash-123"}}
        local = MagicMock()
        local.model_name = "gpt-4o"
        local.instance_url = "https://x.example.com/v1"
        local.max_concurrent = None
        local.inference_engine = "vLLM"
        local.extra_params = {"grafana_job_name": "vllm-x.example.com:443"}
        local.created_at = None
        local.updated_at = None
        r = _fetch_model_detail(svc, m, local)
        assert r["litellm_params"] == {"model": "gpt"}
        assert r["model_info"] == {"id": "hash-123"}
        assert r["id"] == "hash-123"
        assert r["instance_url"] == "https://x.example.com/v1"
        assert r["grafana_job_name"] == "vllm-x.example.com:443"

    async def test_empty_model_name(self, svc):
        """
        场景: 模型字典无 model_name 也无 id.

        预期: 返回 None
        """
        assert _fetch_model_detail(svc, {"no": "name"}, None) is None

    async def test_without_local(self, svc):
        """
        场景: 本地无记录.

        预期: 使用 LiteLLM 返回的 model_name
        """
        m = {"model_name": "gpt-4o", "litellm_params": {"m": "fb"},
             "model_info": {"f": "l"}}
        r = _fetch_model_detail(svc, m, None)
        assert r["litellm_params"] == {"m": "fb"}
        assert r["instance_url"] is None


class TestCreateModel:
    """create_model — 创建 + 回滚"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_success(self, svc, db_session):
        """
        场景: LiteLLM 返回 model_id, 本地写入 instance_url.

        预期: model_id 正确, 本地记录可查询
        """
        with (
            patch.object(
                svc, "request",
                new=AsyncMock(return_value={
                    "model_name": "ds", "model_info": {"id": "uuid-new"},
                }),
            ),
            patch(
                "app.services.litellm_service._sync_metrics_on_create",
                new=AsyncMock(return_value=None),
            ),
        ):
            r = await svc.create_model(
                db_session, model_name="ds",
                litellm_params={"model": "openai/ds", "api_key": "sk"},
                extras=CreateModelExtras(instance_url="https://x.example.com/v1"),
            )
        assert r["id"] == "uuid-new"
        local = await LitellmModelParams.get_by_id(db_session, "uuid-new")
        assert local is not None
        assert local.model_name == "ds"

    async def test_db_failure_rollback(self, svc, db_session):
        """
        场景: 本地 DB upsert 失败.

        预期: 调 /model/delete 回滚 LiteLLM
        """
        rollback_called = []

        async def mock_req(method, path, **kw):
            if path == "/model/delete":
                rollback_called.append(True)
            return {"model_name": "bad", "model_info": {"id": "uuid-bad"}}

        with patch.object(svc, "request", new=mock_req):
            with patch.object(
                LitellmModelParams, "upsert",
                new=AsyncMock(side_effect=Exception("DB error")),
            ):
                with pytest.raises(Exception, match="DB error"):
                    await svc.create_model(
                        db_session, model_name="bad",
                        litellm_params={"model": "bad/provider"},
                    )
        assert len(rollback_called) == 1

    async def test_rollback_without_uuid(self, svc, db_session):
        """
        场景: LiteLLM 响应中无法提取 ID.

        预期: 抛 LitellmServiceError, 用 model_name 回滚
        """
        rollback_id = []

        async def mock_req(method, path, **kw):
            if path == "/model/delete":
                rollback_id.append(kw["json_data"]["id"])
            return {"model_name": "bad"}

        with patch.object(svc, "request", new=mock_req):
            with pytest.raises(
                LitellmServiceError, match="Failed to extract model_id",
            ):
                await svc.create_model(
                    db_session, model_name="bad",
                    litellm_params={"model": "bad"},
                )
        assert rollback_id == ["bad"]


class TestDeleteModel:
    """delete_model — 删除 + 幂等"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_404_idempotent(self, svc, db_session):
        """
        场景: LiteLLM 返回 404.

        预期: 视为幂等, 本地记录正常删除
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-old", "old",
            LocalModelExtension(),
        )

        async def mock_req(method, path, **kw):
            raise LitellmUpstreamError(404, "Not Found")

        with patch.object(svc, "request", new=mock_req):
            r = await svc.delete_model(db_session, "uuid-old")
        assert r["ok"] is True
        assert r["orphan_warning"] is False
        assert await LitellmModelParams.get_by_id(db_session, "uuid-old") is None

    async def test_500_propagates(self, svc, db_session):
        """
        场景: LiteLLM 返回 500.

        预期: 异常向上传播, 本地记录保留不删
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-old", "old",
            LocalModelExtension(),
        )

        async def mock_req(method, path, **kw):
            raise LitellmUpstreamError(500, "Err")

        with patch.object(svc, "request", new=mock_req):
            with pytest.raises(LitellmUpstreamError):
                await svc.delete_model(db_session, "uuid-old")
        assert await LitellmModelParams.get_by_id(db_session, "uuid-old") is not None


class TestUpdateModel:
    """update_model — 更新 + 本地写入失败传播"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    async def test_db_failure_propagates(self, svc, db_session):
        """
        场景: 本地 DB upsert 失败.

        预期: 向上抛异常, 记录 warning
        """
        await LitellmModelParams.upsert(
            db_session, "uuid-ds", "ds",
            LocalModelExtension(),
        )
        with patch.object(
            svc, "request",
            new=AsyncMock(return_value={"model_name": "ds"}),
        ):
            with patch.object(
                LitellmModelParams, "upsert",
                new=AsyncMock(side_effect=Exception("DB error")),
            ):
                with pytest.raises(Exception, match="DB error"):
                    await svc.update_model(
                        db_session, model_id="uuid-ds",
                        litellm_params={"model": "ds"},
                    )
