"""Agent instance monitoring API.

Exposes ``GET /api/v1/agent/instances`` — a snapshot-backed endpoint that
filters / sorts / paginates agent instances from the agent register.
The agent register backend is only called on first access or explicit refresh;
all other operations work on the in-memory snapshot.
"""

import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query

from app.iam.deps import TokenData, require_admin
from app.services.agent_snapshot import (
    AgentSnapshotError,
    SnapshotQuery,
    ensure_snapshot,
    query,
    total_pages,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["智能体实例监控"])


@dataclass
class AgentQueryParams:
    """收敛 list_instances 路由的查询参数。"""

    page: int = Query(1, ge=1)
    size: int = Query(10, ge=1, le=100)
    sort: str | None = Query(None, max_length=100)
    keyword: str | None = Query(None, max_length=500)
    status: str | None = Query(None, max_length=100)
    framework: str | None = Query(None, max_length=200)
    refresh: bool = Query(False)


@router.get("/instances")
async def list_instances(
    q: AgentQueryParams = Depends(),
    _admin: TokenData = Depends(require_admin),
):
    """Admin: 分页查看全部 agent 实例，支持搜索 / 筛选 / 排序。

    首次访问或 ``refresh=true`` 时调注册中心拉取全量快照；
    其余操作（翻页 / 筛选 / 排序 / 计数）在内存快照上完成。
    """
    try:
        await ensure_snapshot(refresh=q.refresh)
    except AgentSnapshotError as e:
        logger.error("agent snapshot error: %s (status=%d)", e.detail, e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    sq = SnapshotQuery(
        page=q.page,
        size=q.size,
        sort=q.sort,
        keyword=q.keyword,
        status=q.status,
        framework=q.framework,
    )
    items, total, overview = query(sq)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": q.page,
            "page_size": q.size,
            "total_pages": total_pages(total, q.size),
            "overview_total": overview["total"],
            "overview_running": overview["running"],
            "overview_abnormal": overview["abnormal"],
            "overview_stopped": overview["stopped"],
        },
    }
