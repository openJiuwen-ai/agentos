"""Unit tests for thirdparty_agent.package — pure module, no framework dependencies."""

import io
import json
import tarfile

import pytest

from app.thirdparty_agent.package import (
    extract_package_meta,
    InvalidArchiveError,
    MissingFieldError,
    MissingPackageJsonError,
    PackageMeta,
    PlatformMismatchError,
)


def _tgz_bytes(package_json: dict | None) -> bytes:
    """Build an in-memory .tgz with an optional package/package.json entry."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        if package_json is not None:
            payload = json.dumps(package_json).encode()
            info = tarfile.TarInfo(name="package/package.json")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


class TestExtractPackageMeta:

    @staticmethod
    def test_valid_package_json():
        content = _tgz_bytes({
            "name": "@scope/opencode-linux-x64",
            "version": "1.0.0",
            "displayName": "OpenCode",
            "bin": "opencode",
        })
        meta = extract_package_meta(content)
        assert meta is not None
        assert meta.agent_name == "opencode"  # scope stripped
        assert meta.version == "1.0.0"
        assert meta.display_name == "OpenCode"
        assert meta.entrypoint == "opencode"

    @staticmethod
    def test_missing_name_raises():
        content = _tgz_bytes({"version": "1.0.0"})
        with pytest.raises(MissingFieldError, match="missing 'name'"):
            extract_package_meta(content)

    @staticmethod
    def test_missing_version_raises():
        content = _tgz_bytes({"name": "opencode-linux-x64"})
        with pytest.raises(MissingFieldError, match="missing 'version'"):
            extract_package_meta(content)

    @staticmethod
    def test_non_tgz_content_raises():
        with pytest.raises(InvalidArchiveError, match="invalid tar.gz"):
            extract_package_meta(b"not a gzip file")

    @staticmethod
    def test_empty_tgz_raises():
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz"):
            pass
        with pytest.raises(MissingPackageJsonError, match="no package/package.json"):
            extract_package_meta(buf.getvalue())

    @staticmethod
    def test_tgz_without_package_json_raises():
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            payload = b"hello"
            info = tarfile.TarInfo(name="README.md")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        with pytest.raises(MissingPackageJsonError, match="no package/package.json"):
            extract_package_meta(buf.getvalue())

    @staticmethod
    def test_bin_as_dict():
        content = _tgz_bytes({
            "name": "opencode-linux-x64",
            "version": "1.0.0",
            "bin": {"opencode": "bin/opencode.js"},
        })
        meta = extract_package_meta(content)
        assert meta is not None
        assert meta.entrypoint == "opencode"

    @staticmethod
    def test_display_name_falls_back_to_name():
        content = _tgz_bytes({"name": "opencode-linux-x64", "version": "1.0.0"})
        meta = extract_package_meta(content)
        assert meta is not None
        assert meta.display_name == "opencode-linux-x64"


class TestPlatformMismatchError:
    """validate_platform() raises PlatformMismatchError on OS/arch/libc mismatch."""

    @staticmethod
    def test_validate_platform_raises_on_mismatch():
        meta = PackageMeta(
            agent_name="test", version="1.0",
            display_name="Test", entrypoint="test",
            os="nonexistent-os", arch="x64", libc="gnu",
        )
        with pytest.raises(PlatformMismatchError, match="platform mismatch"):
            meta.validate_platform()
