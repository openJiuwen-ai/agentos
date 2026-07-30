import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.iam.security import require_admin
from app.iam.tokens import TokenData
from app.schemas.litellm import ApiResponse
from app.schemas.log import (
    ExportCreate,
    FileEntry,
    LogCategoryItem,
    LogExportTaskRead,
    LogComponentRead,
    LOG_CATEGORIES,
    CATEGORY_LABELS,
)
from app.services.log_component_config import (
    get_components,
    get_component_by_id,
    get_category_counts,
)
from app.config import settings
from app.services.log_export import (
    create_export_task,
    create_archive_task,
    get_export_task,
    get_export_tasks_by_user,
    delete_export_task,
    _format_size,
)
from app.services.log_component import get_component_by_id as _db_get_component_by_id

router = APIRouter(prefix="/api/v1/logs", tags=["日志中心"])


@router.get(
    "/categories",
    summary="获取日志分类列表及每个分类的组件数量",
    response_model=ApiResponse[list[LogCategoryItem]],
)
async def list_categories(
    _admin: TokenData = Depends(require_admin),
):
    counts = get_category_counts()
    all_components = get_components()
    category_component: dict[str, str] = {}
    for c in all_components:
        if c.category not in category_component:
            category_component[c.category] = c.id
    items = [
        LogCategoryItem(
            key=cat,
            label=CATEGORY_LABELS.get(cat, cat),
            count=counts.get(cat, 0),
            component_id=category_component.get(cat, ""),
        )
        for cat in LOG_CATEGORIES
    ]
    return ApiResponse(data=items)


def _count_dir_entries(dir_path: str) -> int:
    try:
        return len(os.listdir(dir_path))
    except OSError:
        return 0


@router.get(
    "/components",
    summary="获取日志组件列表，可按 category 过滤",
    response_model=ApiResponse[list[LogComponentRead]],
)
async def list_components(
    category: str | None = Query(None),
    _admin: TokenData = Depends(require_admin),
):
    config_components = get_components(category=category)
    result = [
        LogComponentRead(
            id=c.id,
            category=c.category,
            name=c.name,
            log_path=c.path,
            description=c.description,
            size=_count_dir_entries(c.path),
        )
        for c in config_components
    ]
    return ApiResponse(data=result)


def _resolve_safe_path(base_dir: str, user_path: str) -> str:
    resolved = os.path.realpath(os.path.join(base_dir, user_path))
    real_base = os.path.realpath(base_dir)
    if not resolved.startswith(real_base + os.sep) and resolved != real_base:
        raise HTTPException(status_code=403, detail="PATH_TRAVERSAL_DENIED")
    return resolved


def _get_component_path(component_id: str, username: str = "") -> str | None:
    comp = get_component_by_id(component_id)
    if not comp:
        return None
    path = comp.path
    if username:
        path = path.replace("{username}", username)
    return path


@router.get(
    "/components/{component_id}/files",
    summary="获取组件目录下的文件和子目录列表",
    response_model=ApiResponse[list[FileEntry]],
)
async def list_component_files(
    component_id: str,
    admin: TokenData = Depends(require_admin),
):
    base_dir = _get_component_path(component_id, admin.username)
    if not base_dir:
        raise HTTPException(status_code=404, detail="COMPONENT_NOT_FOUND")

    entries: list[FileEntry] = []
    try:
        with os.scandir(base_dir) as it:
            for entry in it:
                try:
                    st = entry.stat()
                except OSError:
                    continue
                entries.append(FileEntry(
                    name=entry.name,
                    path=entry.path,
                    size=st.st_size if entry.is_file() else 0,
                    modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    is_dir=entry.is_dir(),
                ))
    except FileNotFoundError:
        pass
    except OSError as e:
        raise HTTPException(status_code=500, detail="DIRECTORY_READ_ERROR") from e

    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return ApiResponse(data=entries)


@router.post(
    "/components/{component_id}/files/archive",
    summary="创建文件/目录打包下载任务",
    status_code=201,
    response_model=ApiResponse[dict],
)
async def create_archive(
    component_id: str,
    path: str = Query(""),
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    base_dir = _get_component_path(component_id, admin.username)
    if not base_dir:
        raise HTTPException(status_code=404, detail="COMPONENT_NOT_FOUND")

    target_path = _resolve_safe_path(base_dir, path) if path else base_dir
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="PATH_NOT_FOUND")

    task_id = await create_archive_task(
        session,
        target_path,
        os.path.basename(target_path),
        uuid.UUID(admin.user_id),
    )
    return ApiResponse(data={"task_id": task_id, "status": "pending"})


@router.post(
    "/files/download-task",
    summary="创建文件下载任务（进入任务中心）",
    status_code=201,
    response_model=ApiResponse[dict],
)
async def create_file_download_task(
    component_id: str = Query(...),
    name: str = Query(...),
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    base_dir = _get_component_path(component_id, admin.username)
    if not base_dir:
        raise HTTPException(status_code=404, detail="COMPONENT_NOT_FOUND")

    target_path = _resolve_safe_path(base_dir, name)
    if not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    max_size = settings.LOG_EXPORT_MAX_SIZE_BYTES
    if max_size > 0 and os.path.getsize(target_path) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制 {_format_size(max_size)}",
        )

    task_id = await create_archive_task(
        session, target_path, name, uuid.UUID(admin.user_id)
    )
    return ApiResponse(data={"task_id": task_id, "status": "pending"})



@router.get(
    "/exports",
    summary="获取当前用户的导出任务列表",
    response_model=ApiResponse[list[LogExportTaskRead]],
)
async def list_exports(
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    tasks = await get_export_tasks_by_user(session, uuid.UUID(admin.user_id))
    result = []
    for t in tasks:
        item = LogExportTaskRead.model_validate(t)
        if t.task_type == "archive" and t.source_name:
            item.component_name = t.source_name
        elif t.component_id:
            component = await _db_get_component_by_id(session, t.component_id)
            if component:
                item.component_name = component.name
                item.component_category = component.category
        result.append(item)
    return ApiResponse(data=result)


@router.get(
    "/exports/{task_id}",
    summary="获取导出任务状态",
    response_model=ApiResponse[LogExportTaskRead],
)
async def get_export_status(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    task = await get_export_task(session, task_id, uuid.UUID(admin.user_id))
    if not task:
        raise HTTPException(status_code=404, detail="EXPORT_TASK_NOT_FOUND")
    return ApiResponse(data=LogExportTaskRead.model_validate(task))


@router.get(
    "/exports/{task_id}/download",
    summary="下载导出文件",
)
async def download_export(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    task = await get_export_task(session, task_id, uuid.UUID(admin.user_id))
    if not task:
        raise HTTPException(status_code=404, detail="EXPORT_TASK_NOT_FOUND")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="EXPORT_NOT_READY")
    if not task.file_path or not os.path.exists(task.file_path):
        raise HTTPException(status_code=404, detail="EXPORT_FILE_NOT_FOUND")

    return FileResponse(
        task.file_path,
        media_type="application/zip",
        filename=f"logs-export-{task_id}.zip",
    )


@router.delete(
    "/exports/{task_id}",
    summary="删除导出任务及文件",
    status_code=204,
)
async def remove_export(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    deleted = await delete_export_task(session, task_id, uuid.UUID(admin.user_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="EXPORT_TASK_NOT_FOUND")
    return None
