"""Agent installer service — upload, build, query."""

import asyncio
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.thirdparty_agent.exceptions import ThirdpartyAgentError
from app.thirdparty_agent.package import PackageMeta, extract_package_meta
from app.models.thirdparty_agent import (
    AgentRegistration, BuildTask, ConcurrentBuildLimitError, CreateAgentRegistrationParams)
from app.schemas.thirdparty_agent import (
    InstallerListItem,
    InstallerListResponse,
    BuildStatusResponse,
    BuildTaskResponse,
)
from app.services import image_process_client
from app.services.image_process_client import ImageProcessError, RemoteBuildStatus

logger = logging.getLogger(__name__)


@dataclass
class RegisterParams:
    """Parameters for register_image."""
    installer_path: str
    entrypoint: str
    agent_name: str
    version: str
    uploaded_by: str
    display_name: str


@dataclass
class CreateBuildTaskParams:
    """Parameters for create_build_task."""
    agent_name: str
    version: str
    display_name: str
    entrypoint: str
    uploaded_by: str


@dataclass
class ListInstallersParams:
    """Parameters for list_installers."""
    uploaded_by: str
    framework: str = ""
    size: int = 20
    page: int = 1


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
    def _installer_path(uploaded_by: str, agent_name: str, version: str) -> str:
        return str(
            Path(settings.AGENTOS_HOME_BASE) / uploaded_by / "installers"
            / f"{agent_name}-{version}.tgz"
        )

    @staticmethod
    def check_disk_space(uploaded_by: str, needed: int) -> None:
        installer_dir = Path(settings.AGENTOS_HOME_BASE) / uploaded_by / "installers"
        installer_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(installer_dir)
        if usage.free < needed:
            raise InsufficientDiskSpaceError(
                f"not enough disk space: {usage.free} free, {needed} required")

    @staticmethod
    def save_installer_file(path: str, content: bytes) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_bytes(content)
        except Exception:
            p.unlink(missing_ok=True)
            raise
        return str(p)

    # ── upload ────────────────────────────────────────────────────────

    async def upload(
        self, session: AsyncSession, uploaded_by: str, package: UploadFile,
    ) -> InstallerListItem:
        if package.size and package.size > settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES:
            raise PackageTooLargeError(
                package.size, settings.THIRDPARTY_AGENT_INSTALLER_MAX_BYTES)

        self.check_disk_space(
            uploaded_by, (package.size or 0) + self._DISK_SPACE_MARGIN)

        content = await package.read()
        meta = extract_package_meta(content)

        meta.validate_platform()

        # duplicate check: query agent_registrations by installer_path
        installer_path = self._installer_path(uploaded_by, meta.agent_name, meta.version)
        if await AgentRegistration.exists_by_path(session, installer_path):
            raise AgentAlreadyExistsError(meta.agent_name, meta.version)

        self.save_installer_file(installer_path, content)
        logger.info("agent uploaded: %s v%s", meta.agent_name, meta.version)
        return InstallerListItem(
            agent_name=meta.agent_name, version=meta.version,
            display_name=package.filename,
            entrypoint=meta.entrypoint)

    # ── build ─────────────────────────────────────────────────────────

    async def create_build_task(
        self, session: AsyncSession, p: CreateBuildTaskParams,
    ) -> BuildTaskResponse:
        installer_path = self._installer_path(p.uploaded_by, p.agent_name, p.version)
        if not os.path.isfile(installer_path):
            raise AgentNotFoundError(p.agent_name, p.version)

        task = BuildTask(
            task_id=f"build-{uuid.uuid4().hex[:12]}",
            installer_path=installer_path,
            status="pending", progress=0,
            created_at=datetime.now(timezone.utc))

        inserted, created = await BuildTask.try_insert(
            session, task, max_concurrent=5)

        if not created:
            return BuildTaskResponse(
                task_id=inserted.task_id, status=inserted.status,
                created_at=inserted.created_at)

        logger.info("build task created: %s task=%s", installer_path, task.task_id)
        params = RegisterParams(
            installer_path=installer_path,
            entrypoint=p.entrypoint,
            agent_name=p.agent_name,
            version=p.version,
            uploaded_by=p.uploaded_by,
            display_name=p.display_name,
        )
        asyncio.create_task(self._run_build(task.task_id, params))

        logger.info("build task created: %s v%s task=%s", p.agent_name, p.version, task.task_id)
        return BuildTaskResponse(
            task_id=task.task_id, status=task.status, created_at=task.created_at)

    # ── list / status (pull-sync from image_process) ───────────────────

    @staticmethod
    async def list_installers(
        session: AsyncSession,
        p: ListInstallersParams,
    ) -> InstallerListResponse:
        import httpx

        url = f"{settings.AGENT_REGISTER_URL.rstrip('/')}/api/images"
        params: dict[str, str] = {"framework": p.framework, "uploaded_by": p.uploaded_by}
        if p.size > 0:
            params["page"] = str(p.page)
            params["size"] = str(p.size)

        logger.info("querying registry: %s params=%s", url, params)
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            logger.error("registry query error %s: %s", resp.status_code, resp.text)
            raise AgentServiceError(f"registry returned {resp.status_code}")

        images = resp.json()
        total = int(resp.headers.get("X-Total-Count", len(images)))

        # Enrich registry images with local AgentRegistration data
        items: list[InstallerListItem] = []
        for img in images:
            fw = img["framework"]
            fw_version = img["framework_version"]
            reg = await AgentRegistration.get(session, fw, fw_version)
            items.append(InstallerListItem(
                agent_name=reg.agent_name if reg else "",
                version=fw_version,
                display_name=reg.display_name if reg else "",
                entrypoint=fw,
            ))

        return InstallerListResponse(items=items, total=total)

    async def get_build_task(
        self, session: AsyncSession, task_id: str,
    ) -> BuildStatusResponse | None:
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

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    async def register_image(
        session: AsyncSession,
        params: RegisterParams,
        result: RemoteBuildStatus,
    ) -> None:
        import httpx

        url = f"{settings.AGENT_REGISTER_URL.rstrip('/')}/api/images"
        payload = {
            "framework": params.entrypoint,
            "framework_version": params.version,
            "env_vars": {},
            "runtime_spec": {
                **result.runtime_spec,
                "rootfs": {
                    **result.runtime_spec.get("rootfs", {}),
                    "imageurl": result.image,
                },
            },
            "image_module_version": result.image_module_version,
            "uploaded_by": params.uploaded_by,
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
        logger.info("image registered: %s v%s → %s", params.agent_name, params.version, result.image)

        await AgentRegistration.create(
            session,
            CreateAgentRegistrationParams(
                framework=params.entrypoint,
                framework_version=params.version,
                installer_path=params.installer_path,
                display_name=params.display_name,
                agent_name=params.agent_name,
            ),
        )

    async def _run_build(
        self, task_id: str, params: RegisterParams,
    ) -> None:
        from app.database import async_session_maker

        async with async_session_maker() as session:
            if (await BuildTask.mark_building(session, task_id)) is None:
                return

            try:
                user_home = Path(settings.AGENTOS_HOME_BASE) / params.uploaded_by
                await image_process_client.submit_build(
                    task_id=task_id,
                    agent_name=params.agent_name,
                    version=params.version,
                    installer_path=params.installer_path,
                    output_dir=str(user_home / "images"),
                    work_dir=str(user_home / "run" / task_id),
                )

                while True:
                    result = await image_process_client.fetch_build(task_id)
                    if result is None:
                        await asyncio.sleep(1)
                        continue
                    await BuildTask.update_progress(session, task_id, result.progress)
                    if result.status in ("failed", "done"):
                        break
                    await asyncio.sleep(1)

                if result.status == "failed":
                    await BuildTask.mark_failed(
                        session, task_id,
                        error_message=result.error_message or "Build failed",
                    )
                    logger.error("build failed: %s v%s task=%s error=%s",
                                 params.agent_name, params.version, task_id,
                                 result.error_message)
                    return

                await self.register_image(session, params, result)

                await BuildTask.mark_done(session, task_id, result.image, result.image_digest)
                logger.info("build done: %s v%s task=%s image=%s",
                            params.agent_name, params.version, task_id, result.image)

            except Exception as e:
                logger.exception("unexpected error during build %s", task_id)
                await BuildTask.mark_failed(session, task_id, error_message=str(e))
