import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from app.services.log_reader import shutdown_file_executor
from app.services.log_component_config import find_merge_virtual_name
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.log import LogExportTask

import app.database as _db

logger = logging.getLogger(__name__)

_export_semaphore = asyncio.Semaphore(settings.LOG_EXPORT_MAX_CONCURRENT)
_stop_event: asyncio.Event | None = None

_log_scheduler: AsyncIOScheduler | None = None
_log_worker_task: asyncio.Task | None = None


async def start_log_services():
    global _log_scheduler, _log_worker_task

    _log_scheduler = AsyncIOScheduler()
    _log_scheduler.add_job(
        cleanup_expired_exports,
        "cron",
        hour=settings.LOG_EXPORT_CLEANUP_HOUR,
        minute=0,
        id="log_export_cleanup",
    )
    _log_scheduler.start()
    logger.info("Log export cleanup scheduler started (daily at %02d:00)", settings.LOG_EXPORT_CLEANUP_HOUR)

    _log_worker_task = await start_export_worker()
    logger.info("Log export worker started")


async def stop_log_services():
    global _log_scheduler, _log_worker_task

    if _log_scheduler:
        _log_scheduler.shutdown(wait=False)
        _log_scheduler = None
    if _log_worker_task:
        _log_worker_task.cancel()
        try:
            await _log_worker_task
        except asyncio.CancelledError:
            pass
        _log_worker_task = None

    await asyncio.to_thread(shutdown_file_executor)


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f}GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f}MB"
    if size_bytes >= 1_024:
        return f"{size_bytes / 1_024:.1f}KB"
    return f"{size_bytes}B"


async def get_export_task(
    session: AsyncSession, task_id: str, user_id: uuid.UUID
) -> LogExportTask | None:
    result = await session.execute(
        select(LogExportTask).where(
            LogExportTask.task_id == task_id,
            LogExportTask.created_by == user_id,
        )
    )
    return result.scalars().first()


async def get_export_tasks_by_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[LogExportTask]:
    result = await session.execute(
        select(LogExportTask)
        .where(LogExportTask.created_by == user_id)
        .order_by(LogExportTask.created_at.desc())
    )
    return list(result.scalars().all())


async def create_loki_export_task(
    session: AsyncSession,
    query_spec: dict,
    source_name: str,
    user_id: uuid.UUID,
) -> str:
    task_id = str(uuid.uuid4())

    task = LogExportTask(
        task_id=task_id,
        task_type="loki-export",
        query_spec=json.dumps(query_spec, ensure_ascii=False),
        source_name=source_name,
        status="pending",
        created_by=user_id,
    )
    session.add(task)
    await session.flush()

    asyncio.create_task(_process_one_export(task_id))

    return task_id


async def _export_worker():
    global _stop_event
    _stop_event = asyncio.Event()

    async def pickup_and_run():
        async with _db.async_session_maker() as session:
            async with session.begin():
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
                await session.execute(
                    update(LogExportTask)
                    .where(
                        LogExportTask.status == "running",
                        LogExportTask.created_at < cutoff,
                    )
                    .values(status="pending")
                )

                result = await session.execute(
                    select(LogExportTask)
                    .where(LogExportTask.status == "pending")
                    .order_by(LogExportTask.created_at.asc())
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                task = result.scalars().first()
                if task is None:
                    return
                task.status = "running"

        await _process_one_export(task.task_id)

    while not _stop_event.is_set():
        try:
            await pickup_and_run()
        except Exception:
            logger.exception("Log export worker error")
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=2.0)
            break
        except asyncio.TimeoutError:
            continue


async def start_export_worker():
    task = asyncio.create_task(_export_worker())
    await asyncio.sleep(0.1)
    return task


async def stop_export_worker():
    global _stop_event
    if _stop_event:
        _stop_event.set()


async def _process_one_export(task_id: str) -> None:
    async with _db.async_session_maker() as claim_session:
        async with claim_session.begin():
            result = await claim_session.execute(
                select(LogExportTask)
                .where(LogExportTask.task_id == task_id)
                .with_for_update(skip_locked=True)
            )
            task = result.scalars().first()
            if task is None:
                return
            if task.status in ("completed", "failed"):
                return
            task.status = "running"

    async with _export_semaphore:
        async with _db.async_session_maker() as session:
            task = await _get_task_by_id(session, task_id)
            if not task:
                return

            try:
                if task.task_type == "loki-export":
                    file_path, file_size = await _do_loki_export(
                        task_id,
                        task.query_spec or "{}",
                        task.source_name or "loki",
                    )
                else:
                    raise ValueError(f"未知的任务类型: {task.task_type}")

                task.file_path = file_path
                task.file_size_bytes = file_size
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()

            except Exception as e:
                await session.rollback()
                task = await _get_task_by_id(session, task_id)
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    await session.commit()


