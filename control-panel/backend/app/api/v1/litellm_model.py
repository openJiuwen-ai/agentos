"""模型管理路由 — 薄层，调用 LitellmService

[管理员] 模型的增删改查，底层调 LiteLLM Admin API，扩展字段存面板本地。

认证：使用 IAM ``require_admin``（JWT 验证 + 角色检查）。
"""

import asyncio
import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.litellm_deps import get_litellm_svc
from app.iam.deps import get_current_user, require_admin, TokenData
from app.services.litellm_service import (
    CreateModelExtras,
    UpdateModelExtras,
    LitellmService,
    LitellmConnectionError,
    LitellmUpstreamError,
    LitellmServiceError,
)
from app.schemas.litellm import (
    ApiResponse,
    ModelCreate,
    ModelItem,
    ModelUpdate,
    ModelUpdated,
    PaginatedModels,
    ModelCreated,
    OkResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/litellm/model", tags=["模型管理"])

_sync_timer_task: asyncio.Task | None = None
_SYNC_DELAY = 300  # 5 分钟防抖窗口


def _fire_agentos_sync() -> None:
    """模型变更后防抖同步：5 分钟内的多次变更只同步一次。"""
    global _sync_timer_task
    if _sync_timer_task is not None and not _sync_timer_task.done():
        return  # 定时器已在运行，到期后会查最新模型列表
    _sync_timer_task = asyncio.create_task(_delayed_agentos_sync())


async def _delayed_agentos_sync() -> None:
    """延迟 5 分钟后执行全量同步，用最新模型列表重建所有用户 agentos。"""
    global _sync_timer_task
    from app.services.local_users.backend import _sync_all_users_agentos

    try:
        await asyncio.sleep(_SYNC_DELAY)
        await _sync_all_users_agentos()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.warning("延迟同步 agentos 失败", exc_info=True)
    finally:
        _sync_timer_task = None


def _mask_model_for_user(data: dict | None, is_admin: bool) -> dict | None:
    """非管理员脱敏：用 LiteLLM 网关地址替换真实 api_base，移除 api_key。"""
    if data is None or is_admin:
        return data
    masked = dict(data)
    params = dict(masked.get("litellm_params") or {})
    params["api_base"] = settings.LITELLM_ADMIN_URL or ""
    params.pop("api_key", None)
    masked["litellm_params"] = params
    return masked


@dataclass
class ListModelsQuery:
    """模型列表查询参数。"""

    page: int = Query(1, ge=1, description="页码")
    page_size: int = Query(20, ge=1, le=100, description="每页条数")
    model_name: str | None = Query(None, description="按名称过滤，同名返回多条")
    keyword: str | None = Query(None, description="关键词搜索（匹配名称）")


@router.get(
    "",
    response_model=ApiResponse[PaginatedModels],
    summary="获取模型列表",
    description=(
        "合并 LiteLLM 的模型数据与面板本地扩展字段（`instance_url` 等），"
        "支持内存分页。可通过 model_name 过滤，同名返回多条。"
    ),
)
async def list_models(
    query: ListModelsQuery = Depends(),
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        data = await svc.list_models(
            db,
            page=query.page,
            page_size=query.page_size,
            model_name=query.keyword or query.model_name,
        )
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e
    is_admin = current_user.role == "admin"
    data["items"] = [_mask_model_for_user(it, is_admin) for it in data.get("items", [])]
    return ApiResponse(data=data)


@router.get(
    "/{model_id}",
    response_model=ApiResponse[ModelItem],
    summary="获取单个模型详情",
    description="合并 LiteLLM 模型数据与面板本地扩展字段，通过模型 ID 查询。",
)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        data = await svc.get_model(db, model_id)
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e
    if data is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return ApiResponse(data=_mask_model_for_user(data, current_user.role == "admin"))


@router.post(
    "",
    response_model=ApiResponse[ModelCreated],
    status_code=201,
    summary="添加模型",
    description="向 LiteLLM 注册新模型，并将扩展字段写入面板本地。",
)
async def create_model(
    body: ModelCreate,
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    try:
        data = await svc.create_model(
            db,
            model_name=body.model_name,
            litellm_params=body.litellm_params.model_dump(),
            extras=CreateModelExtras(
                model_info=body.model_info.model_dump() if body.model_info else None,
                instance_url=body.instance_url,
                max_concurrent=body.max_concurrent,
                inference_engine=body.inference_engine,
            ),
        )
        _fire_agentos_sync()
        return ApiResponse(data=data)
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e
    except LitellmServiceError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put(
    "/{model_id}",
    response_model=ApiResponse[ModelUpdated],
    summary="更新模型",
    description="更新 LiteLLM 中已有模型的配置，同时更新面板本地扩展字段。",
)
async def update_model(
    model_id: str,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    logger.info("Updating model: %s", model_id)
    logger.info("Request body litellm_params: %s", body.litellm_params.model_dump())
    logger.info("Request body model_info: %s", body.model_info.model_dump() if body.model_info else None)
    logger.info("Request body instance_url: %s", body.instance_url)
    logger.info("Request body max_concurrent: %s", body.max_concurrent)
    logger.info("Request body inference_engine: %s", body.inference_engine)
    try:
        data = await svc.update_model(
            db,
            model_id=model_id,
            model_name=body.model_name,
            litellm_params=body.litellm_params.model_dump(),
            extras=UpdateModelExtras(
                model_info=body.model_info.model_dump() if body.model_info else None,
                instance_url=body.instance_url,
                max_concurrent=body.max_concurrent,
                inference_engine=body.inference_engine,
            ),
        )
        _fire_agentos_sync()
        return ApiResponse(data=data)
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e
    except LitellmServiceError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete(
    "/{model_id}",
    response_model=ApiResponse[OkResult],
    summary="删除模型",
    description="从 LiteLLM 和面板本地同时删除指定模型。404/400 幂等。",
)
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    try:
        data = await svc.delete_model(db, model_id)
        _fire_agentos_sync()
        return ApiResponse(data=data)
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e


config_router = APIRouter(prefix="/api/v1/maas", tags=["MaaS 配置"])


class GatewayConfig(BaseModel):
    gateway_url: str


@config_router.get(
    "/config",
    response_model=ApiResponse[GatewayConfig],
    summary="获取 Gateway 配置",
    description="返回 MASS Gateway 访问地址，用于用户推理请求接口，所有登录用户申请API-Key后可访问。",
)
async def get_config(
    _current_user: TokenData = Depends(get_current_user),
):
    return ApiResponse(data=GatewayConfig(
        gateway_url=settings.LITELLM_ADMIN_URL,
    ))
