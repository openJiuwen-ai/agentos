"""Unit tests for image_process HTTP client (path-only factory API)."""

from unittest.mock import AsyncMock

import httpx
import pytest


def _client(client, url="http://image-process:8091"):
    from app.services.image_process_client import ImageProcessClient

    return ImageProcessClient(client=client, base_url=url, timeout=5.0)


def _response(status_code=200, *, json=None, text=None):
    if json is not None:
        return httpx.Response(status_code, json=json)
    return httpx.Response(status_code, text=text or "")


@pytest.mark.asyncio
async def test_build_from_path_requires_url():
    from app.services.image_process_client import ImageProcessClient, ImageProcessError

    client = ImageProcessClient(client=AsyncMock(), base_url="", timeout=5.0)
    with pytest.raises(ImageProcessError, match="IMAGE_PROCESS_URL"):
        await client.build_from_path("/x.tgz")


@pytest.mark.asyncio
async def test_build_from_path_posts_payload():
    http_client = AsyncMock()
    http_client.request = AsyncMock(
        return_value=_response(202, json={"request_id": "build-1"})
    )
    client = _client(http_client)
    rid = await client.build_from_path("/i.tgz", request_id="build-1")
    assert rid == "build-1"
    args, kwargs = http_client.request.await_args
    assert args[0] == "POST"
    assert args[1] == "http://image-process:8091/v1/builds"
    assert kwargs["json"]["package_path"] == "/i.tgz"
    assert kwargs["json"]["request_id"] == "build-1"


@pytest.mark.asyncio
async def test_build_from_path_connect_error():
    from app.services.image_process_client import ImageProcessError

    http_client = AsyncMock()
    http_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client = _client(http_client)
    with pytest.raises(ImageProcessError, match="unreachable"):
        await client.build_from_path("/x")


@pytest.mark.asyncio
async def test_fetch_build_returns_status():
    http_client = AsyncMock()
    http_client.request = AsyncMock(
        return_value=_response(
            json={
                "request_id": "build-1",
                "status": "building",
                "progress": 55,
                "image_ref": None,
                "name": "demo",
            },
        )
    )
    remote = await _client(http_client).fetch_build("build-1")
    assert remote is not None
    assert remote.status == "building"
    assert remote.progress == 55
    assert remote.name == "demo"


@pytest.mark.asyncio
async def test_fetch_build_404_returns_none():
    http_client = AsyncMock()
    http_client.request = AsyncMock(return_value=_response(404, text="missing"))
    assert await _client(http_client).fetch_build("missing") is None


@pytest.mark.asyncio
async def test_remove_loaded_image():
    http_client = AsyncMock()
    http_client.request = AsyncMock(return_value=_response(json={}))
    await _client(http_client).remove_loaded_image("demo:1.0")
    args, kwargs = http_client.request.await_args
    assert args[0] == "POST"
    assert args[1].endswith("/v1/images/remove")
    assert kwargs["json"] == {"tag": "demo:1.0"}
