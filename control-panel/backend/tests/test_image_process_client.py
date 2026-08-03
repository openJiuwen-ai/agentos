"""Unit tests for image_process HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_submit_build_requires_url():
    from app.services.image_process_client import ImageProcessError, submit_build

    with patch("app.services.image_process_client.settings") as settings:
        settings.IMAGE_PROCESS_URL = ""
        settings.IMAGE_PROCESS_TIMEOUT_SECONDS = 5.0
        with pytest.raises(ImageProcessError, match="IMAGE_PROCESS_URL"):
            await submit_build(
                task_id="t1", agent_name="a", version="1",
                installer_path="/x.tgz", output_dir="/out",
            )


@pytest.mark.asyncio
async def test_submit_build_posts_payload():
    from app.services.image_process_client import submit_build

    mock_resp = MagicMock(status_code=202, text="")
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.image_process_client.settings") as settings, \
         patch("app.services.image_process_client.httpx.AsyncClient", return_value=mock_client):
        settings.IMAGE_PROCESS_URL = "http://image-process:8091"
        settings.IMAGE_PROCESS_TIMEOUT_SECONDS = 5.0
        await submit_build(
            task_id="build-1", agent_name="opencode", version="1.0",
            installer_path="/i.tgz", output_dir="/out", work_dir="/w",
        )

    mock_client.post.assert_awaited_once()
    args, kwargs = mock_client.post.await_args
    assert args[0] == "http://image-process:8091/v1/builds"
    assert kwargs["json"]["task_id"] == "build-1"
    assert "headers" not in kwargs or "Authorization" not in (kwargs.get("headers") or {})


@pytest.mark.asyncio
async def test_submit_build_connect_error():
    from app.services.image_process_client import ImageProcessError, submit_build

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.image_process_client.settings") as settings, \
         patch("app.services.image_process_client.httpx.AsyncClient", return_value=mock_client):
        settings.IMAGE_PROCESS_URL = "http://image-process:8091"
        settings.IMAGE_PROCESS_TIMEOUT_SECONDS = 5.0
        with pytest.raises(ImageProcessError, match="unreachable"):
            await submit_build(
                task_id="t", agent_name="a", version="1",
                installer_path="/x", output_dir="/o",
            )


@pytest.mark.asyncio
async def test_fetch_build_returns_status():
    from app.services.image_process_client import fetch_build

    mock_resp = MagicMock(
        status_code=200,
        json=MagicMock(return_value={
            "task_id": "build-1",
            "status": "building",
            "progress": 55,
            "image": None,
        }),
        text="",
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.image_process_client.settings") as settings, \
         patch("app.services.image_process_client.httpx.AsyncClient", return_value=mock_client):
        settings.IMAGE_PROCESS_URL = "http://image-process:8091"
        settings.IMAGE_PROCESS_TIMEOUT_SECONDS = 5.0
        remote = await fetch_build("build-1")

    assert remote is not None
    assert remote.status == "building"
    assert remote.progress == 55
    args, _kwargs = mock_client.get.await_args
    assert args[0] == "http://image-process:8091/v1/builds/build-1"


@pytest.mark.asyncio
async def test_fetch_build_404_returns_none():
    from app.services.image_process_client import fetch_build

    mock_resp = MagicMock(status_code=404, text="missing")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.image_process_client.settings") as settings, \
         patch("app.services.image_process_client.httpx.AsyncClient", return_value=mock_client):
        settings.IMAGE_PROCESS_URL = "http://image-process:8091"
        settings.IMAGE_PROCESS_TIMEOUT_SECONDS = 5.0
        assert await fetch_build("missing") is None
