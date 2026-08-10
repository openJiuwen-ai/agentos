"""In-memory build task registry and runner."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.builder import BuildError, BuildParams, BuildResult, _builder, build
from app.config import settings
from app.schemas import BuildCreateRequest, BuildStatusResponse

logger = logging.getLogger(__name__)

_FINISHED = frozenset({"done", "failed"})


@dataclass
class TaskRecord:
    task_id: str
    status: str = "pending"
    progress: int = 0
    image: str | None = None
    image_digest: str | None = None
    image_path: str | None = None
    base_image: str | None = None
    runtime_spec: dict | None = None
    image_module_version: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


_tasks: dict[str, TaskRecord] = {}
# Serializes registry mutations (idempotent enqueue + prune). Concurrency
# limiting is enforced upstream in control-panel (BuildTask.try_insert
# max_concurrent); this lock is not a rate limiter.
_lock = asyncio.Lock()


def get_task(task_id: str) -> TaskRecord | None:
    return _tasks.get(task_id)


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


def list_task_status(task_id: str) -> BuildStatusResponse | None:
    rec = get_task(task_id)
    if rec is None:
        return None
    return BuildStatusResponse(
        task_id=rec.task_id,
        status=rec.status,  # type: ignore[arg-type]
        progress=rec.progress,
        image=rec.image,
        image_digest=rec.image_digest,
        image_path=rec.image_path,
        base_image=rec.base_image,
        runtime_spec=rec.runtime_spec,
        image_module_version=rec.image_module_version,
        error_message=rec.error_message,
        created_at=rec.created_at,
        started_at=rec.started_at,
        finished_at=rec.finished_at,
    )


async def enqueue_build(req: BuildCreateRequest) -> TaskRecord:
    installer = Path(req.installer_path)
    if not installer.is_file():
        raise FileNotFoundError(f"installer not found: {req.installer_path}")

    async with _lock:
        removed = prune_finished_tasks()
        if removed:
            logger.debug("pruned %d finished build task(s)", removed)
        existing = _tasks.get(req.task_id)
        if existing and existing.status in ("pending", "building"):
            return existing
        rec = TaskRecord(task_id=req.task_id)
        _tasks[req.task_id] = rec

    asyncio.create_task(_run_build(req))
    return rec


async def _run_build(req: BuildCreateRequest) -> None:
    rec = _tasks[req.task_id]
    rec.status = "building"
    rec.started_at = datetime.now(timezone.utc)
    rec.progress = 0

    async def on_progress(pct: int) -> None:
        rec.progress = pct
        rec.status = "building"

    try:
        result: BuildResult = await build(BuildParams(
            task_id=req.task_id,
            agent_name=req.agent_name,
            version=req.version,
            installer_path=Path(req.installer_path),
            output_dir=Path(req.output_dir),
            work_dir=Path(req.work_dir) if req.work_dir else None,
            on_progress=on_progress,
        ))
        rec.status = "done"
        rec.progress = 100
        rec.image = result.image
        rec.image_digest = result.image_digest
        rec.image_path = result.image_path
        rec.base_image = result.base_image
        rec.runtime_spec = result.runtime_spec
        rec.image_module_version = result.image_module_version
        rec.finished_at = datetime.now(timezone.utc)
        logger.info("build done task=%s image=%s", req.task_id, result.image)
    except BuildError as e:
        await _fail(rec, str(e))
    except Exception as e:
        logger.exception("unexpected build error task=%s", req.task_id)
        await _fail(rec, str(e))


async def _fail(rec: TaskRecord, message: str) -> None:
    rec.status = "failed"
    rec.error_message = message[:1024]
    rec.finished_at = datetime.now(timezone.utc)


async def docker_available() -> bool:
    return await _builder.check_available()
