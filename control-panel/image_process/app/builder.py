"""Docker image runtime used by factory Recipes.

This module is the ImageRuntime adapter (formerly AbstractBuilder / DockerBuilder).
Recipe orchestration lives in ``app.factory``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*$")


class BuildError(Exception):
    """Raised when image build or docker operations fail."""


class ImageRuntime(ABC):
    """Pluggable image execution backend (docker)."""

    @abstractmethod
    async def build(self, work_dir: Path, tag: str, build_args: dict[str, str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def load_archive(self, archive_path: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save_archive(self, tag: str, dest: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    async def remove(self, tag: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def inspect(self, tag: str) -> dict:
        """Return ``{id, labels, runtime_spec}`` for *tag*."""
        raise NotImplementedError

    @abstractmethod
    async def check_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_sandbox_type(self) -> str:
        """Return sandbox type for registry registration (e.g. 'docker')."""
        raise NotImplementedError


class DockerRuntime(ImageRuntime):
    """Builds OCI images via docker build / docker save."""

    async def check_available(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def get_sandbox_type(self) -> str:
        return "docker"

    async def build(self, work_dir: Path, tag: str, build_args: dict[str, str]) -> None:
        cmd = ["docker", "build", "-t", tag]
        for k, v in build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd += ["-f", str(work_dir / "Dockerfile"), str(work_dir)]
        logger.info("docker build: %s", " ".join(cmd))
        await self._run(cmd, "docker build failed")

    async def save_archive(self, tag: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = f"docker save {tag} | gzip -c > {dest}"
        logger.info("docker save: %s", cmd)
        await self._run_shell(cmd, "docker save failed")

    async def load_archive(self, archive_path: Path) -> None:
        cmd = ["docker", "load", "-i", str(archive_path)]
        logger.info("docker load: %s", " ".join(cmd))
        await self._run(cmd, "docker load failed")

    async def remove(self, tag: str) -> None:
        cmd = ["docker", "rmi", tag]
        logger.info("docker rmi: %s", " ".join(cmd))
        await self._run(cmd, "docker rmi failed")

    async def inspect(self, tag: str) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            tag,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise BuildError(
                f"docker inspect {tag!r} failed: "
                f"{stderr.decode(errors='replace').strip()}"
            )
        data = json.loads(stdout.decode())
        if not data:
            raise BuildError(f"docker inspect {tag!r} returned empty")
        info = data[0]
        labels = (info.get("Config") or {}).get("Labels") or {}
        raw = labels.get("agentos.runtime_spec", "{}")
        runtime_spec = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return {
            "id": info.get("Id", ""),
            "labels": labels,
            "runtime_spec": runtime_spec,
        }

    async def _run(self, cmd: list[str], fail_msg: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await self._stream(proc, fail_msg)

    async def _run_shell(self, cmd: str, fail_msg: str) -> None:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
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


_runtime: ImageRuntime = DockerRuntime()