async def _get_task_by_id(
    session: AsyncSession, task_id: str
) -> LogExportTask | None:
    result = await session.execute(
        select(LogExportTask).where(LogExportTask.task_id == task_id)
    )
    return result.scalars().first()


_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)

_LOKI_EXPORT_MAX_PAGES = 2000
_LOKI_EXPORT_PAGE_LIMIT = 5000


def _write_loki_export_zip_sync(archive_file: str, log_name: str, lines: list[str]) -> None:
    import shutil
    import tempfile
    import zipfile

    tmp_dir = tempfile.mkdtemp(prefix="log-loki-export-")
    try:
        tmp_log = os.path.join(tmp_dir, log_name)
        with open(tmp_log, "w", encoding="utf-8") as f:
            f.writelines(lines)
        with zipfile.ZipFile(archive_file, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_log, arcname=log_name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _do_loki_export(
    task_id: str,
    query_spec_raw: str,
    source_name: str,
) -> tuple[str, int]:
    """通过 Loki 分页拉取日志并打包为 zip（loki-export 任务）。"""
    from app.services.loki_export import LokiPagedQuery, LokiQueryClient, query_range_pages

    try:
        spec = json.loads(query_spec_raw)
        query = spec.get("query", "")
        if not query:
            raise ValueError("查询参数缺失: query")
        start = datetime.fromisoformat(spec["start"])
        end = datetime.fromisoformat(spec["end"])
        limit = int(spec.get("limit", _LOKI_EXPORT_PAGE_LIMIT))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"查询参数无效: {e}") from e
    if limit <= 0:
        raise ValueError("查询参数无效: limit 必须大于 0")

    export_path = settings.LOG_EXPORT_PATH
    os.makedirs(export_path, exist_ok=True)
    archive_file = os.path.join(export_path, f"export-{task_id}.zip")

    client = LokiQueryClient()
    try:
        lines: list[str] = []
        total_size = 0
        max_size = settings.LOG_EXPORT_MAX_SIZE_BYTES
        async for batch in query_range_pages(
            LokiPagedQuery(
                client=client,
                query=query,
                start=start,
                end=end,
                limit=limit,
                max_pages=_LOKI_EXPORT_MAX_PAGES,
            )
        ):
            for ts, line in batch:
                ts_iso = (_EPOCH + timedelta(microseconds=ts // 1000)).isoformat()
                entry = f"{ts_iso} {line}\n"
                total_size += len(entry.encode("utf-8"))
                if max_size > 0 and total_size > max_size:
                    raise ValueError(f"导出数据超过大小限制 {_format_size(max_size)}")
                lines.append(entry)

        lines.reverse()  # 分页结果为时间降序，翻转为升序

        raw_filename = (spec.get("filename") or "").strip()
        basename = os.path.basename(raw_filename) if raw_filename else ""
        if basename and re.fullmatch(r"[0-9A-Za-z._-]+", basename):
            log_name = basename
        else:
            log_name = find_merge_virtual_name(raw_filename) or (
                f"{os.path.basename(source_name) or 'loki-export'}.log"
            )
        await asyncio.to_thread(_write_loki_export_zip_sync, archive_file, log_name, lines)
    finally:
        await client.close()

    file_size = os.path.getsize(archive_file)
    return archive_file, file_size


async def delete_export_task(
    session: AsyncSession, task_id: str, user_id: uuid.UUID
) -> bool:
    task = await get_export_task(session, task_id, user_id)
    if not task:
        return False
    if task.file_path and os.path.exists(task.file_path):
        try:
            os.remove(task.file_path)
        except OSError:
            pass
    await session.delete(task)
    await session.flush()
    return True


async def cleanup_expired_exports() -> int:
    loop = asyncio.get_running_loop()
    total_deleted = await loop.run_in_executor(None, _cleanup_expired_sync)

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.LOG_EXPORT_RETENTION_DAYS)
    db_deleted = 0
    async with _db.async_session_maker() as session:
        result = await session.execute(
            select(LogExportTask).where(LogExportTask.created_at < cutoff)
        )
        expired_tasks = result.scalars().all()
        for task in expired_tasks:
            db_deleted += 1
            await session.delete(task)
        await session.commit()

    if db_deleted:
        logger.info("Cleaned up %d expired DB export task records", db_deleted)

    return total_deleted + db_deleted


def _cleanup_expired_sync() -> int:
    import time

    export_path = settings.LOG_EXPORT_PATH
    if not os.path.exists(export_path):
        return 0

    now = time.time()
    cutoff = now - (settings.LOG_EXPORT_RETENTION_DAYS * 86400)
    deleted = 0

    with os.scandir(export_path) as entries:
        for entry in entries:
            if entry.is_file() and (entry.name.startswith("export-") or entry.name.startswith("archive-")):
                if entry.stat().st_mtime < cutoff:
                    try:
                        os.remove(entry.path)
                        deleted += 1
                    except OSError:
                        continue

    return deleted
