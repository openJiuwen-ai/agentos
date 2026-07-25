"""AgentInstaller service — upload, build, query."""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.image_process.build import BuildError, BuildParams, BuildResult, build
from app.thirdparty_agent.package import PackageMeta, extract_package_meta
from app.models.thirdparty_agent import (
    AgentInstaller, BuildTask, InstallerCreate, InstallerUpdate)
from app.schemas.thirdparty_agent import (
    AgentInstallerUploadResult,
    BuildStatusResponse,
    BuildTaskResponse,
)

logger = logging.getLogger(__name__)


# ── Domain exceptions ────────────────────────────────────────────────────


class AgentServiceError(Exception):
    """Base exception for agent service operations."""


class PackageTooLargeError(AgentServiceError):
    """Uploaded package exceeds the configured size limit."""

    def __init__(self, size: int, max_bytes: int) -> None:
        self.size = size
        self.max_bytes = max_bytes
        super().__init__(f"package too large: {size} bytes (max {max_bytes})")


class InvalidPackageError(AgentServiceError):
    """Uploaded file is not a valid agent package."""


class AgentNotFoundError(AgentServiceError):
    """Requested agent version does not exist."""

    def __init__(self, agent_name: str, version: str) -> None:
        self.agent_name = agent_name
        self.version = version
        super().__init__(f"agent {agent_name!r} version {version!r} not found")


class AgentAlreadyExistsError(AgentServiceError):
    """Agent version already registered."""

    def __init__(self, agent_name: str, version: str) -> None:
        self.agent_name = agent_name
        self.version = version
        super().__init__(f"agent {agent_name!r} version {version!r} already exists")


class BuildTaskConflictError(AgentServiceError):
    """Another build is already in progress."""


# ── Service ──────────────────────────────────────────────────────────────

MAX_CONCURRENT_BUILDS = 5


