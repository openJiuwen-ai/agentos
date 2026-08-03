"""AgentInstaller service — upload, build orchestration, query."""

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.thirdparty_agent import (
    AgentInstaller,
    BuildTask,
    InstallerCreate,
    InstallerUpdate,
)
from app.schemas.thirdparty_agent import (
    AgentInstallerUploadResult,
    BuildStatusResponse,
    BuildTaskResponse,
    InstallerListItem,
)
from app.services import image_process_client
from app.services.image_process_client import ImageProcessError, RemoteBuildStatus
from app.thirdparty_agent.exceptions import ThirdpartyAgentError
from app.thirdparty_agent.package import PackageMeta, extract_package_meta

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


class InsufficientDiskSpaceError(AgentServiceError):
    """Not enough disk space on the target filesystem."""


# ── Service ──────────────────────────────────────────────────────────────

class ThirdpartyAgentService:
    """Third-party agent lifecycle: upload, build orchestration, query."""

    # ── helpers ───────────────────────────────────────────────────────

    _DISK_SPACE_MARGIN = 50 * 1024 * 1024  # 50 MB

    @staticmethod
    def check_disk_space(uploaded_by: str, needed: int) -> None:
        """Raise :class:`InsufficientDiskSpaceError` if the installer
        directory does not have at least *needed* bytes free.
        """
        installer_dir = Path(settings.AGENTOS_HOME_BASE) / uploaded_by / "installers"
        installer_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(installer_dir)
        if usage.free < needed:
            raise InsufficientDiskSpaceError(
                f"not enough disk space: {usage.free} free, {needed} required")

    @staticmethod
    def _save_installer_file(content: bytes, meta: PackageMeta, uploaded_by: str) -> str:
        dest = Path(settings.AGENTOS_HOME_BASE) / uploaded_by / "installers"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{meta.agent_name}-{meta.version}.tgz"
        try:
            path.write_bytes(content)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return str(path)

    # ── upload ────────────────────────────────────────────────────────

    async def upload(
        self, session: AsyncSession, uploaded_by: str, package: UploadFile,
    ) -> AgentInstallerUploadResult:
        if package.size and package.size > settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES:
            raise PackageTooLargeError(
                package.size, settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES)

        self.check_disk_space(
            uploaded_by, (package.size or 0) + self._DISK_SPACE_MARGIN)

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

        user_home = Path(settings.AGENTOS_HOME_BASE) / agent_installer.uploaded_by
        try:
            await image_process_client.submit_build(
                task_id=task.task_id,
                agent_name=agent_installer.agent_name,
                version=agent_installer.version,
                installer_path=agent_installer.installer_path,
                output_dir=str(user_home / "images"),
                work_dir=str(user_home / "run" / task.task_id),
            )
        except ImageProcessError as e:
            logger.error("image_process submit failed task=%s: %s", task.task_id, e)
            await BuildTask.mark_failed(session, task.task_id, error_message=str(e))
            return BuildTaskResponse(
                task_id=task.task_id, status="failed", created_at=task.created_at)

        logger.info("build task created: %s v%s task=%s", agent_name, version, task.task_id)
        return BuildTaskResponse(
            task_id=task.task_id, status=task.status, created_at=task.created_at)

    # ── list / status (pull-sync from image_process) ───────────────────

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

    async def get_build_task(
        self, session: AsyncSession, task_id: str,
    ) -> BuildStatusResponse | None:
        task = await BuildTask.get_by_id(session, task_id)
        if task is None:
            return None

        if task.status not in ("done", "failed"):
            remote = await image_process_client.fetch_build(task_id)
            if remote is not None:
                await self._apply_remote(session, task, remote)
                task = await BuildTask.get_by_id(session, task_id)
                if task is None:
                    return None

        return BuildStatusResponse(
            task_id=task.task_id, status=task.status, progress=task.progress,
            image=task.image, image_digest=task.image_digest,
            started_at=task.started_at, finished_at=task.finished_at,
            registered=(task.status == "done"),
            error_message=task.error_message,
        )

    async def _apply_remote(
        self, session: AsyncSession, task: BuildTask, remote: RemoteBuildStatus,
    ) -> None:
        """Idempotently mirror image_process status into the local DB."""
        if task.status in ("done", "failed"):
            return

        if remote.status == "pending":
            return

        if remote.status == "building":
            if task.status == "pending":
                await BuildTask.mark_building(session, task.task_id)
            await BuildTask.update_progress(session, task.task_id, remote.progress)
            return

        if remote.status == "failed":
            await BuildTask.mark_failed(
                session, task.task_id,
                error_message=remote.error_message or "build failed",
            )
            return

        if remote.status != "done":
            logger.warning(
                "ignore unknown remote status task=%s status=%s",
                task.task_id, remote.status,
            )
            return

        installer = await AgentInstaller.get(session, task.agent_name, task.version)
        if installer is not None:
            await AgentInstaller.update(
                session, installer.agent_name, installer.version,
                params=InstallerUpdate(
                    image_digest=remote.image_digest or "",
                    image_path=remote.image_path or "",
                    base_image=remote.base_image or "",
                ))

        image = remote.image or ""
        digest = remote.image_digest or ""
        await BuildTask.mark_done(session, task.task_id, image, digest)
        logger.info("build done via poll: task=%s image=%s", task.task_id, image)

        if installer is not None and image:
            try:
                await self._register_image(installer, image)
            except Exception:
                logger.exception(
                    "registry registration failed (non-blocking) task=%s", task.task_id)

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    async def _register_image(installer: AgentInstaller, image: str) -> None:
        import httpx

        url = f"{settings.AGENT_REGISTER_URL.rstrip('/')}/api/images"
        payload = {
            "framework": installer.entrypoint,
            "framework_version": installer.version,
            "env_vars": {},
            "runtime_spec": {
                "runtime": "python3.11",
                "sandbox_type": "docker",
                "rootfs": {
                    "imageurl": image,
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
        logger.info(
            "image registered: %s v%s → %s",
            installer.agent_name, installer.version, image,
        )
