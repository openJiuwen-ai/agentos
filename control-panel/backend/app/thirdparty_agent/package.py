"""Agent package metadata extraction — pure functions, no framework dependencies."""

import json
import platform
import re
import sys
import tarfile
from dataclasses import dataclass
from io import BytesIO

from app.thirdparty_agent.exceptions import ThirdpartyAgentError

_SCOPE_RE = re.compile(r"^@[^/]+/")
_PLATFORM_RE = re.compile(r"-(linux|darwin|win32)-(x64|arm64)(-musl)?$")


class PackageExtractError(ThirdpartyAgentError):
    """Failed to extract package metadata."""


class InvalidArchiveError(PackageExtractError):
    """Not a valid tar.gz archive."""


class MissingPackageJsonError(PackageExtractError):
    """No package/package.json found in archive."""


class MissingFieldError(PackageExtractError):
    """Required field (name / version) missing from package.json."""


class PlatformNotDeterminedError(PackageExtractError):
    """Cannot determine os/arch from package name."""


class PlatformMismatchError(PackageExtractError):
    """Package platform (os/arch/libc) does not match the running system."""


@dataclass
class PackageMeta:
    agent_name: str
    version: str
    display_name: str
    entrypoint: str
    os: str
    arch: str
    libc: str  # "gnu" or "musl"

    def validate_platform(self) -> None:
        """Raise :class:`PlatformMismatchError` if this package doesn't match
        the current platform.
        """
        os_map = {"linux": "linux", "darwin": "darwin", "win32": "win32"}
        arch_map = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}
        expected_os = os_map.get(sys.platform, sys.platform)
        expected_arch = arch_map.get(platform.machine().lower(),
                                     platform.machine().lower())
        libc_name, _ = platform.libc_ver()
        expected_libc = "musl" if "musl" in libc_name.lower() else "gnu"

        if (self.os != expected_os
                or self.arch != expected_arch
                or self.libc != expected_libc):
            raise PlatformMismatchError(
                f"platform mismatch: expected "
                f"{expected_os}-{expected_arch}-{expected_libc}, "
                f"got {self.os}-{self.arch}-{self.libc}")


def extract_package_meta(content: bytes) -> PackageMeta:
    """Parse a .tgz archive and extract agent metadata from package/package.json.

    Raises ``PackageExtractError`` subclasses for specific failures:
    - ``InvalidArchiveError``: not a valid tar.gz
    - ``MissingPackageJsonError``: no package.json found
    - ``MissingFieldError``: name or version missing
    - ``PlatformNotDeterminedError``: cannot determine os/arch from name
    """
    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("package/package.json"):
                    f = tf.extractfile(member)
                    if f is not None:
                        pkg = json.loads(f.read())
                        if "name" not in pkg:
                            raise MissingFieldError("package.json missing 'name' field")
                        if "version" not in pkg:
                            raise MissingFieldError("package.json missing 'version' field")
                        raw_name = pkg["name"]
                        unscoped = _SCOPE_RE.sub("", raw_name)
                        m = _PLATFORM_RE.search(unscoped)
                        if not m:
                            raise PlatformNotDeterminedError(
                                f"cannot determine os/arch from package name {raw_name!r}")
                        agent_name = _PLATFORM_RE.sub("", unscoped)
                        version = pkg["version"]
                        display_name = pkg.get("displayName") or pkg["name"]
                        entrypoint = ""
                        if "bin" in pkg:
                            bin_val = pkg["bin"]
                            if isinstance(bin_val, dict):
                                entrypoint = next(iter(bin_val))
                            elif isinstance(bin_val, str):
                                entrypoint = bin_val
                        return PackageMeta(
                            agent_name=agent_name, version=version,
                            display_name=display_name, entrypoint=entrypoint,
                            os=m.group(1), arch=m.group(2),
                            libc="musl" if m.group(3) else "gnu")
            raise MissingPackageJsonError("no package/package.json found in archive")
    except tarfile.TarError as e:
        raise InvalidArchiveError(f"invalid tar.gz archive: {e}") from e
    except json.JSONDecodeError as e:
        raise InvalidArchiveError(f"invalid package.json: {e}") from e
