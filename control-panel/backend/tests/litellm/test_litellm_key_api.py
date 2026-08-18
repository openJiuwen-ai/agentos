"""测试 Key 管理 API 端点"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.litellm_service import (
    LitellmUpstreamError,
    LitellmConnectionError,
    MaxKeysReachedError,
    KeyNotFoundError,
)


class TestListKeysAPI:
    """GET /api/v1/litellm/key — 查询 Key 列表"""

    async def test_list_keys_empty(self, client):
        """
        场景: mock 服务层返回空 keys 数组.

        预期: HTTP 200, data.keys == []
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.list_keys",
            new=AsyncMock(return_value={"keys": []}),
        ):
            resp = await client.get("/api/v1/litellm/key")
            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["keys"] == []

    async def test_list_keys_with_data(self, client):
        """
        场景: mock 服务层返回两个 Key.

        预期: HTTP 200, data.keys 长度为 2
        """
        mock_keys = {
            "keys": [
                {
                    "uid": "user-1",
                    "key_preview": "sk-abc12***", "key_alias": "sk-abc", "key_name": None,
                    "bound_model": None, "created_at": None, "expires_at": None,
                },
                {
                    "uid": "user-1",
                    "key_preview": "sk-def45***", "key_alias": "sk-def", "key_name": None,
                    "bound_model": "deepseek", "created_at": None, "expires_at": None,
                },
            ]
        }
        with patch(
            "app.api.v1.litellm_key.LitellmService.list_keys",
            new=AsyncMock(return_value=mock_keys),
        ):
            resp = await client.get("/api/v1/litellm/key")
            assert resp.status_code == 200
            assert len(resp.json()["data"]["keys"]) == 2


class TestApplyKeyAPI:
    """POST /api/v1/litellm/key/generate — 申请 Key"""

    async def test_apply_key_success(self, client):
        """
        场景: 申请一个新 Key (不绑定模型).

        预期: HTTP 200, data.key == "sk-abc123xyz" 
        """
        mock_result = {
            "key": "sk-abc123xyz", "key_alias": "sk-abc123xyz", "key_name": None,
            "uid": "dev-user", "models": [], "expires": None,
        }
        with patch(
            "app.api.v1.litellm_key.LitellmService.apply_key",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = await client.post(
                "/api/v1/litellm/key/generate",
                json={"model": None, "key_name": "test-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["key"] == "sk-abc123xyz"

    async def test_apply_key_max_reached(self, client):
        """
        场景: mock 服务层抛出 MAX_KEYS_REACHED 错误.

        预期: HTTP 403
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.apply_key",
            new=AsyncMock(side_effect=MaxKeysReachedError("MAX_KEYS_REACHED")),
        ):
            resp = await client.post(
                "/api/v1/litellm/key/generate", json={"key_name": "test-key"},
            )
            assert resp.status_code == 403

    async def test_apply_key_upstream_error_502(self, client):
        """
        场景: mock 服务层抛出 LitellmUpstreamError(500).

        预期: HTTP 502
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.apply_key",
            new=AsyncMock(side_effect=LitellmUpstreamError(500, "Error")),
        ):
            resp = await client.post(
                "/api/v1/litellm/key/generate", json={"key_name": "test-key"},
            )
            assert resp.status_code == 502

    async def test_apply_key_connection_error_502(self, client):
        """
        场景: mock 服务层抛出 LitellmConnectionError.

        预期: HTTP 502
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.apply_key",
            new=AsyncMock(side_effect=LitellmConnectionError("timeout")),
        ):
            resp = await client.post(
                "/api/v1/litellm/key/generate", json={"key_name": "test-key"},
            )
            assert resp.status_code == 502


class TestDeleteKeyAPI:
    """DELETE /api/v1/litellm/key/{key_alias} — 删除 Key"""

    async def test_delete_key_success(self, client):
        """
        场景: 删除一个 Key.

        预期: HTTP 200, data.ok == True
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.delete_key",
            new=AsyncMock(return_value={"ok": True}),
        ):
            resp = await client.delete("/api/v1/litellm/key/sk-abc")
            assert resp.status_code == 200
            assert resp.json()["data"]["ok"] is True

    async def test_delete_key_not_found(self, client):
        """
        场景: mock 服务层抛出 KEY_NOT_FOUND 错误.

        预期: HTTP 404
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.delete_key",
            new=AsyncMock(side_effect=KeyNotFoundError("KEY_NOT_FOUND")),
        ):
            resp = await client.delete("/api/v1/litellm/key/nope")
            assert resp.status_code == 404

    async def test_delete_key_upstream_error_502(self, client):
        """
        场景: mock 服务层抛出 LitellmUpstreamError(500).

        预期: HTTP 502
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.delete_key",
            new=AsyncMock(side_effect=LitellmUpstreamError(500, "Error")),
        ):
            resp = await client.delete("/api/v1/litellm/key/sk-abc")
            assert resp.status_code == 502

    async def test_delete_key_connection_error_502(self, client):
        """
        场景: mock 服务层抛出 LitellmConnectionError.

        预期: HTTP 502
        """
        with patch(
            "app.api.v1.litellm_key.LitellmService.delete_key",
            new=AsyncMock(side_effect=LitellmConnectionError("timeout")),
        ):
            resp = await client.delete("/api/v1/litellm/key/sk-abc")
            assert resp.status_code == 502
