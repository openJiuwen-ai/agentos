"""模型管理 API 测试 — CRUD + 分页 + 异常映射"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.litellm_service import LitellmUpstreamError


class TestListModelsAPI:
    """GET /api/v1/litellm/model — 模型列表"""

    async def test_empty(self, client):
        mock = {"total": 0, "page": 1, "page_size": 20, "items": []}
        with patch(
            "app.api.v1.litellm_model.LitellmService.list_models",
            new=AsyncMock(return_value=mock),
        ):
            resp = await client.get("/api/v1/litellm/model")
            assert resp.status_code == 200
            assert resp.json()["data"]["total"] == 0

    async def test_with_data(self, client):
        mock = {
            "total": 1, "page": 1, "page_size": 20,
            "items": [{
                "id": "uuid-123", "model_name": "deepseek-chat",
                "litellm_params": {"model": "deepseek/deepseek-chat"},
                "model_info": None,
                "instance_url": "https://example.com:8000/v1", "created_at": None,
            }],
        }
        with patch(
            "app.api.v1.litellm_model.LitellmService.list_models",
            new=AsyncMock(return_value=mock),
        ):
            resp = await client.get("/api/v1/litellm/model")
            assert resp.status_code == 200
            assert resp.json()["data"]["items"][0]["model_name"] == "deepseek-chat"

    async def test_upstream_error_502(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.list_models",
            new=AsyncMock(side_effect=LitellmUpstreamError(500, "Down")),
        ):
            resp = await client.get("/api/v1/litellm/model")
            assert resp.status_code == 502


class TestGetModelAPI:
    """GET /api/v1/litellm/model/{model_id} — 单个模型详情"""

    async def test_found(self, client):
        mock = {
            "id": "uuid-123", "model_name": "deepseek-chat",
            "litellm_params": {"model": "deepseek-chat"},
            "model_info": {"description": "DeepSeek"},
            "instance_url": "https://example.com:8000/v1",
            "max_concurrent": None, "created_at": None, "updated_at": None,
        }
        with patch(
            "app.api.v1.litellm_model.LitellmService.get_model",
            new=AsyncMock(return_value=mock),
        ):
            resp = await client.get("/api/v1/litellm/model/uuid-123")
            assert resp.status_code == 200
            assert resp.json()["data"]["model_info"] == {"description": "DeepSeek"}

    async def test_not_found(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.get_model",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.get("/api/v1/litellm/model/nonexistent")
            assert resp.status_code == 404

    async def test_upstream_error_502(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.get_model",
            new=AsyncMock(side_effect=LitellmUpstreamError(500, "Down")),
        ):
            resp = await client.get("/api/v1/litellm/model/some-id")
            assert resp.status_code == 502


class TestCreateModelAPI:
    """POST /api/v1/litellm/model — 创建模型"""

    async def test_success(self, client):
        mock = {
            "id": "uuid-new", "model_name": "deepseek-chat",
            "instance_url": "https://example.com:8000/v1", "created_at": None,
        }
        with patch(
            "app.api.v1.litellm_model.LitellmService.create_model",
            new=AsyncMock(return_value=mock),
        ):
            resp = await client.post("/api/v1/litellm/model", json={
                "model_name": "deepseek-chat",
                "litellm_params": {
                    "model": "deepseek/deepseek-chat", "api_key": "sk-xxx",
                    "api_base": "https://api.deepseek.com/v1",
                },
                "model_info": {"description": "DeepSeek"},
                "instance_url": "https://example.com:8000/v1",
            })
            assert resp.status_code == 201
            assert resp.json()["data"]["model_name"] == "deepseek-chat"

    async def test_upstream_error_502(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.create_model",
            new=AsyncMock(side_effect=LitellmUpstreamError(400, "Bad Request")),
        ):
            resp = await client.post("/api/v1/litellm/model", json={
                "model_name": "bad", "litellm_params": {"model": "bad/provider"},
            })
            assert resp.status_code == 502


class TestUpdateModelAPI:
    """PUT /api/v1/litellm/model/{model_id} — 更新模型"""

    async def test_success(self, client):
        mock = {
            "id": "uuid-123", "model_name": "deepseek-chat",
            "instance_url": "https://new.example.com/v1",
            "max_concurrent": None, "updated_at": None,
        }
        with patch(
            "app.api.v1.litellm_model.LitellmService.update_model",
            new=AsyncMock(return_value=mock),
        ):
            resp = await client.put("/api/v1/litellm/model/uuid-123", json={
                "litellm_params": {"model": "deepseek/deepseek-chat", "api_key": "sk"},
                "instance_url": "https://new.example.com/v1",
            })
            assert resp.status_code == 200

    async def test_upstream_error_502(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.update_model",
            new=AsyncMock(side_effect=LitellmUpstreamError(404, "Not Found")),
        ):
            resp = await client.put(
                "/api/v1/litellm/model/nope",
                json={"litellm_params": {"model": "nope/provider"}},
            )
            assert resp.status_code == 502


class TestDeleteModelAPI:
    """DELETE /api/v1/litellm/model/{model_id} — 删除模型"""

    async def test_success(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.delete_model",
            new=AsyncMock(return_value={"ok": True}),
        ):
            resp = await client.delete("/api/v1/litellm/model/uuid-old")
            assert resp.status_code == 200
            assert resp.json()["data"]["ok"] is True

    async def test_upstream_error_502(self, client):
        with patch(
            "app.api.v1.litellm_model.LitellmService.delete_model",
            new=AsyncMock(side_effect=LitellmUpstreamError(500, "Server Error")),
        ):
            resp = await client.delete("/api/v1/litellm/model/uuid-old")
            assert resp.status_code == 502