class ThirdpartyAgentService:
    """Third-party agent lifecycle: upload, build, query."""

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _save_installer_file(content: bytes, meta: PackageMeta, uploaded_by: str) -> Path:
        filename = f"{meta.agent_name}-{meta.version}.tgz"
        dest = Path(settings.AGENTOS_HOME_BASE) / uploaded_by / "installers"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / filename).write_bytes(content)
        return dest / filename

    # ── upload ────────────────────────────────────────────────────────

    async def upload(
        self, session: AsyncSession, uploaded_by: str, package: UploadFile,
    ) -> AgentInstallerUploadResult:
        if package.size and package.size > settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES:
            raise PackageTooLargeError(
                package.size, settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES)

        content = await package.read()
        meta = extract_package_meta(content)
        if meta is None:
            raise InvalidPackageError("cannot extract package.json from uploaded file")
        if await AgentInstaller.exists(session, meta.agent_name, meta.version):
            raise AgentAlreadyExistsError(meta.agent_name, meta.version)

        installer_path = self._save_installer_file(content, meta, uploaded_by)
        await AgentInstaller.create(session, InstallerCreate(
            agent_name=meta.agent_name, display_name=meta.display_name,
            version=meta.version, entrypoint=meta.entrypoint,
            installer_path=str(installer_path), uploaded_by=uploaded_by,
        ))
        logger.info("agent uploaded: %s v%s", meta.agent_name, meta.version)
        return AgentInstallerUploadResult(
            agent_name=meta.agent_name, version=meta.version,
            display_name=meta.display_name, entrypoint=meta.entrypoint)

    # ── build ─────────────────────────────────────────────────────────

    async def create_build_task(
        self, session: AsyncSession,
        agent_name: str, version: str, display_name: str, entrypoint: str,
    ) -> BuildTaskResponse:
        # If a task for this agent+version is already active, return it.
        for t in await BuildTask.get_by_name(session, agent_name, version):
            if t.status in ("pending", "building"):
                return BuildTaskResponse(
                    task_id=t.task_id, status=t.status, created_at=t.created_at)

        agent_installer = await AgentInstaller.get(session, agent_name, version)
        if agent_installer is None:
            raise AgentNotFoundError(agent_name, version)

        if await BuildTask.count_active(session) >= MAX_CONCURRENT_BUILDS:
            raise BuildTaskConflictError(
                f"max concurrent builds ({MAX_CONCURRENT_BUILDS}) reached")

        agent_installer.display_name = display_name
        agent_installer.entrypoint = entrypoint

        task_id = f"build-{uuid.uuid4().hex[:12]}"
        task = await BuildTask.create(session, agent_name, version, task_id)
        logger.info("build task created: %s v%s task=%s", agent_name, version, task.task_id)

        asyncio.create_task(self._run_build(task_id, agent_installer))

        return BuildTaskResponse(
            task_id=task.task_id, status=task.status, created_at=task.created_at)

    # ── list / status ─────────────────────────────────────────────────

    @staticmethod
    async def list_installers(session: AsyncSession) -> list[AgentInstallerUploadResult]:
        return [
            AgentInstallerUploadResult(
                agent_name=i.agent_name, version=i.version,
                display_name=i.display_name, entrypoint=i.entrypoint,
            )
            for i in await AgentInstaller.list_all(session)
        ]

    @staticmethod
    async def get_build_task(
        session: AsyncSession, task_id: str,
    ) -> BuildStatusResponse | None:
        task = await BuildTask.get_by_id(session, task_id)
        if task is None:
            return None
        return BuildStatusResponse(
            task_id=task.task_id, status=task.status, progress=task.progress,
            image=task.image, image_digest=task.image_digest,
            started_at=task.started_at, finished_at=task.finished_at,
            registered=(task.status == "done"))

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    async def _register_image(installer: AgentInstaller, result: BuildResult) -> None:
        import httpx

        url = f"http://{settings.AGENT_REGISTRY_HOST}:{settings.AGENT_REGISTRY_PORT}/api/images"
        payload = {
            "framework": installer.agent_name,
            "framework_version": installer.version,
            "env_vars": {},
            "runtime_spec": {
                "runtime": "python3.11",
                "sandbox_type": "docker",
                "rootfs": {
                    "imageurl": result.image,
                    "user": "agentos",
                    "ports": ["tcp:2222"],
                },
            },
            "image_module_version": settings.AGENT_IMAGE_MODULE_VERSION,
            "uploaded_by": installer.uploaded_by,
        }
        logger.info("registering image: %s", url)
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"registry returned {resp.status_code}: {resp.text}")
        body = resp.json()
        status = body.get("status", "")
        if status not in ("registered", "updated"):
            raise RuntimeError(f"registry returned unexpected status {status!r}: {resp.text}")
        logger.info("image registered: %s v%s → %s", installer.agent_name, installer.version, result.image)

    async def _run_build(self, task_id: str, agent_installer: AgentInstaller) -> None:
        from app.database import async_session_maker

        async with async_session_maker() as session:
            if (await BuildTask.mark_building(session, task_id)) is None:
                return

            try:
                async def progress_cb(pct: int):
                    await BuildTask.update_progress(session, task_id, pct)

                user_home = Path(settings.AGENTOS_HOME_BASE) / agent_installer.uploaded_by
                result = await build(BuildParams(
                    task_id=task_id,
                    agent_name=agent_installer.agent_name,
                    version=agent_installer.version,
                    installer_path=Path(agent_installer.installer_path),
                    output_dir=user_home / "images",
                    work_dir=user_home / "run" / task_id,
                    on_progress=progress_cb,
                ))

                await self._register_image(agent_installer, result)

                await AgentInstaller.update(
                    session, agent_installer.agent_name, agent_installer.version,
                    params=InstallerUpdate(
                        display_name=agent_installer.display_name,
                        entrypoint=agent_installer.entrypoint,
                        image_digest=result.image_digest,
                        image_path=result.image_path,
                        base_image=result.base_image,
                    ))

                await BuildTask.mark_done(session, task_id, result.image, result.image_digest)
                logger.info("build done: %s v%s task=%s image=%s",
                             agent_installer.agent_name, agent_installer.version,
                                 task_id, result.image)

            except Exception:
                logger.exception("unexpected error during build %s", task_id)
                await BuildTask.mark_failed(session, task_id)
