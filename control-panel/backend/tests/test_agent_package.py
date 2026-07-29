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


class TestElfDetection:
    """Entrypoint fallback via ELF magic-number detection."""

    @staticmethod
    def test_no_bin_falls_back_to_elf():
        """When package.json has no 'bin', the first ELF file's basename
        becomes the entrypoint."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            # package.json without bin
            pkg = json.dumps({
                "name": "@scope/mytool-linux-x64",
                "version": "2.0.0",
            }).encode()
            pkg_info = tarfile.TarInfo(name="package/package.json")
            pkg_info.size = len(pkg)
            tf.addfile(pkg_info, io.BytesIO(pkg))
            # ELF executable
            elf_payload = b"\x7fELF\x00\x00\x00\x00\x00\x00\x00\x00extra"
            elf_info = tarfile.TarInfo(name="package/bin/mytool")
            elf_info.size = len(elf_payload)
            tf.addfile(elf_info, io.BytesIO(elf_payload))
            # Non-ELF regular file
            txt_payload = b"just a text file"
            txt_info = tarfile.TarInfo(name="package/README.md")
            txt_info.size = len(txt_payload)
            tf.addfile(txt_info, io.BytesIO(txt_payload))

        meta = extract_package_meta(buf.getvalue())
        assert meta.entrypoint == "mytool"

    @staticmethod
    def test_bin_takes_priority_over_elf():
        """When package.json has 'bin', ELF scan is skipped."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            pkg = json.dumps({
                "name": "mytool-linux-x64",
                "version": "1.0.0",
                "bin": "explicit-entry",
            }).encode()
            pkg_info = tarfile.TarInfo(name="package/package.json")
            pkg_info.size = len(pkg)
            tf.addfile(pkg_info, io.BytesIO(pkg))
            # ELF file — should be ignored because bin is present
            elf_payload = b"\x7fELF" + b"\x00" * 20
            elf_info = tarfile.TarInfo(name="package/bin/ignored")
            elf_info.size = len(elf_payload)
            tf.addfile(elf_info, io.BytesIO(elf_payload))

        meta = extract_package_meta(buf.getvalue())
        assert meta.entrypoint == "explicit-entry"

    @staticmethod
    def test_no_elf_no_bin_returns_empty():
        """When neither bin nor ELF exists, entrypoint is ''."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            pkg = json.dumps({
                "name": "mytool-linux-x64",
                "version": "1.0.0",
            }).encode()
            pkg_info = tarfile.TarInfo(name="package/package.json")
            pkg_info.size = len(pkg)
            tf.addfile(pkg_info, io.BytesIO(pkg))
            # No ELF file in the archive
            txt_payload = b"hello"
            txt_info = tarfile.TarInfo(name="package/readme.txt")
            txt_info.size = len(txt_payload)
            tf.addfile(txt_info, io.BytesIO(txt_payload))

        meta = extract_package_meta(buf.getvalue())
        assert meta.entrypoint == ""

    @staticmethod
    def test_elf_basename_only_no_directory():
        """Only the filename is returned, not the full path."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            pkg = json.dumps({
                "name": "mytool-linux-x64",
                "version": "1.0.0",
            }).encode()
            pkg_info = tarfile.TarInfo(name="package/package.json")
            pkg_info.size = len(pkg)
            tf.addfile(pkg_info, io.BytesIO(pkg))
            # ELF at a nested path
            elf_payload = b"\x7fELF" + b"\x00" * 20
            elf_info = tarfile.TarInfo(name="package/sub/deep/binary.x")
            elf_info.size = len(elf_payload)
            tf.addfile(elf_info, io.BytesIO(elf_payload))

        meta = extract_package_meta(buf.getvalue())
        assert meta.entrypoint == "binary.x"

    @staticmethod
    def test_first_elf_wins_with_multiple():
        """When multiple ELF files exist, the first in tar order wins."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            pkg = json.dumps({
                "name": "mytool-linux-x64",
                "version": "1.0.0",
            }).encode()
            pkg_info = tarfile.TarInfo(name="package/package.json")
            pkg_info.size = len(pkg)
            tf.addfile(pkg_info, io.BytesIO(pkg))
            # First ELF
            elf1 = b"\x7fELF" + b"\x00" * 20
            info1 = tarfile.TarInfo(name="package/bin/first")
            info1.size = len(elf1)
            tf.addfile(info1, io.BytesIO(elf1))
            # Second ELF
            elf2 = b"\x7fELF" + b"\x00" * 20
            info2 = tarfile.TarInfo(name="package/bin/second")
            info2.size = len(elf2)
            tf.addfile(info2, io.BytesIO(elf2))

        meta = extract_package_meta(buf.getvalue())
        assert meta.entrypoint == "first"

    @staticmethod
    def test_directory_not_mistaken_for_elf():
        """Directories are not regular files — they are skipped."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            pkg = json.dumps({
                "name": "mytool-linux-x64",
                "version": "1.0.0",
            }).encode()
            pkg_info = tarfile.TarInfo(name="package/package.json")
            pkg_info.size = len(pkg)
            tf.addfile(pkg_info, io.BytesIO(pkg))
            # A directory (no ELF)
            dir_info = tarfile.TarInfo(name="package/bin")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info)

        meta = extract_package_meta(buf.getvalue())
        assert meta.entrypoint == ""
