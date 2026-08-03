"""API tests for image_process service (TB-01 ~ TB-04)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.builder import BuildError, BuildResult
from app.main import app


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
    """TB-01: docker available → 200."""
    with patch("app.tasks.docker_available", AsyncMock(return_value=True)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["docker"] is True


@pytest.mark.asyncio
async def test_health_503_when_docker_unavailable():
    """TB-01: docker unavailable → 503."""
    with patch("app.tasks.docker_available", AsyncMock(return_value=False)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            resp = await client.get("/health")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_create_build_rejects_bad_name(tmp_path: Path):
    """TB-02: invalid agent/version → 400."""
    installer = tmp_path / "pkg.tgz"
    installer.write_bytes(b"x")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as client:
        resp = await client.post("/v1/builds", json={
            "task_id": "build-1",
            "agent_name": "bad;name",
            "version": "1.0",
            "installer_path": str(installer),
            "output_dir": str(tmp_path / "out"),
        })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_build_rejects_missing_installer(tmp_path: Path):
    """TB-02: missing installer → 400."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as client:
        resp = await client.post("/v1/builds", json={
            "task_id": "build-2",
            "agent_name": "opencode",
            "version": "1.0",
            "installer_path": str(tmp_path / "missing.tgz"),
            "output_dir": str(tmp_path / "out"),
        })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_build_and_reach_done(tmp_path: Path):
    """TB-03: enqueue → done (status queryable via GET)."""
    installer = tmp_path / "pkg.tgz"
    installer.write_bytes(b"fake")
    output_dir = tmp_path / "out"

    async def _fake_build(params):
        if params.on_progress:
            await params.on_progress(10)
            await params.on_progress(50)
            await params.on_progress(90)
        return BuildResult(
            image=f"{params.agent_name}:{params.version}",
            image_digest="sha256:abc",
            image_path=str(output_dir / f"{params.agent_name}-{params.version}.tar.gz"),
            base_image="agent-base:1.0",
        )

    with patch("app.tasks.build", AsyncMock(side_effect=_fake_build)), \
         patch("app.tasks.docker_available", AsyncMock(return_value=True)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            create = await client.post("/v1/builds", json={
                "task_id": "build-ok",
                "agent_name": "opencode",
                "version": "1.0",
                "installer_path": str(installer),
                "output_dir": str(output_dir),
            })
            assert create.status_code == 202

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
    assert body["image"] == "opencode:1.0"


@pytest.mark.asyncio
async def test_create_build_failure_sets_failed(tmp_path: Path):
    """TB-04: build failure → failed status + error_message."""
    installer = tmp_path / "pkg.tgz"
    installer.write_bytes(b"fake")

    with patch("app.tasks.build", AsyncMock(side_effect=BuildError("boom"))), \
         patch("app.tasks.docker_available", AsyncMock(return_value=True)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            create = await client.post("/v1/builds", json={
                "task_id": "build-fail",
                "agent_name": "opencode",
                "version": "1.0",
                "installer_path": str(installer),
                "output_dir": str(tmp_path / "out"),
            })
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
