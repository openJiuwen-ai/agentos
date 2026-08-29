"""Unit tests for AgentRegisterClient."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.agent_register_client import AgentRegisterClient, AgentRegisterError


def _client(client):
    return AgentRegisterClient(
        client=client, base_url="http://registry:4003", timeout=5.0
    )


def _response(status_code=200, *, json=None, headers=None):
    return httpx.Response(status_code, json=json, headers=headers)


@pytest.mark.asyncio
async def test_list_images():
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_response(
            json=[{"framework": "demo", "framework_version": "1.0"}],
            headers={"X-Total-Count": "1"},
        )
    )
    items, total = await _client(client).list_images(framework="demo")
    assert total == 1
    assert items[0]["framework"] == "demo"


@pytest.mark.asyncio
async def test_register_image():
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_response(json={"status": "registered"})
    )
    status = await _client(client).register_image(
        {"framework": "demo", "framework_version": "1"}
    )
    assert status == "registered"


@pytest.mark.asyncio
async def test_delete_image():
    client = AsyncMock()
    client.request = AsyncMock(return_value=_response(json={}))
    await _client(client).delete_image("demo", "1.0")
    args, kwargs = client.request.await_args
    assert args[0] == "DELETE"
    assert args[1].endswith("/api/images/demo/1.0")


@pytest.mark.asyncio
async def test_set_default_version():
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_response(
            json={"framework": "demo", "default": "2.0", "status": "updated"}
        )
    )
    body = await _client(client).set_default_version("demo", "2.0")
    args, kwargs = client.request.await_args
    assert args[0] == "PUT"
    assert args[1].endswith("/api/images/demo/default")
    assert kwargs["json"]["framework_version"] == "2.0"
    assert body["default"] == "2.0"


@pytest.mark.asyncio
async def test_list_instances():
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_response(json=[{"framework": "demo", "status": "运行"}])
    )
    items = await _client(client).list_instances(framework="demo")
    assert len(items) == 1


@pytest.mark.asyncio
async def test_missing_url():
    client = AgentRegisterClient(client=AsyncMock(), base_url="", timeout=1)
    with pytest.raises(AgentRegisterError, match="AGENT_REGISTER_URL"):
        await client.list_images()
