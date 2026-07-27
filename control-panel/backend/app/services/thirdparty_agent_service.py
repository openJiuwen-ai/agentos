"""AgentInstaller service — upload, build, query."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.image_process.build import BuildParams, BuildResult, build
from app.thirdparty_agent.exceptions import ThirdpartyAgentError
from app.thirdparty_agent.package import PackageMeta, extract_package_meta
from app.models.thirdparty_agent import (
    AgentInstaller, BuildTask, ConcurrentBuildLimitError,
    InstallerCreate, InstallerUpdate)
from app.schemas.thirdparty_agent import (
    AgentInstallerUploadResult,
    BuildStatusResponse,
    BuildTaskResponse,
    InstallerListItem,
)

logger = logging.getLogger(__name__)


# ── Domain exceptions ────────────────────────────────────────────────────


class AgentServiceError(ThirdpartyAgentError):
    """Base exception for agent service operations."""


class PackageTooLargeError(AgentServiceError):
    """Uploaded package exceeds the configured size limit."""

    def __init__(self, size: int, max_bytes: int) -> None:
        self.size = size
        self.max_bytes = max_bytes
        super().__init__(f"package too large: {size} bytes (max {max_bytes})")


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


# ── Service ──────────────────────────────────────────────────────────────

class ThirdpartyAgentService:
    """Third-party agent lifecycle: upload, build, query."""

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _save_installer_file(content: bytes, meta: PackageMeta, uploaded_by: str) -> str:
        dest = Path(settings.AGENTOS_HOME_BASE) / uploaded_by / "installers"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{meta.agent_name}-{meta.version}.tgz"
        path.write_bytes(content)
        return str(path)

    # ── upload ────────────────────────────────────────────────────────

    async def upload(
        self, session: AsyncSession, uploaded_by: str, package: UploadFile,
    ) -> AgentInstallerUploadResult:
        if package.size and package.size > settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES:
            raise PackageTooLargeError(
                package.size, settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES)

        content = await package.read()
        meta = extract_package_meta(content)  # exceptions propagate directly

        meta.validate_platform()  # raises PlatformMismatchError on failure

        if await AgentInstaller.exists(session, meta.agent_name, meta.version):
            raise AgentAlreadyExistsError(meta.agent_name, meta.version)

        installer_path = self._save_installer_file(content, meta, uploaded_by)
        await AgentInstaller.create(session, InstallerCreate(
            agent_name=meta.agent_name, display_name=meta.display_name,
            version=meta.version, entrypoint=meta.entrypoint,
            installer_path=installer_path, uploaded_by=uploaded_by,
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
        agent_installer = await AgentInstaller.get(session, agent_name, version)
        if agent_installer is None:
            raise AgentNotFoundError(agent_name, version)

        task = BuildTask(
            task_id=f"build-{uuid.uuid4().hex[:12]}",
            agent_name=agent_name, version=version,
            status="pending", progress=0,
            created_at=datetime.now(timezone.utc))

        inserted, created = await BuildTask.try_insert(
            session, task, max_concurrent=5)

        if not created:
            return BuildTaskResponse(
                task_id=inserted.task_id, status=inserted.status,
                created_at=inserted.created_at)

        await AgentInstaller.update(
            session, agent_name, version,
            params=InstallerUpdate(display_name=display_name, entrypoint=entrypoint))

        logger.info("build task created: %s v%s task=%s", agent_name, version, task.task_id)
        asyncio.create_task(self._run_build(task.task_id, agent_installer))

        return BuildTaskResponse(
            task_id=task.task_id, status=task.status, created_at=task.created_at)

    # ── list / status ─────────────────────────────────────────────────

    @staticmethod
    async def list_installers(session: AsyncSession) -> list[InstallerListItem]:
        installers = await AgentInstaller.list_all(session)
        result = []
        for i in installers:
            latest = await BuildTask.latest_for(session, i.agent_name, i.version)
            result.append(InstallerListItem(
                agent_name=i.agent_name, version=i.version,
                display_name=i.display_name, entrypoint=i.entrypoint,
                build_status=latest.status if latest else None,
                build_task_id=latest.task_id if latest else None,
            ))
        return result

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
            registered=(task.status == "done"),
            error_message=task.error_message)

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    async def _register_image(installer: AgentInstaller, result: BuildResult) -> None:
        import httpx

        url = f"{settings.AGENT_REGISTER_URL.rstrip('/')}/api/images"
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
            logger.error("registry error %s: %s", resp.status_code, resp.text)
            raise RuntimeError(f"registry returned {resp.status_code}: {resp.text}")
        body = resp.json()
        status = body.get("status", "")
        if status not in ("registered", "updated"):
            raise RuntimeError(f"registry returned unexpected status {status!r}: {resp.text}")
        logger.info("image registered: %s v%s → %s", installer.agent_name, installer.version, result.image)

    async def _run_build(self, task_id: str, agent_installer: AgentInstaller) -> None:
        """Build lifecycle: building → (register → update → mark_done) | mark_failed."""
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
                        image_digest=result.image_digest,
                        image_path=result.image_path,
                        base_image=result.base_image,
                    ))

                await BuildTask.mark_done(session, task_id, result.image, result.image_digest)
                logger.info("build done: %s v%s task=%s image=%s",
                            agent_installer.agent_name, agent_installer.version,
                            task_id, result.image)

            except Exception as e:
                logger.exception("unexpected error during build %s", task_id)
                await BuildTask.mark_failed(session, task_id, error_message=str(e))
