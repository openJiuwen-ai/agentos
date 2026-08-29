"""In-memory build task registry and runner."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.builder import BuildError, _runtime
from app.config import settings
from app.factory import FactoryService, create_default_factory
from app.factory.models import BuildResult, FactoryError
from app.schemas import BuildCreateRequest, BuildStatusResponse

logger = logging.getLogger(__name__)

_FINISHED = frozenset({"done", "failed"})

_factory: FactoryService = create_default_factory()


def set_factory(factory: FactoryService) -> None:
    """Replace the process factory (tests)."""
    global _factory
    _factory = factory


@dataclass
class TaskRecord:
    request_id: str
    package_path: str
    status: str = "pending"
    progress: int = 0
    name: str | None = None
    version: str | None = None
    image_ref: str | None = None
    archive_path: str | None = None
    runtime_spec: dict | None = None
    recipe_id: str | None = None
    base_ref: str | None = None
    image_digest: str | None = None
    image_module_version: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


_tasks: dict[str, TaskRecord] = {}
_lock = asyncio.Lock()


def get_task(request_id: str) -> TaskRecord | None:
    return _tasks.get(request_id)


def clear_tasks() -> None:
    """Clear in-memory task registry (for tests only)."""
    _tasks.clear()


def prune_finished_tasks(now: datetime | None = None) -> int:
    """Drop finished tasks older than TASK_TTL_SECONDS. Returns removed count."""
    now = now or datetime.now(timezone.utc)
    ttl = timedelta(seconds=settings.TASK_TTL_SECONDS)
    expired: list[str] = []
    for tid, rec in _tasks.items():
        if rec.status not in _FINISHED:
            continue
        if rec.finished_at is None:
            continue
        if now - rec.finished_at < ttl:
            continue
        expired.append(tid)
    for tid in expired:
        del _tasks[tid]
    return len(expired)


def list_task_status(request_id: str) -> BuildStatusResponse | None:
    rec = get_task(request_id)
    if rec is None:
        return None
    return BuildStatusResponse(
        request_id=rec.request_id,
        status=rec.status,  # type: ignore[arg-type]
        progress=rec.progress,
        name=rec.name,
        version=rec.version,
        image_ref=rec.image_ref,
        archive_path=rec.archive_path,
        runtime_spec=rec.runtime_spec,
        recipe_id=rec.recipe_id,
        base_ref=rec.base_ref,
        image_digest=rec.image_digest,
        image_module_version=rec.image_module_version,
        error_message=rec.error_message,
        created_at=rec.created_at,
        started_at=rec.started_at,
        finished_at=rec.finished_at,
    )


async def enqueue_build(req: BuildCreateRequest) -> TaskRecord:
    package = Path(req.package_path)
    if not package.is_file():
        raise FileNotFoundError(f"package not found: {req.package_path}")

    request_id = req.request_id or f"build-{uuid.uuid4().hex[:12]}"
    async with _lock:
        removed = prune_finished_tasks()
        if removed:
            logger.debug("pruned %d finished build task(s)", removed)
        existing = _tasks.get(request_id)
        if existing and existing.status in ("pending", "building"):
            return existing
        rec = TaskRecord(request_id=request_id, package_path=req.package_path)
        _tasks[request_id] = rec

    asyncio.create_task(_run_build(request_id, package, req.options))
    return rec


async def _run_build(
    request_id: str,
    package_path: Path,
    options: dict | None,
) -> None:
    rec = _tasks[request_id]
    rec.status = "building"
    rec.started_at = datetime.now(timezone.utc)
    rec.progress = 0

    async def on_progress(pct: int) -> None:
        rec.progress = pct
        rec.status = "building"

    try:
        result: BuildResult = await _factory.build_from_path(
            package_path,
            options,
            request_id=request_id,
            on_progress=on_progress,
        )
        rec.status = "done"
        rec.progress = 100
        rec.name = result.name
        rec.version = result.version
        rec.image_ref = result.image_ref
        rec.archive_path = result.archive_path
        rec.runtime_spec = result.runtime_spec
        rec.recipe_id = result.recipe_id
        rec.base_ref = result.base_ref
        rec.image_digest = result.image_digest
        rec.image_module_version = result.image_module_version
        rec.finished_at = datetime.now(timezone.utc)
        logger.info("build done request=%s image=%s", request_id, result.image_ref)
    except (BuildError, FactoryError) as e:
        await _fail(rec, str(e))
    except Exception as e:
        logger.exception("unexpected build error request=%s", request_id)
        await _fail(rec, str(e))


async def _fail(rec: TaskRecord, message: str) -> None:
    rec.status = "failed"
    rec.error_message = message[:1024]
    rec.finished_at = datetime.now(timezone.utc)


async def docker_available() -> bool:
    return await _runtime.check_available()


async def remove_loaded_image(tag: str) -> None:
    await _factory.remove_loaded_image(tag)
