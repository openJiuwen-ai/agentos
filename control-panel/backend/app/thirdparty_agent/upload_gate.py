"""Generic upload gate: safe name, size, disk, digest, and atomic persist."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.thirdparty_agent.exceptions import (
    InsufficientDiskSpaceError,
    InvalidUploadError,
    PackageTooLargeError,
)

_DISK_MARGIN = 50 * 1024 * 1024


@dataclass(frozen=True)
class AcceptedPackage:
    content_digest: str
    package_path: str
    size: int
    original_filename: str


def artifact_metadata_path(package_path: str | Path) -> Path:
    """Return the trusted sidecar path for a persisted artifact."""
    return Path(package_path).with_suffix(".metadata.json")


def read_original_filename(package_path: str | Path) -> str:
    """Read the display-only upload name without trusting it as a local path."""
    metadata = artifact_metadata_path(package_path)
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Path(package_path).name
    name = data.get("original_filename") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else Path(package_path).name


class UploadGate:
    """Validate constraints shared by every uploaded artifact.

    Extend this gate only with format-independent transport/storage checks,
    such as filename safety, size, disk capacity, digesting, and atomic writes.
    Artifact-specific validation (archive format, package layout, platform,
    signature, and build compatibility) belongs to the matching image-process
    Recipe so adding a new artifact type does not require changing this gate.
    """

    @staticmethod
    def accept_meta(uploaded: UploadFile) -> None:
        raw = uploaded.filename or "artifact"
        if "/" in raw or "\\" in raw or raw in (".", ".."):
            raise InvalidUploadError("unsafe filename")
        if (
            uploaded.size
            and uploaded.size > settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES
        ):
            raise PackageTooLargeError(
                uploaded.size,
                settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES,
            )

    @staticmethod
    def check_disk(dest_dir: Path, needed: int) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(dest_dir)
        if usage.free < needed + _DISK_MARGIN:
            raise InsufficientDiskSpaceError(
                f"not enough disk space: {usage.free} free, {needed} required"
            )

    async def persist(self, uploaded: UploadFile, dest_dir: Path) -> AcceptedPackage:
        self.accept_meta(uploaded)
        original_filename = uploaded.filename or "artifact"
        dest_dir.mkdir(parents=True, exist_ok=True)
        content = await uploaded.read()
        if not content:
            raise InvalidUploadError("empty artifact")
        if len(content) > settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES:
            raise PackageTooLargeError(
                len(content),
                settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES,
            )
        self.check_disk(dest_dir, len(content))
        digest = hashlib.sha256(content).hexdigest()
        dest = dest_dir / f"{digest}.artifact"
        tmp = dest.with_suffix(".artifact.tmp")
        metadata = artifact_metadata_path(dest)
        metadata_tmp = metadata.with_suffix(".json.tmp")
        try:
            tmp.write_bytes(content)
            metadata_tmp.write_text(
                json.dumps(
                    {"original_filename": original_filename},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, dest)
            os.replace(metadata_tmp, metadata)
        except Exception:
            tmp.unlink(missing_ok=True)
            metadata_tmp.unlink(missing_ok=True)
            raise
        return AcceptedPackage(
            content_digest=digest,
            package_path=str(dest),
            size=len(content),
            original_filename=original_filename,
        )
