import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.iam.security import require_admin
from app.iam.tokens import TokenData
from app.schemas.litellm import ApiResponse
from app.schemas.log import (
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
    build_merge_regex,
)
from app.services.log_export import (
    get_export_task,
    get_export_tasks_by_user,
    delete_export_task,
)
from app.services.local_users.models import User
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
    session: AsyncSession = Depends(get_session),
    _admin: TokenData = Depends(require_admin),
):
    config_components = get_components(category=category)
    result = []
    for c in config_components:
        if c.id == "jiuwenswarm":
            size = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        else:
            size = _count_dir_entries(c.path)
        result.append(LogComponentRead(
            id=c.id,
            category=c.category,
            name=c.name,
            log_path=c.path,
            description=c.description,
            size=size,
        ))
    return ApiResponse(data=result)


def _resolve_safe_path(base_dir: str, user_path: str) -> str:
    resolved = os.path.realpath(os.path.join(base_dir, user_path))
    real_base = os.path.realpath(base_dir)
    if not resolved.startswith(real_base + os.sep) and resolved != real_base:
        raise HTTPException(status_code=403, detail="PATH_TRAVERSAL_DENIED")
    return resolved


@router.get(
    "/components/{component_id}/resolve-path",
    summary="根据组件和相对路径解析完整文件路径",
    response_model=ApiResponse[dict],
)
async def resolve_file_path(
    component_id: str,
    subpath: str = Query(...),
    admin: TokenData = Depends(require_admin),
):
    comp = get_component_by_id(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="COMPONENT_NOT_FOUND")
    base_dir = comp.path
    if admin.username:
        base_dir = base_dir.replace("{username}", admin.username)

    if os.path.isfile(base_dir):
        return ApiResponse(data={"resolved_path": os.path.realpath(base_dir)})

    merge_regex = build_merge_regex(comp, subpath)
    if merge_regex:
        return ApiResponse(data={"resolved_path": merge_regex})

    resolved = _resolve_safe_path(base_dir, subpath)
    return ApiResponse(data={"resolved_path": resolved})


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
        if t.task_type in ("archive", "loki-export") and t.source_name:
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
