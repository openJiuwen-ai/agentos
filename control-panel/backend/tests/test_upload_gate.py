"""Unit tests for publish gate and lock behaviour."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.thirdparty_agent.exceptions import InvalidUploadError, PackageTooLargeError
from app.thirdparty_agent.local_file_cleaner import LocalFileCleaner
from app.thirdparty_agent.upload_gate import (
    UploadGate,
    artifact_metadata_path,
    read_original_filename,
)


def _upload(name: str, data: bytes, size: int | None = None):
    from fastapi import UploadFile

    return UploadFile(
        filename=name,
        file=io.BytesIO(data),
        size=size if size is not None else len(data),
    )


@pytest.mark.asyncio
async def test_gate_accepts_artifact_without_format_assumption(tmp_path):
    gate = UploadGate()
    accepted = await gate.persist(_upload("x.bin", b"abc"), tmp_path)
    assert accepted.package_path.endswith(".artifact")


@pytest.mark.asyncio
async def test_gate_rejects_empty_artifact(tmp_path):
    gate = UploadGate()
    with pytest.raises(InvalidUploadError, match="empty artifact"):
        await gate.persist(_upload("x.bin", b""), tmp_path)


@pytest.mark.asyncio
async def test_gate_rejects_path_in_name(tmp_path):
    gate = UploadGate()
    with pytest.raises(InvalidUploadError):
        await gate.persist(_upload("../x.bin", b"abc"), tmp_path)


@pytest.mark.asyncio
async def test_gate_rejects_too_large(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "THIRDPARTY_AGENT_INSTALLER_MAX_BYTES", 8)
    gate = UploadGate()
    with pytest.raises(PackageTooLargeError):
        await gate.persist(_upload("x.tgz", b"0123456789"), tmp_path)


@pytest.mark.asyncio
async def test_gate_persists_digest_named_file(tmp_path):
    gate = UploadGate()
    accepted = await gate.persist(_upload("pkg.tgz", b"hello-tgz"), tmp_path)
    assert accepted.content_digest
    assert accepted.package_path.endswith(".artifact")
    assert accepted.original_filename == "pkg.tgz"
    from pathlib import Path

    assert Path(accepted.package_path).read_bytes() == b"hello-tgz"
    assert artifact_metadata_path(accepted.package_path).is_file()
    assert read_original_filename(accepted.package_path) == "pkg.tgz"


@pytest.mark.asyncio
async def test_package_cleanup_removes_artifact_and_metadata(tmp_path):
    accepted = await UploadGate().persist(_upload("original.zip", b"data"), tmp_path)
    metadata = artifact_metadata_path(accepted.package_path)

    LocalFileCleaner().remove_package(accepted.package_path)

    from pathlib import Path

    assert not Path(accepted.package_path).exists()
    assert not metadata.exists()


@pytest.mark.asyncio
async def test_publish_refuses_when_locked(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.thirdparty_agent_service import (
        PublishParams,
        ThirdpartyAgentService,
    )
    from app.thirdparty_agent.exceptions import PackageLockedError

    monkeypatch.setattr(settings, "THIRDPARTY_AGENT_PACKAGE_DIR", str(tmp_path))
    factory = AsyncMock()
    registry = AsyncMock()
    svc = ThirdpartyAgentService(factory=factory, registry=registry)
    with (
        patch(
            "app.services.thirdparty_agent_service.BuildTask.try_insert",
            AsyncMock(
                return_value=(MagicMock(), False),
            ),
        ),
        patch("app.services.thirdparty_agent_service.asyncio.create_task"),
    ):
        with pytest.raises(PackageLockedError):
            await svc.publish(
                AsyncMock(),
                _upload("a.tgz", b"data"),
                PublishParams(uploaded_by="admin", launch_command="demo-agent"),
            )
