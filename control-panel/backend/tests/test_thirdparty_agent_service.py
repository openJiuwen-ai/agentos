"""Unit tests for thirdparty_agent_service."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _has_sqlalchemy():
    from importlib.util import find_spec
    return find_spec("sqlalchemy") is not None


_skip_sql = pytest.mark.skipif(not _has_sqlalchemy(), reason="sqlalchemy not installed")


def _tgz_bytes(package_json: dict | None) -> bytes:
    import json
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        if package_json is not None:
            payload = json.dumps(package_json).encode()
            info = tarfile.TarInfo(name="package/package.json")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


# ── Upload ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@_skip_sql
class TestUpload:

    @staticmethod
    async def test_package_too_large_raises():
        from fastapi import UploadFile
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, PackageTooLargeError)

        pkg = UploadFile(
            filename="opencode.tgz",
            file=io.BytesIO(b"x" * 10),
            size=524_288_001,
        )
        svc = ThirdpartyAgentService()
        with pytest.raises(PackageTooLargeError) as exc:
            await svc.upload(AsyncMock(), "admin", pkg)
        assert exc.value.size == 524_288_001

    @staticmethod
    async def test_invalid_package_raises():
        from fastapi import UploadFile
        from app.thirdparty_agent.package import MissingFieldError
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        content = _tgz_bytes({"version": "1.0.0"})  # missing "name"
        pkg = UploadFile(filename="bad.tgz", file=io.BytesIO(content))

        svc = ThirdpartyAgentService()
        with pytest.raises(MissingFieldError):
            await svc.upload(AsyncMock(), "admin", pkg)


# ── Build ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@_skip_sql
class TestCreateBuildTask:

    @staticmethod
    async def test_returns_existing_task_if_pending():
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        existing = BuildTask(
            task_id="build-existing", agent_name="opencode", version="1.0",
            status="pending", progress=0,
        )
        with patch("app.services.thirdparty_agent_service.AgentInstaller") as mock_agent, \
             patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("asyncio.create_task"):
            mock_agent.get = AsyncMock(return_value=MagicMock())
            mock_bt.get_by_name = AsyncMock(return_value=[existing])

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                agent_name="opencode", version="1.0",
                display_name="OpenCode", entrypoint="opencode")

        assert result.task_id == "build-existing"
        assert result.status == "pending"

    @staticmethod
    async def test_agent_not_found_raises():
        from app.services.thirdparty_agent_service import AgentNotFoundError, ThirdpartyAgentService

        with patch("app.services.thirdparty_agent_service.AgentInstaller") as mock_agent:
            mock_agent.get = AsyncMock(return_value=None)
            with pytest.raises(AgentNotFoundError) as exc:
                await ThirdpartyAgentService().create_build_task(
                    AsyncMock(),
                    agent_name="nobody", version="1.0",
                    display_name="Nobody", entrypoint="nobody")
            assert exc.value.agent_name == "nobody"


# ── Status ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@_skip_sql
class TestGetBuildTask:

    @staticmethod
    async def test_no_task_returns_none():
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt:
            mock_bt.get_by_id = AsyncMock(return_value=None)
            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "nonexistent-task-id")
        assert result is None

    @staticmethod
    async def test_done_task():
        from datetime import datetime, timezone
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-done", agent_name="opencode", version="1.0",
            status="done", progress=100,
            image="opencode:1.0", image_digest="sha256:abc",
            started_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt:
            mock_bt.get_by_id = AsyncMock(return_value=task)
            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-done")

        assert result is not None
        assert result.status == "done"
        assert result.progress == 100
        assert result.registered is True
        assert result.image == "opencode:1.0"

    @staticmethod
    async def test_building_task():
        from datetime import datetime, timezone
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-progress", agent_name="opencode", version="1.0",
            status="building", progress=45,
            started_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt:
            mock_bt.get_by_id = AsyncMock(return_value=task)
            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-progress")

        assert result is not None
        assert result.status == "building"
        assert result.progress == 45
        assert result.registered is False
