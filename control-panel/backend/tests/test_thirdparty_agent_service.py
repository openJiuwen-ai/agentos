"""Unit tests for thirdparty_agent_service — upload, remote build, poll sync."""

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
        """TC-03：重复上传相同 agent_name + version → 400."""
        from fastapi import UploadFile
        from app.services.thirdparty_agent_service import (
            AgentAlreadyExistsError, ThirdpartyAgentService)

        content = _tgz_bytes({"name": "opencode-linux-x64", "version": "1.0.0"})
        pkg = UploadFile(filename="opencode.tgz", file=io.BytesIO(content))

        with patch("app.services.thirdparty_agent_service.AgentInstaller") as mock_model, \
             patch("app.thirdparty_agent.package.PackageMeta.validate_platform",
                   return_value=None):
            mock_model.exists = AsyncMock(return_value=True)
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
# Build task creation (remote image_process)
# ═══════════════════════════════════════════════════════════════════════════


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
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client:
            mock_agent.get = AsyncMock(return_value=MagicMock())
            mock_bt.try_insert = AsyncMock(return_value=(existing, False))
            mock_client.submit_build = AsyncMock()

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                agent_name="opencode", version="1.0",
                display_name="OpenCode", entrypoint="opencode")

        assert result.task_id == "build-existing"
        assert result.status == "pending"
        mock_client.submit_build.assert_not_called()

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
    async def test_normal_build_submits_to_image_process():
        """TC-01：下发成功 → status=pending，调用 image_process."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        installer = MagicMock(
            agent_name="opencode", version="1.1.0",
            installer_path="/home/agentos/users/admin/installers/opencode-1.1.0.tgz",
            uploaded_by="admin",
        )
        with patch("app.services.thirdparty_agent_service.AgentInstaller") as mock_agent, \
             patch("app.services.thirdparty_agent_service.BuildTask", wraps=BuildTask) as mock_bt, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client, \
             patch("uuid.uuid4") as mock_uuid:
            mock_agent.get = AsyncMock(return_value=installer)
            mock_agent.update = AsyncMock()
            mock_uuid.return_value.hex = "abc123def456"

            async def _try_insert(session, task, *, max_concurrent):
                return (task, True)

            mock_bt.try_insert = AsyncMock(side_effect=_try_insert)
            mock_client.submit_build = AsyncMock()

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                agent_name="opencode", version="1.1.0",
                display_name="OpenCode v2", entrypoint="opencode")

        assert result.task_id == "build-abc123def456"
        assert result.status == "pending"
        mock_client.submit_build.assert_awaited_once()
        kwargs = mock_client.submit_build.await_args.kwargs
        assert kwargs["task_id"] == "build-abc123def456"
        assert kwargs["agent_name"] == "opencode"

    @staticmethod
    async def test_image_process_unreachable_marks_failed():
        """TC-03：image-process 不可达 → 任务 failed."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.image_process_client import ImageProcessError
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        installer = MagicMock(
            agent_name="opencode", version="1.0",
            installer_path="/x.tgz", uploaded_by="admin",
        )
        with patch("app.services.thirdparty_agent_service.AgentInstaller") as mock_agent, \
             patch("app.services.thirdparty_agent_service.BuildTask", wraps=BuildTask) as mock_bt, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client, \
             patch("uuid.uuid4") as mock_uuid:
            mock_agent.get = AsyncMock(return_value=installer)
            mock_agent.update = AsyncMock()
            mock_uuid.return_value.hex = "deadbeef0001"
            mock_bt.try_insert = AsyncMock(side_effect=lambda s, t, max_concurrent=5: (t, True))
            mock_bt.mark_failed = AsyncMock()
            mock_client.submit_build = AsyncMock(
                side_effect=ImageProcessError("image_process unreachable"))

            result = await ThirdpartyAgentService().create_build_task(
                AsyncMock(),
                agent_name="opencode", version="1.0",
                display_name="OpenCode", entrypoint="opencode")

        assert result.status == "failed"
        mock_bt.mark_failed.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# Poll sync from image_process
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@_skip_sql
class TestPollSync:

    @staticmethod
    async def test_building_updates_progress():
        """active task → fetch building → mark_building + progress."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.image_process_client import RemoteBuildStatus
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-cb1", agent_name="opencode", version="1.0",
            status="pending", progress=0,
        )
        refreshed = BuildTask(
            task_id="build-cb1", agent_name="opencode", version="1.0",
            status="building", progress=40,
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client:
            mock_bt.get_by_id = AsyncMock(side_effect=[task, refreshed])
            mock_bt.mark_building = AsyncMock()
            mock_bt.update_progress = AsyncMock()
            mock_client.fetch_build = AsyncMock(
                return_value=RemoteBuildStatus(status="building", progress=40))

            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-cb1")

        mock_bt.mark_building.assert_awaited_once()
        mock_bt.update_progress.assert_awaited_once()
        assert result is not None
        assert result.status == "building"
        assert result.progress == 40

    @staticmethod
    async def test_failed_remote_marks_failed():
        """fetch failed → DB failed + error_message."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.image_process_client import RemoteBuildStatus
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-cb2", agent_name="opencode", version="1.0",
            status="building", progress=50,
        )
        refreshed = BuildTask(
            task_id="build-cb2", agent_name="opencode", version="1.0",
            status="failed", progress=50, error_message="docker boom",
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client:
            mock_bt.get_by_id = AsyncMock(side_effect=[task, refreshed])
            mock_bt.mark_failed = AsyncMock()
            mock_client.fetch_build = AsyncMock(
                return_value=RemoteBuildStatus(
                    status="failed", progress=50, error_message="docker boom"))

            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-cb2")

        mock_bt.mark_failed.assert_awaited_once()
        assert "docker boom" in mock_bt.mark_failed.await_args.kwargs["error_message"]
        assert result is not None
        assert result.status == "failed"

    @staticmethod
    async def test_done_remote_marks_done_and_registers():
        """fetch done → mark_done；registry 失败不阻断."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.image_process_client import RemoteBuildStatus
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-cb3", agent_name="opencode", version="1.0",
            status="building", progress=90,
        )
        refreshed = BuildTask(
            task_id="build-cb3", agent_name="opencode", version="1.0",
            status="done", progress=100,
            image="opencode:1.0", image_digest="sha256:abc",
        )
        installer = MagicMock(agent_name="opencode", version="1.0", uploaded_by="admin")
        svc = ThirdpartyAgentService()
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.AgentInstaller") as mock_agent, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client, \
             patch.object(
                 ThirdpartyAgentService, "_register_image",
                 new_callable=AsyncMock,
                 side_effect=RuntimeError("down"),
             ) as mock_reg:
            mock_bt.get_by_id = AsyncMock(side_effect=[task, refreshed])
            mock_bt.mark_done = AsyncMock()
            mock_agent.get = AsyncMock(return_value=installer)
            mock_agent.update = AsyncMock()
            mock_client.fetch_build = AsyncMock(
                return_value=RemoteBuildStatus(
                    status="done", progress=100,
                    image="opencode:1.0", image_digest="sha256:abc",
                    image_path="/images/opencode-1.0.tar",
                ))

            result = await svc.get_build_task(AsyncMock(), "build-cb3")

        mock_bt.mark_done.assert_awaited_once()
        mock_reg.assert_awaited_once()
        assert result is not None
        assert result.status == "done"


# ═══════════════════════════════════════════════════════════════════════════
# Build status query
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
        """TC-07：构建完成 → GET /build_tasks/{id} 返回 done（不再拉取）."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-done", agent_name="opencode", version="1.0",
            status="done", progress=100,
            image="opencode:1.0", image_digest="sha256:abc",
            started_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client:
            mock_bt.get_by_id = AsyncMock(return_value=task)
            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-done")

        assert result is not None
        assert result.status == "done"
        assert result.progress == 100
        assert result.registered is True
        assert result.image == "opencode:1.0"
        mock_client.fetch_build.assert_not_called()

    @staticmethod
    async def test_building_task_keeps_db_when_remote_missing():
        """TC-06：远端暂不可达 → 返回 DB 快照."""
        from app.models.thirdparty_agent import BuildTask
        from app.services.thirdparty_agent_service import ThirdpartyAgentService

        task = BuildTask(
            task_id="build-progress", agent_name="opencode", version="1.0",
            status="building", progress=45,
            started_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        )
        with patch("app.services.thirdparty_agent_service.BuildTask") as mock_bt, \
             patch("app.services.thirdparty_agent_service.image_process_client") as mock_client:
            mock_bt.get_by_id = AsyncMock(return_value=task)
            mock_client.fetch_build = AsyncMock(return_value=None)
            result = await ThirdpartyAgentService().get_build_task(AsyncMock(), "build-progress")

        assert result is not None
        assert result.status == "building"
        assert result.progress == 45
        assert result.registered is False
