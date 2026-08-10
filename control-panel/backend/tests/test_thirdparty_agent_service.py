"""Unit tests for thirdparty_agent_service — upload, build, query."""

import asyncio
import io
from datetime import datetime, timezone
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


# ═══════════════════════════════════════════════════════════════════════════
# Upload validation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@_skip_sql
class TestUpload:

    @staticmethod
    async def test_package_too_large_raises():
        from fastapi import UploadFile
        from app.services.thirdparty_agent_service import (
            PackageTooLargeError, ThirdpartyAgentService)

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
    async def test_duplicate_upload_raises():
        """TC-03：重复上传相同 installer_path → 400."""
        from fastapi import UploadFile
        from app.services.thirdparty_agent_service import (
            AgentAlreadyExistsError, ThirdpartyAgentService)

        content = _tgz_bytes({"name": "opencode-linux-x64", "version": "1.0.0"})
        pkg = UploadFile(filename="opencode.tgz", file=io.BytesIO(content))

        with patch("app.services.thirdparty_agent_service.AgentRegistration") as mock_model, \
             patch("app.thirdparty_agent.package.PackageMeta.validate_platform",
                   return_value=None):
            mock_model.exists_by_path = AsyncMock(return_value=True)
            svc = ThirdpartyAgentService()
            with patch.object(svc, "check_disk_space", return_value=None):
                with pytest.raises(AgentAlreadyExistsError) as exc:
                    await svc.upload(AsyncMock(), "admin", pkg)
            assert exc.value.agent_name == "opencode"
            assert exc.value.version == "1.0.0"

    @staticmethod
    async def test_invalid_package_raises():
        from fastapi import UploadFile
        from app.thirdparty_agent.package import MissingFieldError
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        content = _tgz_bytes({"version": "1.0.0"})  # missing "name"
        pkg = UploadFile(filename="bad.tgz", file=io.BytesIO(content))

        svc = ThirdpartyAgentService()
        with patch.object(svc, "check_disk_space", return_value=None):
            with pytest.raises(MissingFieldError):
                await svc.upload(AsyncMock(), "admin", pkg)

    @staticmethod
    async def test_upload_rejects_existing_registration(tmp_path, monkeypatch):
        """Upload should raise AgentAlreadyExistsError when installer_path already registered."""
        from fastapi import UploadFile
        from app.config import settings
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, AgentAlreadyExistsError)
        from app.thirdparty_agent.package import PackageMeta

        monkeypatch.setattr(settings, "AGENTOS_HOME_BASE", str(tmp_path))

        svc = ThirdpartyAgentService()
        svc.check_disk_space = MagicMock()

        meta = PackageMeta(
            agent_name="opencode", version="1.0",
            display_name="OpenCode", entrypoint="opencode",
            os="linux", arch="x64", libc="gnu")
        monkeypatch.setattr(
            "app.services.thirdparty_agent_service.extract_package_meta",
            lambda content: meta)

        with patch("app.services.thirdparty_agent_service.AgentRegistration") as mock_reg:
            mock_reg.exists_by_path = AsyncMock(return_value=True)
            pkg = UploadFile(filename="test.tgz", file=io.BytesIO(b"dummy"))
            with pytest.raises(AgentAlreadyExistsError):
                await svc.upload(AsyncMock(), "testuser", pkg)


# ═══════════════════════════════════════════════════════════════════════════
# Disk space check
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@_skip_sql
class TestCheckDiskSpace:

    @staticmethod
    async def test_raises_when_insufficient_space():
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, InsufficientDiskSpaceError)

        mock_usage = MagicMock(free=1000)
        with patch("app.services.thirdparty_agent_service.shutil.disk_usage",
                   return_value=mock_usage):
            with patch("app.services.thirdparty_agent_service.Path.mkdir"):
                with pytest.raises(InsufficientDiskSpaceError) as exc:
                    ThirdpartyAgentService.check_disk_space("user", 2000)
                assert "not enough disk space" in str(exc.value)
                assert "1000 free" in str(exc.value)
                assert "2000 required" in str(exc.value)

    @staticmethod
    async def test_passes_when_sufficient_space():
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        mock_usage = MagicMock(free=10000)
        with patch("app.services.thirdparty_agent_service.shutil.disk_usage",
                   return_value=mock_usage):
            with patch("app.services.thirdparty_agent_service.Path.mkdir"):
                ThirdpartyAgentService.check_disk_space("user", 5000)


