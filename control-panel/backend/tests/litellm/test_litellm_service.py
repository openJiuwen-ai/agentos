"""Unit tests for LitellmService — model management.

Covers:
  - Schema validation (ModelUpdate, ModelCreate)
  - LitellmService.request() exception mapping
  - LitellmService CRUD (create, update, delete) with mocked httpx + DB
  - Route layer (litellm_model.py) with FastAPI TestClient + DI overrides

All LiteLLM HTTP calls are mocked — no external dependency.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _mock_agent_metrics_sync(monkeypatch: pytest.MonkeyPatch):
    """避免 CRUD 测试写入真实 agent-metrics.json。"""

    async def fake_create(model_name, instance_url, inference_engine=None):
        if not instance_url:
            return None
        desc = (inference_engine or model_name).lower()
        return {
            "grafana_job_name": f"{desc}-metrics-target",
        }

    async def fake_update(
        model_name, local, instance_url, inference_engine=None,
    ):
        effective_url = instance_url or (local.instance_url if local else None)
        if not effective_url:
            return None
        desc = (
            inference_engine
            or (local.inference_engine if local else None)
            or model_name
        ).lower()
        return {
            "grafana_job_name": f"{desc}-metrics-target",
        }

    async def fake_delete(model_name, local):
        return None

    monkeypatch.setattr(
        "app.services.litellm_service._sync_metrics_on_create", fake_create,
    )
    monkeypatch.setattr(
        "app.services.litellm_service._sync_metrics_on_update", fake_update,
    )
    monkeypatch.setattr(
        "app.services.litellm_service._sync_metrics_on_delete", fake_delete,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Schema: ModelUpdate
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelUpdateSchema:
    """ModelUpdate schema — 本次改动新增 model_info 字段."""

    def test_minimal_valid(self):
        """场景: 仅传必填字段 litellm_params.
        预期: model_info / instance_url / max_concurrent 均为 None, 验证通过."""
        from app.schemas.litellm import ModelUpdate
        body = ModelUpdate(
            litellm_params={"model": "openai/gpt-4o", "api_key": "sk-xxx"},
        )
        assert body.litellm_params.model == "openai/gpt-4o"
        assert body.model_info is None
        assert body.instance_url is None
        assert body.max_concurrent is None

    def test_full_fields(self):
        """场景: 传入所有可选字段.
        预期: 所有字段正确解析, model_info 含 description 和 context_window."""
        from app.schemas.litellm import ModelUpdate
        body = ModelUpdate(
            litellm_params={"model": "openai/gpt-4o", "api_key": "sk-xxx"},
            model_info={"description": "test", "context_window": 8192},
            instance_url="https://example.com/v1",
            max_concurrent=5,
        )
        assert body.model_info.description == "test"
        assert body.model_info.context_window == 8192
        assert body.instance_url == "https://example.com/v1"
        assert body.max_concurrent == 5

    def test_model_info_has_no_id_field(self):
        """场景: 检查 ModelInfo schema 的字段定义.
        预期: ModelInfo 不应包含 'id' 字段 — ID 由 service 层注入, 不由用户传入."""
        from app.schemas.litellm import ModelInfo
        assert "id" not in ModelInfo.model_fields, (
            "ModelInfo must not have an 'id' field"
        )

    def test_max_concurrent_must_be_positive(self):
        """场景: max_concurrent 传入 0.
        预期: Pydantic 校验失败 (ge=1)."""
        from app.schemas.litellm import ModelUpdate
        with pytest.raises(Exception):
            ModelUpdate(
                litellm_params={"model": "x", "api_key": "k"},
                max_concurrent=0,
            )

    def test_litellm_params_requires_model(self):
        """场景: litellm_params 中缺少必填字段 model.
        预期: Pydantic 校验失败."""
        from app.schemas.litellm import ModelUpdate
        with pytest.raises(Exception):
            ModelUpdate(litellm_params={"api_key": "k"})


# ═══════════════════════════════════════════════════════════════════════════════
# Schema: ModelCreate
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelCreateSchema:
    def test_model_name_required(self):
        """场景: 创建模型时不传 model_name.
        预期: Pydantic 校验失败."""
        from app.schemas.litellm import ModelCreate
        with pytest.raises(Exception):
            ModelCreate(litellm_params={"model": "x", "api_key": "k"})

    def test_valid_create(self):
        """场景: 传入完整的创建参数.
        预期: 所有字段正确解析, 包括 instance_url 和 max_concurrent."""
        from app.schemas.litellm import ModelCreate
        body = ModelCreate(
            model_name="deepseek-chat",
            litellm_params={"model": "deepseek/deepseek-chat", "api_key": "sk-ds"},
            model_info={"description": "DeepSeek"},
            instance_url="https://api.deepseek.com/v1",
            max_concurrent=10,
        )
        assert body.model_name == "deepseek-chat"
        assert body.max_concurrent == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Service: request() — HTTP 异常映射
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceRequest:
    """LitellmService.request() — httpx 异常 → 业务异常 的映射."""

    @pytest.fixture
    def svc(self):
        """注入 mock httpx client, 绕过真实网络."""
        from app.services.litellm_service import LitellmService
        s = LitellmService()
        s._client = AsyncMock()
        return s

    @pytest.mark.asyncio
    async def test_success_response(self, svc):
        """场景: LiteLLM 返回 200 + JSON body.
        预期: 返回解析后的 dict."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"data": "ok"}'
        mock_resp.json.return_value = {"data": "ok"}
        svc._client.request = AsyncMock(return_value=mock_resp)

        result = await svc.request("GET", "/test")
        assert result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_204_no_content(self, svc):
        """场景: LiteLLM 返回 204 No Content.
        预期: 返回空 dict."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.content = b""
        svc._client.request = AsyncMock(return_value=mock_resp)

        result = await svc.request("POST", "/test")
        assert result == {}

    @pytest.mark.asyncio
    async def test_400_upstream_error(self, svc):
        """场景: LiteLLM 返回 400 + error JSON.
        预期: 抛出 LitellmUpstreamError, status_code=400, detail 含错误信息."""
        from app.services.litellm_service import LitellmUpstreamError

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.content = b'{"error": "bad request"}'
        mock_resp.json.return_value = {"error": "bad request"}
        svc._client.request = AsyncMock(return_value=mock_resp)

        with pytest.raises(LitellmUpstreamError) as exc_info:
            await svc.request("POST", "/test")
        assert exc_info.value.status_code == 400
        assert "bad request" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_connect_error(self, svc):
        """场景: httpx 抛出 ConnectError (网络不通).
        预期: 映射为 LitellmConnectionError, 信息包含 'Cannot connect'."""
        import httpx
        from app.services.litellm_service import LitellmConnectionError

        svc._client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(LitellmConnectionError) as exc_info:
            await svc.request("GET", "/test")
        assert "Cannot connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error(self, svc):
        """场景: httpx 抛出 TimeoutException.
        预期: 映射为 LitellmConnectionError, 信息包含 'Timeout'."""
        import httpx
        from app.services.litellm_service import LitellmConnectionError

        svc._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        with pytest.raises(LitellmConnectionError) as exc_info:
            await svc.request("GET", "/test")
        assert "Timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_json_response(self, svc):
        """场景: LiteLLM 返回 500 但 body 不是合法 JSON (如 HTML 错误页).
        预期: 抛出 LitellmUpstreamError, detail 包含 'Non-JSON'."""
        from app.services.litellm_service import LitellmUpstreamError

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.content = b"<html>Internal Server Error</html>"
        mock_resp.text = "<html>Internal Server Error</html>"
        mock_resp.json.side_effect = ValueError("not json")
        svc._client.request = AsyncMock(return_value=mock_resp)

        with pytest.raises(LitellmUpstreamError) as exc_info:
            await svc.request("GET", "/test")
        assert "Non-JSON" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════════════
# Service: create_model
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceCreateModel:
    """LitellmService.create_model() — LiteLLM 注册 + 本地 DB 写入."""

    @pytest.fixture
    def svc(self):
        from app.services.litellm_service import LitellmService
        s = LitellmService()
        s._client = AsyncMock()
        return s

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_success(self, svc, mock_db):
        """场景: LiteLLM 返回 model_id, 本地 DB upsert 成功.
        预期: 返回 id, model_name, instance_url, max_concurrent, created_at."""
        from datetime import datetime, timezone
        from app.services.litellm_service import CreateModelExtras

        mock_row = MagicMock()
        mock_row.created_at = datetime.now(timezone.utc)

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"model_id": "uuid-123"}

            with patch(
                "app.services.litellm_service.LitellmModelParams.upsert",
                new_callable=AsyncMock,
            ) as mock_upsert:
                mock_upsert.return_value = mock_row

                result = await svc.create_model(
                    mock_db,
                    model_name="test-model",
                    litellm_params={"model": "openai/test", "api_key": "sk-x"},
                    extras=CreateModelExtras(
                        model_info={"description": "desc"},
                        instance_url="https://example.com/v1",
                        max_concurrent=5,
                        inference_engine="vLLM",
                    ),
                )

                assert result["model_name"] == "test-model"
                assert result["id"] == "uuid-123"
                assert result["instance_url"] == "https://example.com/v1"
                assert result["max_concurrent"] == 5
                # DB upsert 收到正确的 model_id / model_name 与 agent-metrics 元数据
                assert mock_upsert.call_args[0][1] == "uuid-123"
                assert mock_upsert.call_args[0][2] == "test-model"
                ext = mock_upsert.call_args[0][3]
                assert ext.extra_params["grafana_job_name"] == "vllm-metrics-target"
                assert ext.inference_engine == "vLLM"

    @pytest.mark.asyncio
    async def test_create_extracts_id_from_model_info(self, svc, mock_db):
        """场景: LiteLLM 返回的 ID 在 model_info.id 中 (非 model_id/model_uuid 字段).
        预期: 正确从 model_info.id 提取 ID."""
        from datetime import datetime, timezone

        mock_row = MagicMock()
        mock_row.created_at = datetime.now(timezone.utc)

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"model_info": {"id": "uuid-from-info"}}

            with patch(
                "app.services.litellm_service.LitellmModelParams.upsert",
                new_callable=AsyncMock,
            ) as mock_upsert:
                mock_upsert.return_value = mock_row

                result = await svc.create_model(
                    mock_db,
                    model_name="test-model",
                    litellm_params={"model": "openai/test", "api_key": "sk-x"},
                )

                assert result["id"] == "uuid-from-info"

    @pytest.mark.asyncio
    async def test_create_no_id_triggers_rollback(self, svc, mock_db):
        """场景: LiteLLM 创建成功但响应中无法提取 ID.
        预期: 抛出 LitellmServiceError, 并调用 /model/delete 回滚 LiteLLM 端的模型."""
        from app.services.litellm_service import LitellmServiceError

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}  # 无 ID

            with pytest.raises(LitellmServiceError) as exc_info:
                await svc.create_model(
                    mock_db,
                    model_name="test-model",
                    litellm_params={"model": "openai/test", "api_key": "sk-x"},
                )
            assert "model_id" in str(exc_info.value)

            # 验证回滚调用了 /model/delete
            has_delete = any(
                len(c.args) >= 2 and c.args[1] == "/model/delete"
                for c in mock_req.call_args_list
            )
            assert has_delete, "Rollback /model/delete was not called"


# ═══════════════════════════════════════════════════════════════════════════════
# Service: update_model — 本次改动核心
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceUpdateModel:
    """LitellmService.update_model() — model_name 定位 + id 注入."""

    @pytest.fixture
    def svc(self):
        from app.services.litellm_service import LitellmService
        s = LitellmService()
        s._client = AsyncMock()
        return s

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_update_success(self, svc, mock_db):
        """场景: 本地 DB 有记录, LiteLLM 接受更新.
        预期: 返回更新结果; LiteLLM 请求 body 中 model_info.id 为本地 DB 的 id."""
        from datetime import datetime, timezone
        from app.models.litellm_model_params import LitellmModelParams
        from app.services.litellm_service import UpdateModelExtras

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.id = "uuid-123"
        mock_local.model_name = "test-model"

        mock_updated_row = MagicMock()
        mock_updated_row.updated_at = datetime.now(timezone.utc)

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.upsert",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            mock_req.return_value = {"status": "ok"}
            mock_get.return_value = mock_local
            mock_upsert.return_value = mock_updated_row

            result = await svc.update_model(
                mock_db,
                model_id="uuid-123",
                litellm_params={"model": "openai/test", "api_key": "sk-new"},
                extras=UpdateModelExtras(
                    instance_url="https://new.example.com/v1",
                    max_concurrent=8,
                ),
            )

            assert result["model_name"] == "test-model"
            assert result["instance_url"] == "https://new.example.com/v1"
            assert result["max_concurrent"] == 8

            body = mock_req.call_args.kwargs["json_data"]
            assert "model_info" in body
            assert body["model_info"]["id"] == "uuid-123"

    @pytest.mark.asyncio
    async def test_update_request_body_structure(self, svc, mock_db):
        """场景: 仅传必填参数 (无 instance_url/max_concurrent).
        预期: LiteLLM 请求 body 包含 model_name, litellm_params, model_info.{id}."""
        from datetime import datetime, timezone
        from app.models.litellm_model_params import LitellmModelParams

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.id = "uuid-abc"
        mock_local.model_name = "test-model"

        mock_updated_row = MagicMock()
        mock_updated_row.updated_at = datetime.now(timezone.utc)

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.upsert",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            mock_req.return_value = {}
            mock_get.return_value = mock_local
            mock_upsert.return_value = mock_updated_row

            await svc.update_model(
                mock_db,
                model_id="uuid-abc",
                litellm_params={"model": "openai/test", "api_key": "sk-x"},
            )

            body = mock_req.call_args.kwargs["json_data"]
            assert body["model_name"] == "test-model"
            assert body["litellm_params"] == {
                "model": "openai/test", "api_key": "sk-x",
            }
            assert body["model_info"]["id"] == "uuid-abc"

    @pytest.mark.asyncio
    async def test_user_model_info_id_is_stripped(self, svc, mock_db):
        """场景: 用户传入 model_info 含 'id' 字段, 试图覆盖 UUID.
        预期: 'id' 被过滤, 最终 body 中 model_info.id 仍为本地 DB 的 ID;
              其他字段 (description) 正常保留."""
        from datetime import datetime, timezone
        from app.models.litellm_model_params import LitellmModelParams
        from app.services.litellm_service import UpdateModelExtras

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.id = "real-uuid"
        mock_local.model_name = "test-model"

        mock_updated_row = MagicMock()
        mock_updated_row.updated_at = datetime.now(timezone.utc)

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.upsert",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            mock_req.return_value = {}
            mock_get.return_value = mock_local
            mock_upsert.return_value = mock_updated_row

            await svc.update_model(
                mock_db,
                model_id="real-uuid",
                litellm_params={"model": "openai/test", "api_key": "sk-x"},
                extras=UpdateModelExtras(
                    model_info={
                        "id": "attacker-uuid",
                        "description": "legit desc",
                    },
                ),
            )

            body = mock_req.call_args.kwargs["json_data"]
            assert body["model_info"]["id"] == "real-uuid", (
                "id must NOT be overwritten by user input"
            )
            assert body["model_info"]["description"] == "legit desc"

    @pytest.mark.asyncio
    async def test_no_local_record_raises(self, svc, mock_db):
        """场景: 本地 DB 中无此模型的记录 (get_by_names 返回空).
        预期: 抛出 LitellmServiceError, 信息含 'not found' 和模型名称."""
        from app.services.litellm_service import LitellmServiceError

        with patch(
            "app.services.litellm_service.LitellmModelParams.get_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(LitellmServiceError) as exc_info:
                await svc.update_model(
                    mock_db,
                    model_id="nonexistent",
                    litellm_params={"model": "openai/test", "api_key": "sk-x"},
                )
            assert "not found" in str(exc_info.value)
            assert "nonexistent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_db_failure_logs_warning_and_raises(self, svc, mock_db):
        """场景: LiteLLM 更新成功, 但本地 DB upsert 失败.
        预期: 记录 warning 日志, 然后抛出原始异常."""
        from app.models.litellm_model_params import LitellmModelParams

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.id = "uuid-123"
        mock_local.model_name = "test-model"

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.upsert",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch("app.services.litellm_service.logger") as mock_logger,
        ):
            mock_req.return_value = {}
            mock_get.return_value = mock_local
            mock_upsert.side_effect = RuntimeError("DB down")

            with pytest.raises(RuntimeError):
                await svc.update_model(
                    mock_db,
                    model_id="uuid-123",
                    litellm_params={"model": "openai/test", "api_key": "sk-x"},
                )

            mock_logger.warning.assert_called_once()
            assert "agent-metrics" in mock_logger.warning.call_args[0][0]


# ═══════════════════════════════════════════════════════════════════════════════
# Service: delete_model
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceDeleteModel:
    """LitellmService.delete_model() — model_id 定位 + 幂等 + orphan 告警."""

    @pytest.fixture
    def svc(self):
        from app.services.litellm_service import LitellmService
        s = LitellmService()
        s._client = AsyncMock()
        return s

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_delete_with_id(self, svc, mock_db):
        """场景: 本地 DB 有记录, LiteLLM 删除成功.
        预期: 返回 ok=True, orphan_warning=False; LiteLLM 删除请求使用 id."""
        from app.models.litellm_model_params import LitellmModelParams

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.id = "uuid-del"

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.delete_by_id",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            mock_req.return_value = {}
            mock_get.return_value = mock_local
            mock_delete.return_value = True

            result = await svc.delete_model(mock_db, "uuid-del")
            assert result["ok"] is True
            assert result["orphan_warning"] is False
            assert mock_req.call_args.kwargs["json_data"]["id"] == "uuid-del"

    @pytest.mark.asyncio
    async def test_delete_404_is_idempotent(self, svc, mock_db):
        """场景: LiteLLM 返回 404 (模型已不存在).
        预期: 不抛出异常, 返回 ok=True, 视为幂等成功."""
        from app.models.litellm_model_params import LitellmModelParams
        from app.services.litellm_service import LitellmUpstreamError

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.id = "uuid-del"

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.delete_by_id",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            mock_req.side_effect = LitellmUpstreamError(404, "not found")
            mock_get.return_value = mock_local
            mock_delete.return_value = True

            result = await svc.delete_model(mock_db, "uuid-del")
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_no_local_record_orphan_warning(self, svc, mock_db):
        """场景: 本地 DB 无此模型记录.
        预期: 跳过 LiteLLM 调用, 返回 orphan_warning=True, 记录 warning."""
        with (
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "app.services.litellm_service.LitellmModelParams.delete_by_id",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("app.services.litellm_service.logger") as mock_logger,
        ):
            mock_get.return_value = None
            mock_delete.return_value = True

            result = await svc.delete_model(mock_db, "unknown-id")
            assert result["ok"] is True
            assert result["orphan_warning"] is True
            mock_logger.warning.assert_called_once()
            assert "not found" in mock_logger.warning.call_args[0][0]


# ═══════════════════════════════════════════════════════════════════════════════
# Service: list_models
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceListModels:
    """LitellmService.list_models() — LiteLLM /model/info 解析 + 合并本地字段."""

    @pytest.fixture
    def svc(self):
        from app.services.litellm_service import LitellmService
        s = LitellmService()
        s._client = AsyncMock()
        return s

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        db.execute.return_value = empty_result
        return db

    @pytest.mark.asyncio
    async def test_list_models_data_format(self, svc, mock_db):
        """场景: /model/info 返回 {'data': [...]} 格式, 本地无扩展字段.
        预期: 正确解析 items."""
        llm_response = {
            "data": [
                {"model_name": "deepseek-chat", "litellm_params": {"model": "ds"}, "model_info": {}},
                {"model_name": "gpt-4o", "litellm_params": {"model": "gpt"}, "model_info": {}},
            ]
        }

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = llm_response

            result = await svc.list_models(mock_db, page=1, page_size=20)

        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0]["model_name"] == "deepseek-chat"
        assert result["items"][1]["model_name"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_list_models_data_is_list(self, svc, mock_db):
        """场景: /model/info 直接返回列表 [...].
        预期: 同样正确解析."""
        llm_response = [
            {"model_name": "model-a", "litellm_params": {}, "model_info": {}},
        ]

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = llm_response

            result = await svc.list_models(mock_db, page=1, page_size=20)

        assert result["total"] == 1
        assert result["items"][0]["model_name"] == "model-a"

    @pytest.mark.asyncio
    async def test_list_models_empty(self, svc, mock_db):
        """场景: /model/info 返回空列表.
        预期: total=0, items=[]."""
        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": []}

            result = await svc.list_models(mock_db, page=1, page_size=20)

        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_list_models_skips_no_model_name(self, svc, mock_db):
        """场景: /model/info 返回的模型项缺少 'model_name' 字段.
        预期: 被跳过."""
        llm_response = {
            "data": [
                {"model_name": "valid-model", "litellm_params": {}, "model_info": {}},
                {"litellm_params": {}},  # 无 model_name
                {"model_name": "", "litellm_params": {}},  # model_name 为空串
            ]
        }

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = llm_response

            result = await svc.list_models(mock_db, page=1, page_size=20)

        assert result["total"] == 1
        assert result["items"][0]["model_name"] == "valid-model"

    @pytest.mark.asyncio
    async def test_list_models_unexpected_response_format(self, svc, mock_db):
        """场景: LiteLLM 返回非预期格式 (无 'data' key 也非列表).
        预期: 不崩溃, 返回 total=0 空列表 (防御性处理)."""
        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"models": [{"model_name": "x"}], "object": "list"}

            result = await svc.list_models(mock_db, page=1, page_size=20)

        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_list_models_merges_local_fields(self, svc):
        """场景: LiteLLM 返回 2 个模型, 本地有 1 个的 instance_url.
        预期: 合并后本地记录的 instance_url 正确注入到对应模型."""
        from app.models.litellm_model_params import LitellmModelParams

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.instance_url = "https://custom.example.com/v1"
        mock_local.max_concurrent = 10
        mock_local.created_at = None
        mock_local.updated_at = None
        mock_local.model_name = "model-with-local"
        mock_local.id = "uuid-local"

        llm_response = {
            "data": [
                {"model_name": "model-with-local", "litellm_params": {"model": "x"}, "model_info": {}},
                {"model_name": "model-no-local", "litellm_params": {"model": "y"}, "model_info": {}},
            ]
        }

        # db.execute() 只调用一次 (按 model_name 查询)
        result1 = MagicMock()
        result1.scalars.return_value.all.return_value = [mock_local]

        mock_db = AsyncMock()
        mock_db.execute.return_value = result1

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = llm_response

            result = await svc.list_models(mock_db, page=1, page_size=20)

        assert result["total"] == 2
        local_item = next(i for i in result["items"] if i["model_name"] == "model-with-local")
        assert local_item["instance_url"] == "https://custom.example.com/v1"

        no_local = next(i for i in result["items"] if i["model_name"] == "model-no-local")
        assert no_local["instance_url"] is None

    @pytest.mark.asyncio
    async def test_list_models_pagination(self, svc, mock_db):
        """场景: LiteLLM 返回 25 条模型, 分页 10 条/页.
        预期: page=1 返回 10 条, page=3 返回 5 条, total=25."""
        llm_response = {
            "data": [{"model_name": f"m-{i}", "litellm_params": {}, "model_info": {}} for i in range(25)]
        }

        with patch.object(svc, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = llm_response

            page1 = await svc.list_models(mock_db, page=1, page_size=10)
            assert page1["total"] == 25
            assert len(page1["items"]) == 10
            assert page1["page"] == 1

            page3 = await svc.list_models(mock_db, page=3, page_size=10)
            assert len(page3["items"]) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Service: get_model
# ═══════════════════════════════════════════════════════════════════════════════


class TestServiceGetModel:
    """LitellmService.get_model() — 按 model_id 查询单个模型."""

    @pytest.fixture
    def svc(self):
        from app.services.litellm_service import LitellmService
        s = LitellmService()
        s._client = AsyncMock()
        return s

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_model_found(self, svc, mock_db):
        """场景: /model/info 返回目标模型.
        预期: 返回该模型的合并详情."""
        llm_response = {
            "data": [
                {"model_name": "model-a", "litellm_params": {"model": "a"}, "model_info": {"id": "hash-a"}},
                {"model_name": "model-b", "litellm_params": {"model": "b"}, "model_info": {"id": "hash-b"}},
            ]
        }

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_req.return_value = llm_response
            mock_get.return_value = None

            result = await svc.get_model(mock_db, "model-b")

        assert result is not None
        assert result["model_name"] == "model-b"
        assert result["id"] == "hash-b"

    @pytest.mark.asyncio
    async def test_get_model_not_found(self, svc, mock_db):
        """场景: 目标模型不在 /model/info 返回列表中.
        预期: 返回 None."""
        llm_response = {
            "data": [{"model_name": "other-model", "litellm_params": {}, "model_info": {}}]
        }

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_req.return_value = llm_response
            mock_get.return_value = None

            result = await svc.get_model(mock_db, "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_model_empty_response(self, svc, mock_db):
        """场景: /model/info 返回空列表.
        预期: 返回 None."""
        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_req.return_value = {"data": []}
            mock_get.return_value = None

            result = await svc.get_model(mock_db, "any-model")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_model_with_local_fields(self, svc, mock_db):
        """场景: 查询的模型在本地 DB 中有扩展字段.
        预期: instance_url 等本地字段被注入到结果中."""
        from app.models.litellm_model_params import LitellmModelParams

        mock_local = MagicMock(spec=LitellmModelParams)
        mock_local.instance_url = "https://my-instance.example.com/v1"
        mock_local.max_concurrent = 5
        mock_local.created_at = None
        mock_local.updated_at = None
        mock_local.model_name = "my-model"

        llm_response = {
            "data": [{"model_name": "my-model", "litellm_params": {"model": "gpt"}, "model_info": {}}]
        }

        with (
            patch.object(svc, "request", new_callable=AsyncMock) as mock_req,
            patch(
                "app.services.litellm_service.LitellmModelParams.get_by_id",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_req.return_value = llm_response
            mock_get.return_value = mock_local

            result = await svc.get_model(mock_db, "my-model")

        assert result["id"] == "my-model"
        assert result["instance_url"] == "https://my-instance.example.com/v1"


# ═══════════════════════════════════════════════════════════════════════════════
# Route: update_model
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouteUpdateModel:
    """PUT /api/v1/litellm/model/{model_id} — 路由层: schema 校验 + 异常映射.

    使用独立 FastAPI app + DI override, 不依赖真实 DB 或 LiteLLM."""

    @pytest.fixture
    def client(self):
        """构建 TestClient: 含 litellm router, service/session/admin 全部 mock."""
        from unittest.mock import AsyncMock
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.litellm_model import router
        from app.services.litellm_service import LitellmService
        from app.database import get_session
        from app.litellm_deps import get_litellm_svc
        from app.iam.deps import require_admin

        app = FastAPI()
        app.include_router(router)

        mock_svc = AsyncMock(spec=LitellmService)
        mock_db = AsyncMock()

        async def override_get_session():
            yield mock_db

        async def override_get_svc():
            return mock_svc

        async def override_admin():
            from app.iam.tokens import TokenData
            return TokenData(user_id="test-admin", username="admin", role="admin")

        app.dependency_overrides[get_session] = override_get_session
        app.dependency_overrides[get_litellm_svc] = override_get_svc
        app.dependency_overrides[require_admin] = override_admin

        tc = TestClient(app)
        tc.mock_svc = mock_svc
        tc.mock_db = mock_db
        return tc

    def test_update_missing_litellm_params_returns_422(self, client):
        """场景: 请求 body 缺少必填字段 litellm_params.
        预期: FastAPI 返回 422 Unprocessable Entity."""
        response = client.put(
            "/api/v1/litellm/model/uuid-test",
            json={"instance_url": "https://example.com/v1"},
        )
        assert response.status_code == 422

    def test_update_valid_body_passes_validation(self, client):
        """场景: 完整的合法请求, service 返回成功.
        预期: 200 + data.model_name 正确; service 收到的 model_info 不含 'id'."""
        from app.schemas.litellm import ModelUpdated
        from datetime import datetime, timezone
        client.mock_svc.update_model.return_value = ModelUpdated(
            id="uuid-123", model_name="test-model",
            updated_at=datetime.now(timezone.utc),
        )

        response = client.put(
            "/api/v1/litellm/model/uuid-123",
            json={
                "litellm_params": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                },
                "model_info": {
                    "description": "test update",
                    "context_window": 16384,
                },
                "instance_url": "https://example.com/v1",
                "max_concurrent": 5,
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["model_name"] == "test-model"

        call_kwargs = client.mock_svc.update_model.call_args.kwargs
        assert call_kwargs["model_id"] == "uuid-123"
        extras = call_kwargs["extras"]
        assert extras.model_info == {
            "description": "test update",
            "context_window": 16384,
        }
        assert "id" not in extras.model_info

    def test_update_model_info_optional(self, client):
        """场景: 不传 model_info (可选字段).
        预期: 200; service 收到 model_info=None."""
        from app.schemas.litellm import ModelUpdated
        from datetime import datetime, timezone
        client.mock_svc.update_model.return_value = ModelUpdated(
            id="uuid-123", model_name="test-model",
            updated_at=datetime.now(timezone.utc),
        )

        response = client.put(
            "/api/v1/litellm/model/uuid-123",
            json={
                "litellm_params": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                },
            },
        )
        assert response.status_code == 200
        assert client.mock_svc.update_model.call_args.kwargs["extras"].model_info is None

    def test_litellm_service_error_returns_500(self, client):
        """场景: service 层抛出 LitellmServiceError (如模型未找到).
        预期: 路由返回 500, detail 包含原始错误信息."""
        from app.services.litellm_service import LitellmServiceError
        client.mock_svc.update_model.side_effect = LitellmServiceError(
            "model not found"
        )

        response = client.put(
            "/api/v1/litellm/model/nonexistent",
            json={
                "litellm_params": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                },
            },
        )
        assert response.status_code == 500
        assert "model not found" in response.json()["detail"]

    def test_connection_error_returns_502(self, client):
        """场景: service 层抛出 LitellmConnectionError (LiteLLM 不可达).
        预期: 路由返回 502, detail 包含连接错误信息."""
        from app.services.litellm_service import LitellmConnectionError
        client.mock_svc.update_model.side_effect = LitellmConnectionError(
            "Cannot connect"
        )

        response = client.put(
            "/api/v1/litellm/model/uuid-test",
            json={
                "litellm_params": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                },
            },
        )
        assert response.status_code == 502
        assert "Cannot connect" in response.json()["detail"]

    def test_id_field_in_model_info_dropped_by_schema(self, client):
        """场景: 客户端在 model_info 中传入 'id' 字段.
        预期: Pydantic schema (ModelInfo 无 id 字段) 静默丢弃 'id';
              service 收到的 model_info 中不含 'id', description 正常保留."""
        from app.schemas.litellm import ModelUpdated
        from datetime import datetime, timezone
        client.mock_svc.update_model.return_value = ModelUpdated(
            id="uuid-123", model_name="test-model",
            updated_at=datetime.now(timezone.utc),
        )

        response = client.put(
            "/api/v1/litellm/model/uuid-123",
            json={
                "litellm_params": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                },
                "model_info": {
                    "id": "should-be-dropped",
                    "description": "test",
                },
            },
        )
        assert response.status_code == 200

        extras = client.mock_svc.update_model.call_args.kwargs["extras"]
        model_info_to_svc = extras.model_info
        assert "id" not in (model_info_to_svc or {}), (
            f"'id' must not reach service: {model_info_to_svc}"
        )
        assert model_info_to_svc["description"] == "test"
        assert model_info_to_svc.get("context_window") is None
