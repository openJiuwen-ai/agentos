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
        with patch.object(svc, "check_disk_space", return_value=None):
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
             patch("app.services.thirdparty_agent_service.check_prerequisites",
                   new=AsyncMock(return_value=[])), \
             patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("asyncio.create_task"):
            mock_agent.get = AsyncMock(return_value=MagicMock())
            mock_bt.try_insert = AsyncMock(return_value=(existing, False))

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

    @staticmethod
    async def test_base_image_missing_raises_503():
        """check_prerequisites fails → BuildPreconditionError."""
        from app.services.thirdparty_agent_service import (
            BuildPreconditionError, ThirdpartyAgentService)

        with patch(
            "app.services.thirdparty_agent_service.AgentInstaller"
        ) as mock_agent, \
             patch(
            "app.services.thirdparty_agent_service.check_prerequisites",
            new=AsyncMock(return_value=["base image 'agent-base:1.0' not found"]),
        ):
            mock_agent.get = AsyncMock(return_value=MagicMock())
            svc = ThirdpartyAgentService()
            with pytest.raises(BuildPreconditionError) as exc:
                await svc.create_build_task(
                    AsyncMock(),
                    agent_name="test", version="1.0",
                    display_name="Test", entrypoint="test")
            assert "agent-base:1.0" in str(exc.value)


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


# ── Register Image ───────────────────────────────────────────────────────


@pytest.mark.asyncio
@_skip_sql
class TestRegisterImage:

    @staticmethod
    async def test_framework_field_is_entrypoint():
        """register_image sends installer.entrypoint as the 'framework' field."""
        import httpx
        from app.image_process.build import BuildResult
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        installer = MagicMock()
        installer.agent_name = "opencode"
        installer.entrypoint = "custom-entry"
        installer.version = "1.0.0"
        installer.uploaded_by = "admin"

        result = BuildResult(
            image="opencode:1.0",
            image_digest="sha256:abc",
            image_path="/tmp/opencode-1.0.tar.gz",
            base_image="agent-base:1.0",
        )

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "registered"}
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            await ThirdpartyAgentService.register_image(installer, result)

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["framework"] == "custom-entry"
        assert payload["framework_version"] == "1.0.0"


# ── Disk Space Check ────────────────────────────────────────────────────


@pytest.mark.asyncio
@_skip_sql
class TestCheckDiskSpace:

    @staticmethod
    async def test_raises_when_insufficient_space():
        """When free space is less than needed, raises InsufficientDiskSpaceError."""
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
        """When free space >= needed, does not raise."""
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        mock_usage = MagicMock(free=10000)
        with patch("app.services.thirdparty_agent_service.shutil.disk_usage",
                   return_value=mock_usage):
            with patch("app.services.thirdparty_agent_service.Path.mkdir"):
                # Should not raise
                ThirdpartyAgentService.check_disk_space("user", 5000)


# ── Save Installer File ─────────────────────────────────────────────────


@pytest.mark.asyncio
@_skip_sql
class TestSaveInstallerFile:

    @staticmethod
    async def test_saves_file_and_returns_path():
        """Writes content to the expected path and returns it as a string."""
        from app.thirdparty_agent.package import PackageMeta
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        meta = PackageMeta(
            agent_name="test-agent", version="2.0",
            display_name="Test Agent", entrypoint="test-agent",
            os="linux", arch="x64", libc="gnu",
        )
        content = b"fake-tgz-content"

        with patch("app.services.thirdparty_agent_service.Path.mkdir"):
            with patch("app.services.thirdparty_agent_service.Path.write_bytes") as mock_write:
                result = ThirdpartyAgentService.save_installer_file(
                    content, meta, "admin")

        assert isinstance(result, str)
        assert result.endswith("test-agent-2.0.tgz")
        mock_write.assert_called_once_with(content)

    @staticmethod
    async def test_removes_file_on_write_error():
        """If write_bytes fails, the partial file is removed via unlink."""
        from app.thirdparty_agent.package import PackageMeta
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        meta = PackageMeta(
            agent_name="test", version="1.0",
            display_name="Test", entrypoint="test",
            os="linux", arch="x64", libc="gnu",
        )

        with patch("app.services.thirdparty_agent_service.Path.mkdir"):
            with patch("app.services.thirdparty_agent_service.Path.write_bytes",
                       side_effect=OSError("disk full")):
                with patch("app.services.thirdparty_agent_service.Path.unlink") as mock_unlink:
                    with pytest.raises(OSError, match="disk full"):
                        ThirdpartyAgentService.save_installer_file(b"x", meta, "admin")
                    mock_unlink.assert_called_once()
