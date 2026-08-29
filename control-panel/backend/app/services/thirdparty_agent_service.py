"""Third-party agent orchestration: gate, factory, registry cards."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.thirdparty_agent import (
    AgentRegistration,
    BuildTask,
    ConcurrentBuildLimitError,
    CreateAgentRegistrationParams,
)
from app.schemas.thirdparty_agent import (
    CardDetail,
    CardListResponse,
    PublishAccepted,
    UnregisteredItem,
    UnregisteredListResponse,
    UnregisteredStatus,
)
from app.services.agent_register_client import AgentRegisterClient, AgentRegisterError
from app.services.image_process_client import ImageProcessClient, ImageProcessError
from app.thirdparty_agent.card_view import CardViewProjector
from app.thirdparty_agent.exceptions import (
    AgentNotFoundError,
    AgentServiceError,
    CardHasInstancesError,
    InvalidUploadError,
    PackageLockedError,
)
from app.thirdparty_agent.local_file_cleaner import LocalFileCleaner
from app.thirdparty_agent.upload_gate import UploadGate, read_original_filename

logger = logging.getLogger(__name__)


@dataclass
class PublishParams:
    uploaded_by: str
    launch_command: str


class ThirdpartyAgentService:
    def __init__(
        self,
        factory: ImageProcessClient | None = None,
        registry: AgentRegisterClient | None = None,
        gate: UploadGate | None = None,
        cleaner: LocalFileCleaner | None = None,
        projector: CardViewProjector | None = None,
    ) -> None:
        self._factory = factory or ImageProcessClient()
        self._registry = registry or AgentRegisterClient()
        self._gate = gate or UploadGate()
        self._cleaner = cleaner or LocalFileCleaner()
        self._projector = projector or CardViewProjector()

    @staticmethod
    def _packages_dir() -> Path:
        return Path(settings.THIRDPARTY_AGENT_PACKAGE_DIR)

    async def _list_registry_images(self, **kwargs) -> tuple[list[dict], int]:
        try:
            return await self._registry.list_images(**kwargs)
        except AgentRegisterError as exc:
            raise AgentServiceError(f"agent registry unavailable: {exc}") from exc

    async def _list_registry_instances(self, **kwargs) -> list[dict]:
        try:
            return await self._registry.list_instances(**kwargs)
        except AgentRegisterError as exc:
            raise AgentServiceError(f"agent registry unavailable: {exc}") from exc

    async def _register_registry_image(self, payload: dict) -> str:
        try:
            return await self._registry.register_image(payload)
        except AgentRegisterError as exc:
            raise AgentServiceError(f"agent registry unavailable: {exc}") from exc

    async def _set_registry_default(self, framework: str, version: str) -> None:
        try:
            await self._registry.set_default_version(framework, version)
        except AgentRegisterError as exc:
            raise AgentServiceError(f"agent registry unavailable: {exc}") from exc

    async def _delete_registry_image(self, framework: str, version: str) -> None:
        try:
            await self._registry.delete_image(framework, version)
        except AgentRegisterError as exc:
            raise AgentServiceError(f"agent registry unavailable: {exc}") from exc

    async def publish(
        self,
        session: AsyncSession,
        uploaded: UploadFile,
        params: PublishParams,
    ) -> PublishAccepted:
        launch_command = params.launch_command.strip()
        if not launch_command:
            raise InvalidUploadError("launch command must not be empty")
        accepted = await self._gate.persist(uploaded, self._packages_dir())
        request_id = f"build-{uuid.uuid4().hex[:12]}"
        task = BuildTask(task_id=request_id, installer_path=accepted.package_path)
        try:
            _existing, inserted = await BuildTask.try_insert(session, task)
        except ConcurrentBuildLimitError as exc:
            raise PackageLockedError(str(exc)) from exc
        if not inserted:
            raise PackageLockedError(
                f"package {accepted.content_digest} is already in progress"
            )
        asyncio.create_task(
            self._run_build(
                request_id,
                accepted.package_path,
                launch_command,
                params.uploaded_by,
            )
        )
        return PublishAccepted(digest=accepted.content_digest, request_id=request_id)

    async def retry(
        self,
        session: AsyncSession,
        digest: str,
        launch_command: str,
        uploaded_by: str,
    ) -> PublishAccepted:
        launch_command = launch_command.strip()
        if not launch_command:
            raise InvalidUploadError("launch command must not be empty")
        path = self._package_path(digest)
        tasks = await BuildTask.get_by_path(session, str(path))
        if not tasks or not path.is_file():
            raise AgentNotFoundError(digest)
        if any(task.status in ("pending", "building") for task in tasks):
            raise PackageLockedError(f"package {digest} is already in progress")
        request_id = f"build-{uuid.uuid4().hex[:12]}"
        try:
            _, inserted = await BuildTask.try_insert(
                session, BuildTask(task_id=request_id, installer_path=str(path))
            )
        except ConcurrentBuildLimitError as exc:
            raise PackageLockedError(str(exc)) from exc
        if not inserted:
            raise PackageLockedError(f"package {digest} is already in progress")
        asyncio.create_task(
            self._run_build(
                request_id,
                str(path),
                launch_command,
                uploaded_by,
            )
        )
        return PublishAccepted(digest=digest, request_id=request_id)

    def _package_path(self, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise AgentNotFoundError(digest)
        return self._packages_dir() / f"{digest}.artifact"

    async def list_cards(
        self,
        session: AsyncSession,
        *,
        is_admin: bool,
        framework: str = "",
        page: int = 1,
        size: int = 20,
    ) -> CardListResponse:
        images, total = await self._list_registry_images(
            framework=framework,
            page=page,
            size=size,
        )
        # TODO(registry-contract): remove AgentRegistration enrichment and
        # _merge_local_card once /api/images persists and returns package_path
        # and agent_name for every card.
        local_records = await AgentRegistration.list_all(session)
        local_by_key = {
            (record.framework, record.framework_version): record
            for record in local_records
        }
        images = [
            _merge_local_card(
                image,
                local_by_key.get(
                    (image.get("framework"), image.get("framework_version"))
                ),
            )
            for image in images
        ]
        items = []
        if is_admin:
            instances = await self._list_registry_instances()
            for img in images:
                total, running = _count_instances(
                    instances,
                    img.get("framework", ""),
                    img.get("framework_version", ""),
                )
                items.append(
                    self._projector.for_admin(
                        img,
                        total_count=total,
                        running_count=running,
                        include_paths=False,
                    )
                )
        else:
            items = [self._projector.for_user(img) for img in images]
        return CardListResponse(items=items, total=total)

    async def get_card(
        self,
        session: AsyncSession,
        *,
        is_admin: bool,
        framework: str,
        version: str,
    ) -> CardDetail:
        images, _ = await self._list_registry_images(framework=framework, size=-1)
        match = _find_card(images, framework, version)
        if match is None:
            raise AgentNotFoundError(f"{framework}@{version}")
        match = _merge_local_card(
            match,
            await AgentRegistration.get(session, framework, version),
        )
        if is_admin:
            instances = await self._list_registry_instances(
                framework=framework,
                framework_version=version,
            )
            total, running = _count_instances(instances, framework, version)
            data = self._projector.for_admin(
                match,
                total_count=total,
                running_count=running,
                include_paths=True,
            )
        else:
            data = self._projector.for_user(match)
        return CardDetail(**data)

    async def set_default_version(self, framework: str, version: str) -> None:
        await self._set_registry_default(framework, version)

    async def delete_card(
        self,
        session: AsyncSession,
        framework: str,
        version: str,
    ) -> None:
        images, _ = await self._list_registry_images(framework=framework, size=-1)
        match = _find_card(images, framework, version)
        if match is None:
            raise AgentNotFoundError(f"{framework}@{version}")
        instances = await self._list_registry_instances(
            framework=framework,
            framework_version=version,
        )
        if instances:
            raise CardHasInstancesError(
                f"{framework}@{version} still has {len(instances)} instance(s)"
            )
        siblings = [
            i
            for i in images
            if i.get("framework") == framework and i.get("framework_version") != version
        ]
        if match.get("is_default") and siblings:
            successor = max(
                (str(i.get("framework_version") or "") for i in siblings),
                key=_semantic_version_key,
            )
            await self._set_registry_default(framework, successor)
        # TODO(registry-contract): remove this local lookup once the registry
        # returns trusted package_path, archive_path, and agent_name fields.
        local = await AgentRegistration.get(session, framework, version)
        merged = _merge_local_card(match, local)
        await self._delete_registry_image(framework, version)
        self._cleaner.remove_package(merged.get("package_path"))
        archive_path = None
        if settings.THIRDPARTY_AGENT_ARCHIVE_ENABLED and local:
            # NOTE: Registry v1.3.0 has no trusted archive-path field. Derive
            # the path from local metadata and the configured archive root so
            # registry content can never select an arbitrary local file.
            # TODO(registry-contract): accept registry archive metadata only
            # after its ownership and path-validation contract is specified.
            archive_path = _local_archive_path(local.agent_name, version)
        self._cleaner.remove_archive(archive_path)
        tag = _registry_image_tag(merged)
        if tag:
            try:
                await self._factory.remove_loaded_image(tag)
            except ImageProcessError as e:
                logger.warning("remove loaded image failed: %s", e)
        await AgentRegistration.delete_by_key(session, framework, version)

    async def list_unregistered(
        self, session: AsyncSession
    ) -> UnregisteredListResponse:
        registrations = await AgentRegistration.list_all(session)
        registered_paths = {record.installer_path for record in registrations}
        tasks = await BuildTask.list_all(session)
        latest_by_path = {}
        for task in tasks:
            latest_by_path.setdefault(task.installer_path, task)
        items = []
        for task in latest_by_path.values():
            if task.installer_path in registered_paths:
                continue
            if not Path(task.installer_path).is_file():
                continue
            items.append(
                UnregisteredItem(
                    digest=Path(task.installer_path).stem,
                    original_filename=read_original_filename(task.installer_path),
                    package_path=task.installer_path,
                    locked=task.status in ("pending", "building"),
                    last_error=task.error_message,
                    request_id=task.task_id,
                )
            )
        return UnregisteredListResponse(items=items)

    async def get_unregistered(
        self,
        session: AsyncSession,
        digest: str,
    ) -> UnregisteredStatus:
        path = self._package_path(digest)
        tasks = await BuildTask.get_by_path(session, str(path))
        if not tasks or not path.is_file():
            raise AgentNotFoundError(digest)
        task = tasks[0]
        progress = task.progress
        status = task.status
        if task.status in ("pending", "building"):
            remote = await self._factory.fetch_build(task.task_id)
            if remote is not None:
                progress = remote.progress
                status = remote.status
        return UnregisteredStatus(
            digest=digest,
            original_filename=read_original_filename(task.installer_path),
            package_path=task.installer_path,
            locked=task.status in ("pending", "building"),
            last_error=task.error_message,
            request_id=task.task_id,
            status=status,
            progress=progress,
        )

    async def delete_unregistered(self, session: AsyncSession, digest: str) -> None:
        path = self._package_path(digest)
        tasks = await BuildTask.get_by_path(session, str(path))
        if not tasks:
            return
        if any(task.status in ("pending", "building") for task in tasks):
            raise PackageLockedError(f"package {digest} is already in progress")
        self._cleaner.remove_package(str(path))
        await BuildTask.delete_by_path(session, str(path))

    async def _run_build(
        self,
        request_id: str,
        package_path: str,
        launch_command: str,
        uploaded_by: str,
    ) -> None:
        from app.database import async_session_maker

        async with async_session_maker() as session:
            try:
                await BuildTask.mark_building(session, request_id)
                await self._factory.build_from_path(package_path, request_id=request_id)
                result = None
                while True:
                    result = await self._factory.fetch_build(request_id)
                    if result is None:
                        await asyncio.sleep(1)
                        continue
                    if result.status in ("failed", "done"):
                        break
                    await BuildTask.update_progress(
                        session, request_id, result.progress
                    )
                    await asyncio.sleep(1)
                if result is None or result.status == "failed":
                    await BuildTask.mark_failed(
                        session,
                        request_id,
                        result.error_message if result else "build failed",
                    )
                    return
                runtime_spec = dict(result.runtime_spec or {})
                rootfs = {
                    **runtime_spec.get("rootfs", {}),
                    "imageurl": result.image_ref,
                }
                rootfs.pop("ports", None)
                payload = {
                    # NOTE: Registry v1.3.0 has no launch_command field, so
                    # framework temporarily carries the manually entered
                    # command required by existing launchers.
                    # TODO(registry-contract): send stable framework identity
                    # and launch_command separately when the registry/runtime
                    # protocols expose the dedicated field.
                    "framework": launch_command,
                    "framework_version": result.version,
                    "env_vars": {},
                    "runtime_spec": {**runtime_spec, "rootfs": rootfs},
                    "image_module_version": result.image_module_version,
                    "uploaded_by": uploaded_by,
                }
                # NOTE: package_path, archive_path, recipe_id, and base_ref are
                # deliberately local-only until the registry contract defines
                # them. Do not send undeclared fields: Registry v1.3.0 drops
                # them silently and cannot return them during deletion.
                # TODO(registry-contract): add these fields only after the
                # registry API and its persistence model are released.
                await self._register_registry_image(payload)
                # TODO(registry-contract): remove the local AgentRegistration
                # supplement once the registry persists package_path,
                # agent_name, and display_name and returns them from /api/images.
                await AgentRegistration.upsert(
                    session,
                    CreateAgentRegistrationParams(
                        framework=launch_command,
                        framework_version=result.version or "",
                        installer_path=package_path,
                        agent_name=result.name or launch_command,
                        display_name=result.name or launch_command,
                    ),
                )
                await BuildTask.mark_done(
                    session,
                    request_id,
                    result.image_ref or "",
                    result.image_digest or "",
                )
            except Exception as e:
                logger.exception("publish failed task=%s", request_id)
                await BuildTask.mark_failed(session, request_id, str(e))


def _merge_local_card(
    card: dict,
    local: AgentRegistration | None,
) -> dict:
    """Temporarily enrich registry cards with fields absent from registry v1.3.0.

    TODO(registry-contract): delete this helper when /api/images persists and
    returns package_path and agent_name.
    """
    if local is None:
        return dict(card)
    merged = dict(card)
    if not merged.get("package_path"):
        merged["package_path"] = local.installer_path
    if not merged.get("agent_name"):
        merged["agent_name"] = local.agent_name
    return merged


def _find_card(images: list[dict], framework: str, version: str) -> dict | None:
    for image in images:
        if image.get("framework") != framework:
            continue
        if image.get("framework_version") == version:
            return image
    return None


def _registry_image_tag(card: dict) -> str:
    """Read the Docker tag from the registry's current nested RuntimeSpec.

    NOTE: the direct field is compatibility-only for legacy/mock registries.
    Registry v1.3.0 stores the tag at runtime_spec.rootfs.imageurl.
    TODO(registry-contract): remove the direct imageurl fallback after all
    supported registries expose only the nested RuntimeSpec field.
    """
    direct = card.get("imageurl")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    runtime_spec = card.get("runtime_spec")
    if not isinstance(runtime_spec, dict):
        return ""
    rootfs = runtime_spec.get("rootfs")
    if not isinstance(rootfs, dict):
        return ""
    nested = rootfs.get("imageurl")
    return nested.strip() if isinstance(nested, str) else ""


def _local_archive_path(agent_name: str, version: str) -> str | None:
    """Derive an archive path only from validated local metadata and config.

    TODO(registry-contract): delete this helper when the registry owns and
    returns a trusted archive_path with a defined local-path validation contract.
    """
    safe = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    if not safe.fullmatch(agent_name) or not safe.fullmatch(version):
        return None
    root = Path(settings.THIRDPARTY_AGENT_IMAGE_DIR).resolve()
    candidate = (root / f"{agent_name}-{version}.tar.gz").resolve()
    if candidate.parent != root:
        return None
    return str(candidate)


def _count_instances(
    instances: list[dict], framework: str, version: str
) -> tuple[int, int]:
    matched = [
        i
        for i in instances
        if i.get("framework") == framework and i.get("framework_version") == version
    ]
    total = len(matched)
    running = sum(1 for i in matched if i.get("status") == "运行")
    return total, running


_SEMANTIC_VERSION_RE = re.compile(
    r"^[vV]?(?P<core>\d+(?:\.\d+)*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _semantic_version_key(version: str) -> tuple:
    """Return a deterministic SemVer-like precedence key.

    Existing framework versions may omit the patch component (for example
    ``2.0``), so numeric cores are padded before comparison. Build metadata
    does not affect precedence, while a release sorts after its prereleases.
    Invalid legacy versions remain sortable but rank below semantic versions.
    """
    match = _SEMANTIC_VERSION_RE.fullmatch(version.strip())
    if match is None:
        return (0, (), 0, (), version.casefold())

    core = tuple(int(part) for part in match.group("core").split("."))
    core = core + (0,) * max(0, 3 - len(core))
    prerelease = match.group("prerelease")
    if prerelease is None:
        return (1, core, 1, (), "")

    prerelease_key = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in prerelease.split(".")
    )
    return (1, core, 0, prerelease_key, "")
