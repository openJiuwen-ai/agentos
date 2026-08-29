"""Npm binary tgz Recipe: copy executables onto agent-base:1.0."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any

from app.builder import _SAFE_NAME_RE, BuildError, ImageRuntime
from app.config import settings
from app.factory.models import ArtifactManifest, BaseRef, BuildResult, FactoryError
from app.factory.recipe import Recipe

logger = logging.getLogger(__name__)

_SCOPE_RE = re.compile(r"^@[^/]+/")
_PLATFORM_RE = re.compile(r"-(linux|darwin|win32)-(x64|arm64)(-musl)?$")
_DOCKERFILE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "agent.Dockerfile"
)
_BASE_IMAGE = "agent-base:1.0"
_IMAGE_MODULE_VERSION = "1.0"


def _host_platform() -> tuple[str, str, str]:
    os_map = {"linux": "linux", "darwin": "darwin", "win32": "win32"}
    arch_map = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}
    expected_os = os_map.get(sys.platform, sys.platform)
    expected_arch = arch_map.get(platform.machine().lower(), platform.machine().lower())
    libc_name, _ = platform.libc_ver()
    expected_libc = "musl" if "musl" in libc_name.lower() else "gnu"
    return expected_os, expected_arch, expected_libc


def _read_package_json(package_path: Path) -> tuple[tarfile.TarFile, dict] | None:
    try:
        tf = tarfile.open(package_path, "r:gz")
    except (tarfile.TarError, OSError, EOFError):
        return None
    try:
        for member in tf.getmembers():
            if member.name.endswith("package/package.json"):
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                try:
                    pkg = json.loads(handle.read())
                except json.JSONDecodeError:
                    tf.close()
                    return None
                return tf, pkg
        tf.close()
        return None
    except Exception:
        tf.close()
        return None


def _parse_platform(pkg: dict) -> tuple[str, str, str, str] | None:
    raw_name = pkg.get("name")
    version = pkg.get("version")
    if not raw_name or not version:
        return None
    unscoped = _SCOPE_RE.sub("", str(raw_name))
    match = _PLATFORM_RE.search(unscoped)
    if not match:
        return None
    name = _PLATFORM_RE.sub("", unscoped)
    libc = "musl" if match.group(3) else "gnu"
    return name, match.group(1), match.group(2), libc


class NpmTgzOnBaseRecipe(Recipe):
    recipe_id = "npm_tgz_on_base"
    artifact_kind = "npm_binary"
    inject_ssh = True
    inject_yuanrong_sdk = True
    assemble = "copy_binary"

    def __init__(self, runtime: ImageRuntime) -> None:
        self._runtime = runtime

    def artifact_matches(self, package_path: Path) -> bool:
        if not package_path.is_file():
            return False
        parsed = _read_package_json(package_path)
        if parsed is None:
            return False
        tf, pkg = parsed
        try:
            return _parse_platform(pkg) is not None
        finally:
            tf.close()

    def matches(self, package_path: Path) -> bool:
        if not package_path.is_file():
            return False
        parsed = _read_package_json(package_path)
        if parsed is None:
            return False
        tf, pkg = parsed
        try:
            platform_info = _parse_platform(pkg)
            if platform_info is None:
                return False
            _, os_name, arch, libc = platform_info
            expected = _host_platform()
            return (os_name, arch, libc) == expected
        except Exception:
            return False
        finally:
            tf.close()

    def validate(self, package_path: Path) -> ArtifactManifest:
        parsed = _read_package_json(package_path)
        if parsed is None:
            raise FactoryError("无法识别制品")
        tf, pkg = parsed
        try:
            platform_info = _parse_platform(pkg)
            if platform_info is None:
                raise FactoryError("无法识别制品")
            name, os_name, arch, libc = platform_info
            version = str(pkg["version"])
            display_name = str(pkg.get("displayName") or pkg["name"])
            if not _SAFE_NAME_RE.match(name) or not _SAFE_NAME_RE.match(version):
                raise FactoryError(
                    f"invalid docker tag characters: {name!r}:{version!r}"
                )
            return ArtifactManifest(
                name=name,
                version=version,
                display_name=display_name,
                os=os_name,
                arch=arch,
                libc=libc,
            )
        finally:
            tf.close()

    def select_base(self, package_path: Path, manifest: ArtifactManifest) -> BaseRef:
        return BaseRef(ref=_BASE_IMAGE)

    async def execute(
        self,
        package_path: Path,
        base: BaseRef,
        options: dict[str, Any] | None = None,
        *,
        request_id: str,
        on_progress: Any | None = None,
    ) -> BuildResult:
        options = options or {}
        _ = options.get("inject_ssh", self.inject_ssh)

        try:
            await self._runtime.inspect(base.ref)
        except BuildError as exc:
            raise FactoryError(f"base image not found: {base.ref}") from exc

        manifest = self.validate(package_path)
        tag = f"{manifest.name}:{manifest.version}"
        tgz_file = package_path.name
        tarball_name = f"{manifest.name}-{manifest.version}.tar.gz"

        work_dir = Path(settings.WORK_DIR) / request_id
        work_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(package_path, work_dir / tgz_file)
        shutil.copy(_DOCKERFILE_PATH, work_dir / "Dockerfile")

        build_args = {
            "BASE_IMAGE": base.ref,
            "TGZ_FILE": tgz_file,
            "AGENT_NAME": manifest.name,
            "VERSION": manifest.version,
            "AGENTOS_SYS_UID": os.environ.get("AGENTOS_SYS_UID", "1000"),
            "AGENTOS_SYS_GID": os.environ.get("AGENTOS_SYS_GID", "1000"),
        }

        archive_path: Path | None = None
        try:
            inspected = await self._runtime.inspect(base.ref)
            runtime_spec = dict(inspected.get("runtime_spec") or {})
            runtime_spec["sandbox_type"] = await self._runtime.get_sandbox_type()
            if on_progress:
                await on_progress(10)
            await self._runtime.build(work_dir, tag, build_args)
            if on_progress:
                await on_progress(50)
            if settings.THIRDPARTY_AGENT_ARCHIVE_ENABLED:
                output_dir = Path(settings.OUTPUT_DIR)
                output_dir.mkdir(parents=True, exist_ok=True)
                archive_path = output_dir / tarball_name
                await self._runtime.save_archive(tag, archive_path)
            if on_progress:
                await on_progress(90)
            built = await self._runtime.inspect(tag)
            return BuildResult(
                name=manifest.name,
                version=manifest.version,
                image_ref=tag,
                archive_path=str(archive_path) if archive_path else None,
                runtime_spec=runtime_spec,
                recipe_id=self.recipe_id,
                base_ref=base.ref,
                image_digest=str(built.get("id") or ""),
                image_module_version=_IMAGE_MODULE_VERSION,
            )
        except BuildError as exc:
            raise FactoryError(str(exc)) from exc
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
