"""API tests for image_process service."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.factory.models import BuildResult, FactoryError
from app.main import app
from tests.conftest import write_npm_tgz


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_tasks():
    from app.tasks import clear_tasks

    clear_tasks()
    yield
    clear_tasks()


@pytest.mark.asyncio
async def test_health_ok_when_docker_available():
    with patch("app.tasks.docker_available", AsyncMock(return_value=True)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["docker"] is True


@pytest.mark.asyncio
async def test_health_503_when_docker_unavailable():
    with patch("app.tasks.docker_available", AsyncMock(return_value=False)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/health")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_create_build_rejects_missing_package(tmp_path: Path):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/builds",
            json={
                "package_path": str(tmp_path / "missing.tgz"),
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_build_and_reach_done(tmp_path: Path):
    installer = write_npm_tgz(tmp_path / "pkg.tgz")

    async def _fake_build(package_path, options=None, *, request_id, on_progress=None):
        if on_progress:
            await on_progress(10)
            await on_progress(50)
            await on_progress(90)
        return BuildResult(
            name="demo",
            version="1.0.0",
            image_ref="demo:1.0.0",
            archive_path=str(tmp_path / "demo-1.0.0.tar.gz"),
            runtime_spec={"sandbox_type": "docker"},
            recipe_id="npm_tgz_on_base",
            base_ref="agent-base:1.0",
            image_digest="sha256:abc",
            image_module_version="1.0",
        )

    with (
        patch("app.tasks._factory") as mock_factory,
        patch("app.tasks.docker_available", AsyncMock(return_value=True)),
    ):
        mock_factory.build_from_path = AsyncMock(side_effect=_fake_build)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            create = await client.post(
                "/v1/builds",
                json={
                    "package_path": str(installer),
                    "request_id": "build-ok",
                },
            )
            assert create.status_code == 202
            assert create.json()["request_id"] == "build-ok"

            import asyncio

            for _ in range(50):
                status = await client.get("/v1/builds/build-ok")
                if status.json()["status"] in ("done", "failed"):
                    break
                await asyncio.sleep(0.02)

            status = await client.get("/v1/builds/build-ok")

    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    assert body["progress"] == 100
    assert body["image_ref"] == "demo:1.0.0"
    assert body["recipe_id"] == "npm_tgz_on_base"
    assert body["name"] == "demo"


@pytest.mark.asyncio
async def test_create_build_failure_sets_failed(tmp_path: Path):
    installer = write_npm_tgz(tmp_path / "pkg.tgz")

    with (
        patch("app.tasks._factory") as mock_factory,
        patch("app.tasks.docker_available", AsyncMock(return_value=True)),
    ):
        mock_factory.build_from_path = AsyncMock(side_effect=FactoryError("boom"))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            create = await client.post(
                "/v1/builds",
                json={
                    "package_path": str(installer),
                    "request_id": "build-fail",
                },
            )
            assert create.status_code == 202

            import asyncio

            for _ in range(50):
                status = await client.get("/v1/builds/build-fail")
                if status.json()["status"] in ("done", "failed"):
                    break
                await asyncio.sleep(0.02)

            status = await client.get("/v1/builds/build-fail")

    assert status.json()["status"] == "failed"
    assert "boom" in (status.json()["error_message"] or "")


@pytest.mark.asyncio
async def test_remove_image_calls_factory():
    with patch("app.tasks._factory") as mock_factory:
        mock_factory.remove_loaded_image = AsyncMock()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/v1/images/remove", json={"tag": "demo:1.0.0"})
    assert resp.status_code == 200
    assert resp.json()["tag"] == "demo:1.0.0"
    mock_factory.remove_loaded_image.assert_awaited_once_with("demo:1.0.0")
