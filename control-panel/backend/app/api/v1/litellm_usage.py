"""使用统计路由 — 薄层，调用 LitellmService

直连 PG 查询 LiteLLM 原生 spend 表做聚合，不经过 LiteLLM HTTP API。

权限模型：
- /trend, /user → require_permission(INFERENCE_USAGE, READ)
  非 admin 强制看自己的数据
- /by-model, /by-user, /overview → require_admin（全局汇总数据）
"""

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query

from app.iam.deps import require_admin, require_permission, Resource, Action
from app.iam.tokens import TokenData
from app.litellm_deps import get_litellm_svc
from app.services.litellm_service import LitellmService
from app.schemas.litellm import (
    ApiResponse,
    TrendResponse,
    ModelUsageResponse,
    UserUsageRankResponse,
    UserUsageDetailResponse,
    OverviewResponse,
)

router = APIRouter(prefix="/api/v1/litellm/usage", tags=["使用统计"])

# 框架权限校验
_require_usage_read = require_permission(Resource.INFERENCE_USAGE, Action.READ)


def _resolve_user_id(current_user: TokenData, requested: str | None) -> str | None:
    """非 admin 只能看自己：忽略传入的 user_id，强制替换为当前用户 ID。"""
    if current_user.role == "admin":
        return requested
    return current_user.user_id


def _validate_dates(start_date: str, end_date: str):
    """校验日期范围"""
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be <= end_date")


def _validate_granularity(granularity: str):
    """校验粒度（spend 表按天聚合，仅支持 day）"""
    if granularity != "day":
        raise HTTPException(status_code=422, detail="granularity must be 'day'")


@dataclass
class TrendQueryParams:
    """usage_trend 查询参数封装（满足参数个数限制）。"""

    start_date: str
    end_date: str
    granularity: str = "day"
    user_id: str | None = None


def _trend_query(
    start_date: str = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: str = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    granularity: str = Query("day", description="粒度（仅支持 day）", examples=["day"]),
    user_id: str | None = Query(
        None, description="可选，按用户过滤", examples=["alice"]
    ),
) -> TrendQueryParams:
    return TrendQueryParams(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        user_id=user_id,
    )


@router.get(
    "/trend",
    response_model=ApiResponse[TrendResponse],
    summary="趋势图",
    description=(
        "Token/请求数/成本的每日趋势。直连 PG 查询 `LiteLLM_DailyUserSpend` 表，按日期 GROUP BY 聚合。\n\n"
        "**参数说明**:\n"
        "- `granularity`: 粒度（目前仅支持 `day`，因为 spend 表按天聚合）\n"
        "- `user_id`: 可选，按用户过滤\n\n"
        "**规范**: 需配置 PostgreSQL DATABASE_URL；SQLite 下返回空数据不报错。"
    ),
)
async def usage_trend(
    q: TrendQueryParams = Depends(_trend_query),
    svc: LitellmService = Depends(get_litellm_svc),
    _user: TokenData = Depends(_require_usage_read),
):
    _validate_dates(q.start_date, q.end_date)
    _validate_granularity(q.granularity)
    user_id = _resolve_user_id(_user, q.user_id)
    data = await svc.get_usage_trend(
        start_date=q.start_date,
        end_date=q.end_date,
        granularity=q.granularity,
        user_id=user_id,
    )
    return ApiResponse(data=data)


@router.get(
    "/by-model",
    response_model=ApiResponse[ModelUsageResponse],
    summary="模型用量分布",
    description=(
        "各模型的用量分布及成本占比。直连 PG 按 `model` 列 GROUP BY。\n\n"
        "**返回**: 每模型 tokens、requests、cost、pct（占比百分比）。按 cost 降序。"
    ),
)
async def usage_by_model(
    start_date: str = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: str = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_usage_by_model(start_date=start_date, end_date=end_date)
    return ApiResponse(data=data)


@router.get(
    "/by-user",
    response_model=ApiResponse[UserUsageRankResponse],
    summary="用户用量排行",
    description=(
        "用户用量排行 Top N。直连 PG 按 `user_id` GROUP BY，按 token 用量降序取前 N 名。\n\n"
        "**top 参数**: 默认 10，范围 1-100。"
    ),
)
async def usage_by_user(
    start_date: str = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: str = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    top: int = Query(10, ge=1, le=100, description="返回 Top N 名"),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_usage_by_user(
        start_date=start_date, end_date=end_date, top=top
    )
    return ApiResponse(data=data)


@router.get(
    "/user",
    response_model=ApiResponse[UserUsageDetailResponse],
    summary="指定用户每日活动",
    description=(
        "查询指定用户每日的 Token/请求数/成本明细。直连 PG 按 `user_id` 过滤 + `date` GROUP BY。\n\n"
        "**user_id**: 必填，LiteLLM 用户 ID。"
    ),
)
async def usage_user(
    user_id: str = Query(..., description="用户 ID", examples=["alice"]),
    start_date: str = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: str = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _user: TokenData = Depends(_require_usage_read),
):
    _validate_dates(start_date, end_date)
    user_id = _resolve_user_id(_user, user_id)
    data = await svc.get_user_usage(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return ApiResponse(data=data)


@router.get(
    "/overview",
    response_model=ApiResponse[OverviewResponse],
    summary="全部用户总览",
    description=(
        "全部用户用量总览 + 每日趋势。直连 PG 执行两次查询：\n\n"
        "1. 按 `user_id` GROUP BY → 用户汇总（total_tokens / total_requests / total_cost）\n"
        "2. 按 `date` GROUP BY → 每日趋势\n\n"
        "**适用场景**: 管理员 Dashboard 首页。"
    ),
)
async def usage_overview(
    start_date: str = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: str = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_usage_overview(start_date=start_date, end_date=end_date)
    return ApiResponse(data=data)
