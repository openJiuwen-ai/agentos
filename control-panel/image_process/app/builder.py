"""Standalone image builder — no control-panel dependencies.

Usage as library::

    from app.builder import build, BuildError, BuildResult

Usage as CLI::

    python -m app.builder --agent-name <name> --version <ver> --installer-path <tgz> --output-dir <dir>
"""

import asyncio
import logging
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Only allow safe characters in image names/tags to prevent command injection
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*$")


@dataclass
class BuildParams:
    """Parameters for the ``build()`` function."""
    task_id: str
    agent_name: str
    version: str
    installer_path: Path
    output_dir: Path
    on_progress: "callable | None" = None
    work_dir: Path | None = None

# Path to the Dockerfile template at image_process/ root (sibling of app/).
_DOCKERFILE_PATH = Path(__file__).resolve().parent.parent / "agent.Dockerfile"
_BASE_IMAGE = "agent-base:1.0"

# ── Exceptions ──────────────────────────────────────────────────────────


class BuildError(Exception):
    """Raised when image build fails."""


class BuildResult(NamedTuple):
    image: str
    image_digest: str
    image_path: str
    base_image: str


# ── Backend interface ───────────────────────────────────────────────────


class AbstractBuilder(ABC):
    """Pluggable image build backend."""

    @abstractmethod
    async def build_image(
        self, work_dir: Path, image_name: str, build_args: dict[str, str],
    ) -> None:
        ...

    @abstractmethod
    async def save_image(self, image_name: str, agent_name: str, version: str, work_dir: Path) -> None:
        ...

    @abstractmethod
    async def get_image_id(self, image_name: str) -> str:
        ...

    @abstractmethod
    async def check_available(self) -> bool:
        ...


# ── Docker backend ──────────────────────────────────────────────────────


class DockerBuilder(AbstractBuilder):
    """Builds OCI images via ``docker build`` / ``docker save``."""

    async def check_available(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "docker", "version",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def build_image(
        self, work_dir: Path, image_name: str, build_args: dict[str, str],
    ) -> None:
        cmd = ["docker", "build", "-t", image_name]
        for k, v in build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd += ["-f", str(work_dir / "Dockerfile"), str(work_dir)]
        logger.info("docker build: %s", " ".join(cmd))
        await self._run(cmd, "docker build failed")

    async def save_image(self, image_name: str, agent_name: str, version: str, work_dir: Path) -> None:
        oci_tarball = work_dir / "oci" / f"{agent_name}-{version}.tar.gz"
        oci_tarball.parent.mkdir(parents=True, exist_ok=True)
        cmd = f"docker save {image_name} | gzip -c > {oci_tarball}"
        logger.info("docker save: %s", cmd)
        await self._run_shell(cmd, "docker save failed")

    async def get_image_id(self, image_name: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", "--format={{.Id}}", image_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        logger.debug("%s", stdout.decode(errors="replace").strip())
        if proc.returncode == 0:
            return stdout.decode().strip()
        raise BuildError("docker inspect failed")

    async def _run(self, cmd: list[str], fail_msg: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        await self._stream(proc, fail_msg)

    async def _run_shell(self, cmd: str, fail_msg: str) -> None:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        await self._stream(proc, fail_msg)

    async def _stream(self, proc: asyncio.subprocess.Process, fail_msg: str) -> None:
        lines: list[str] = []
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            decoded = line.decode(errors="replace").rstrip()
            logger.debug("%s", decoded)
            lines.append(decoded)
        await proc.wait()
        if proc.returncode != 0:
            logger.error("%s (exit %d)", fail_msg, proc.returncode)
            output = "\n".join(lines)
            if len(output) > 800:
                output = "…\n" + output[-800:]
            raise BuildError(f"{fail_msg} (exit {proc.returncode}):\n{output}")


# ── Builder ─────────────────────────────────────────────────────────────

_builder: AbstractBuilder = DockerBuilder()


# ── Public API ──────────────────────────────────────────────────────────


async def build(params: BuildParams) -> BuildResult:
    """Build an OCI image from the agent tgz.

    *work_dir* is the temporary build workspace (default: ``output_dir / task_id``).
    *output_dir* receives the final ``{name}-{version}.tar.gz`` tarball.
    """
    # Validate safe names to prevent command injection
    for field, value in (("agent_name", params.agent_name),
                         ("version", params.version)):
        if not _SAFE_NAME_RE.match(value):
            logger.error("invalid %s %r — rejected for safety", field, value)
            raise BuildError(f"invalid {field}: {value!r}")

    image_name = f"{params.agent_name}:{params.version}"
    tgz_file = params.installer_path.name
    tarball_name = f"{params.agent_name}-{params.version}.tar.gz"

    work_dir = params.work_dir or params.output_dir / params.task_id

    params.output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(params.installer_path, work_dir / tgz_file)
    shutil.copy(_DOCKERFILE_PATH, work_dir / "Dockerfile")

    build_args = {
        "BASE_IMAGE": _BASE_IMAGE,
        "TGZ_FILE": tgz_file,
        "AGENT_NAME": params.agent_name,
        "VERSION": params.version,
    }

    try:
        await _report(params.on_progress, 10)
        await _builder.build_image(work_dir, image_name, build_args)
        await _report(params.on_progress, 50)
        await _builder.save_image(image_name, params.agent_name, params.version, work_dir)
        await _report(params.on_progress, 90)
        digest = await _builder.get_image_id(image_name)

        tarball = work_dir / "oci" / tarball_name
        if not tarball.exists():
            logger.error("tarball not found after save: %s", tarball)
            raise BuildError(f"tarball not found after save: {tarball}")
        shutil.move(str(tarball), str(params.output_dir / tarball_name))

        return BuildResult(image=image_name, image_digest=digest,
                           image_path=str(params.output_dir / tarball_name),
                           base_image=_BASE_IMAGE)
    except BuildError:
        raise
    except Exception as e:
        logger.error("unexpected build error: %s", e)
        raise BuildError(str(e)) from e
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def _report(on_progress, pct: int) -> None:
    if on_progress:
        await on_progress(pct)


# ── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point.

    ``python -m app.builder --agent-name <name> --version <ver>
    --installer-path <tgz> --output-dir <dir> [--loglevel LEVEL]``
    """
    import argparse
    import sys
    import uuid

    parser = argparse.ArgumentParser(description="Build an Agent OCI image")
    parser.add_argument("--agent-name", required=True, help="e.g. opencode")
    parser.add_argument("--version", required=True, help="e.g. 1.0.0")
    parser.add_argument("--installer-path", required=True, help="Path to the agent .tgz file")
    parser.add_argument("--output-dir", required=True, help="Output directory for OCI tarball")
    parser.add_argument("--loglevel", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"),
                        help="Log level (default: INFO)")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.loglevel),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    async def _run() -> int:
        if not await _builder.check_available():
            logger.error("docker daemon not available")
            return 1

        task_id = f"build-{uuid.uuid4().hex[:12]}"
        installer_path = Path(args.installer_path)
        if not installer_path.is_file():
            logger.error("%s is not a file", installer_path)
            return 1

        output_dir = Path(args.output_dir)
        try:
            result = await build(BuildParams(
                task_id=task_id,
                agent_name=args.agent_name,
                version=args.version,
                installer_path=installer_path,
                output_dir=output_dir,
            ))
            logger.info("OK image=%s digest=%s", result.image, result.image_digest)
            return 0
        except BuildError:
            return 1

    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