# ═══════════════════════════════════════════════════════════════════════════
# Build task creation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@_skip_sql
class TestCreateBuildTask:

    @staticmethod
    async def test_returns_existing_task_if_pending():
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import CreateBuildTaskParams, ThirdpartyAgentService

        existing = BuildTask(
            task_id="build-existing", installer_path="/home/admin/installers/opencode-1.0.tgz",
            status="pending", progress=0,
        )
        with patch("os.path.isfile", return_value=True), \
             patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.asyncio.create_task") as mock_create:
            mock_bt.try_insert = AsyncMock(return_value=(existing, False))

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                CreateBuildTaskParams(agent_name="opencode", version="1.0",
                                      display_name="OpenCode", entrypoint="opencode",
                                      uploaded_by="admin"))

        assert result.task_id == "build-existing"
        assert result.status == "pending"
        mock_create.assert_not_called()

    @staticmethod
    async def test_agent_not_found_raises():
        """Should raise AgentNotFoundError when tgz file doesn't exist."""
        from app.services.thirdparty_agent_service import (
            AgentNotFoundError, CreateBuildTaskParams, ThirdpartyAgentService)

        with patch("os.path.isfile",
                   return_value=False):
            with pytest.raises(AgentNotFoundError) as exc:
                await ThirdpartyAgentService().create_build_task(
                    AsyncMock(),
                    CreateBuildTaskParams(agent_name="nobody", version="1.0",
                                          display_name="Nobody", entrypoint="nobody",
                                          uploaded_by="admin"))
            assert exc.value.agent_name == "nobody"

    @staticmethod
    async def test_normal_build_creates_task_and_launches_background():
        """TC-01：create_build_task returns pending task and spawns _run_build."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import CreateBuildTaskParams, ThirdpartyAgentService

        with patch("os.path.isfile", return_value=True), \
             patch("app.services.thirdparty_agent_service.BuildTask", wraps=BuildTask) as mock_bt, \
             patch("app.services.thirdparty_agent_service.asyncio.create_task") as mock_create, \
             patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123def456"

            async def _try_insert(session, task, *, max_concurrent):
                return (task, True)

            mock_bt.try_insert = AsyncMock(side_effect=_try_insert)

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                CreateBuildTaskParams(agent_name="opencode", version="1.1.0",
                                      display_name="OpenCode v2", entrypoint="opencode",
                                      uploaded_by="admin"))

        assert result.task_id == "build-abc123def456"
        assert result.status == "pending"
        mock_create.assert_called_once()

    @staticmethod
    async def test_create_build_task_when_insert_blocked():
        """When try_insert returns existing task, create_task is not spawned."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import CreateBuildTaskParams, ThirdpartyAgentService

        existing = BuildTask(
            task_id="build-existing", installer_path="/home/admin/installers/opencode-1.0.tgz",
            status="building", progress=50,
        )
        with patch("os.path.isfile", return_value=True), \
             patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.asyncio.create_task") as mock_create:
            mock_bt.try_insert = AsyncMock(return_value=(existing, False))

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                CreateBuildTaskParams(agent_name="opencode", version="1.0",
                                      display_name="OpenCode", entrypoint="opencode",
                                      uploaded_by="admin"))

        assert result.task_id == "build-existing"
        assert result.status == "building"
        mock_create.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Build status query (DB snapshot only — no polling)
# ═══════════════════════════════════════════════════════════════════════════


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
        """TC-07：构建完成 → GET /build_tasks/{id} 返回 done."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-done", installer_path="/home/admin/installers/opencode-1.0.tgz",
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
    async def test_building_task_returns_db_snapshot():
        """Building task returns current DB state (no remote polling)."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-progress", installer_path="/home/admin/installers/opencode-1.0.tgz",
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

    @staticmethod
    async def test_failed_task():
        """Failed task returns error info from DB."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-fail", installer_path="/home/admin/installers/opencode-1.0.tgz",
            status="failed", progress=50, error_message="build error",
            started_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 15, 12, 3, tzinfo=timezone.utc),
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt:
            mock_bt.get_by_id = AsyncMock(return_value=task)
            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-fail")

        assert result is not None
        assert result.status == "failed"
        assert result.error_message == "build error"
