"""Key 管理路由 — 薄层，调用 LitellmService

[用户] 用户自助查询、申请、删除自己的 API Key。

认证：使用 IAM ``get_current_user``（JWT 验证 → TokenData.user_id）。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.litellm_deps import get_litellm_svc
from app.iam.deps import get_current_user, TokenData
from app.services.litellm_service import (
    LitellmService,
    LitellmConnectionError,
    LitellmUpstreamError,
    MaxKeysReachedError,
    KeyNotFoundError,
)
from app.schemas.litellm import (
    ApiResponse,
    KeyApplyRequest,
    KeyListResponse,
    KeyGenerated,
    OkResult,
)

router = APIRouter(prefix="/api/v1/litellm/key", tags=["Key 管理"])


@router.get(
    "",
    response_model=ApiResponse[KeyListResponse],
    summary="查询 Key 列表",
    description="查询当前用户的所有 API Key。直查本地表，不调 LiteLLM API。",
)
async def list_keys(
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    user: TokenData = Depends(get_current_user),
):
    data = await svc.list_keys(db, uid=user.user_id)
    return ApiResponse(data=data)


@router.post(
    "/generate",
    response_model=ApiResponse[KeyGenerated],
    summary="申请 Key",
    description="为当前用户生成一个新的 API Key。调 LiteLLM，加密写入本地。",
)
async def apply_key(
    body: KeyApplyRequest = KeyApplyRequest(),
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    user: TokenData = Depends(get_current_user),
):
    try:
        data = await svc.apply_key(
            db, uid=user.user_id, model=body.model, key_name=body.key_name,
        )
        return ApiResponse(data=data)
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except MaxKeysReachedError as e:
        raise HTTPException(status_code=403, detail="Key数量已达上限") from e


@router.delete(
    "/{key_alias}",
    response_model=ApiResponse[OkResult],
    summary="删除 Key",
    description="删除当前用户的 API Key。先校验归属，再调 LiteLLM 删除，最后清本地映射。",
)
async def delete_key(
    key_alias: str,
    db: AsyncSession = Depends(get_session),
    svc: LitellmService = Depends(get_litellm_svc),
    user: TokenData = Depends(get_current_user),
):
    try:
        data = await svc.delete_key(db, uid=user.user_id, key_alias=key_alias)
        return ApiResponse(data=data)
    except LitellmUpstreamError as e:
        raise HTTPException(status_code=502, detail=e.detail) from e
    except LitellmConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except KeyNotFoundError as e:
        raise HTTPException(status_code=404, detail="Key not found") from e
