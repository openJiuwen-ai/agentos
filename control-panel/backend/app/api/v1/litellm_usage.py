"""使用统计路由 — 薄层，调用 LitellmService

直连 PG 查询 LiteLLM 原生 spend 表做聚合，不经过 LiteLLM HTTP API。

权限模型：
- /trend, /user, /user-model-trend → require_permission(INFERENCE_USAGE, READ)
  普通用户只能查自己的数据（user_id 从 JWT 取，不接受前端传入）
- /by-model, /by-user, /overview, /model-trend → require_admin（全局汇总数据）
"""

from datetime import date

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
    ModelTrendResponse,
    OverviewResponse,
)

router = APIRouter(prefix="/api/v1/litellm/usage", tags=["使用统计"])

# 框架权限校验
_require_usage_read = require_permission(Resource.INFERENCE_USAGE, Action.READ)


def _validate_dates(start_date: date, end_date: date):
    """校验日期范围（格式由 FastAPI date 类型自动校验）。"""
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be <= end_date")


def _validate_granularity(granularity: str):
    """校验粒度（spend 表按天聚合，仅支持 day）"""
    if granularity != "day":
        raise HTTPException(status_code=422, detail="granularity must be 'day'")


@router.get(
    "/trend",
    response_model=ApiResponse[TrendResponse],
    summary="趋势图",
    description=(
        "Token/请求数/成本的每日趋势。直连 PG 查询 `LiteLLM_SpendLogs` 表，按日期 GROUP BY 聚合。\n\n"
        "**参数说明**:\n"
        "- `granularity`: 粒度（目前仅支持 `day`，因为 spend 表按天聚合）\n\n"
        "**权限**: 普通用户只能查自己的数据。\n"
        "**规范**: 需配置 LITELLM_DATABASE_URL；LiteLLM 未初始化时返回空数据不报错。"
    ),
)
async def usage_trend(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    granularity: str = Query("day", description="粒度（仅支持 day）", examples=["day"]),
    svc: LitellmService = Depends(get_litellm_svc),
    _user: TokenData = Depends(_require_usage_read),
):
    _validate_dates(start_date, end_date)
    _validate_granularity(granularity)
    user_id = _user.user_id if _user.role != "admin" else None
    data = await svc.get_usage_trend(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        user_id=user_id,
    )
    return ApiResponse(data=data)


@router.get(
    "/by-model",
    response_model=ApiResponse[ModelUsageResponse],
    summary="模型用量分布",
    description=(
        "各模型的用量分布及成本占比。直连 PG 按 `model_id + model_group` 聚合，"
        "模型名通过 `LiteLLM_ProxyModelTable` 映射，已删除模型归类为『已删除模型』。\n\n"
        "**返回**: 每模型 tokens、requests、cost、pct（占比百分比）。按请求数降序。\n\n"
        "**权限**: 仅管理员。"
    ),
)
async def usage_by_model(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_usage_by_model(
        start_date=start_date, end_date=end_date
    )
    return ApiResponse(data=data)


@router.get(
    "/model-trend",
    response_model=ApiResponse[ModelTrendResponse],
    summary="模型用量趋势",
    description=(
        "按天+模型分组的调用趋势，供堆叠柱状图使用。"
        "直连 PG 按 `date + model_group` GROUP BY，模型名通过 `LiteLLM_ProxyModelTable` 映射，已删除模型归类为『已删除模型』。\n\n"
        "**权限**: 仅管理员。"
    ),
)
async def usage_model_trend(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_model_trend(
        start_date=start_date, end_date=end_date
    )
    return ApiResponse(data=data)


@router.get(
    "/by-user",
    response_model=ApiResponse[UserUsageRankResponse],
    summary="用户用量排行",
    description=(
        "用户用量排行 Top N。直连 PG 按 `user_id` GROUP BY，按 token 用量降序取前 N 名。\n\n"
        "**top 参数**: 默认 10，范围 1-100。\n\n"
        "**权限**: 仅管理员。"
    ),
)
async def usage_by_user(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    top: int = Query(10, ge=-1, description="返回 Top N 名（-1=全量，0=空，超过实际用户数自动回退到最大值）"),
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
        "查询当前用户每日的 Token/请求数/成本明细及请求成功率。"
        "直连 PG 按 `user_id` 过滤 + `date` GROUP BY。\n\n"
        "**权限**: 普通用户只能查自己的数据。"
    ),
)
async def usage_user(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _user: TokenData = Depends(_require_usage_read),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_user_usage(
        user_id=_user.user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return ApiResponse(data=data)


@router.get(
    "/overview",
    response_model=ApiResponse[OverviewResponse],
    summary="全部用户总览",
    description=(
        "全部用户用量总览 + 每日趋势 + 请求成功率。直连 PG 执行三次查询：\n\n"
        "1. 按 `user_id` GROUP BY → 用户汇总（total_tokens / total_requests / total_cost）\n"
        "2. 按 `date` GROUP BY → 每日趋势（含活跃用户数）\n"
        "3. 按 `status` 统计 → 请求成功率\n\n"
        "**权限**: 仅管理员。\n"
        "**适用场景**: 管理员 Dashboard 首页。"
    ),
)
async def usage_overview(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _admin: TokenData = Depends(require_admin),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_usage_overview(start_date=start_date, end_date=end_date)
    return ApiResponse(data=data)


@router.get(
    "/user-model-trend",
    response_model=ApiResponse[ModelTrendResponse],
    summary="用户模型调用趋势",
    description=(
        "查询当前用户按天+模型分组的调用趋势，供个人视图堆叠柱状图使用。\n\n"
        "**权限**: 普通用户只能查自己的数据。"
    ),
)
async def usage_user_model_trend(
    start_date: date = Query(
        ..., description="开始日期 YYYY-MM-DD", examples=["2026-07-01"]
    ),
    end_date: date = Query(
        ..., description="结束日期 YYYY-MM-DD", examples=["2026-07-09"]
    ),
    svc: LitellmService = Depends(get_litellm_svc),
    _user: TokenData = Depends(_require_usage_read),
):
    _validate_dates(start_date, end_date)
    data = await svc.get_user_model_trend(
        user_id=_user.user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return ApiResponse(data=data)
