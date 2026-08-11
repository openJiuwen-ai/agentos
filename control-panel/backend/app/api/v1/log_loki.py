from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.iam.deps import TokenData
from app.iam.security import require_admin
from app.schemas.litellm import ApiResponse
from app.services.loki_export import LokiQueryClient

router = APIRouter(prefix="/api/v1/logs/loki", tags=["日志中心-Loki"])

_loki_client: LokiQueryClient | None = None


async def _get_loki() -> LokiQueryClient:
    global _loki_client
    if _loki_client is None:
        _loki_client = LokiQueryClient()
    return _loki_client


class LokiQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    start: str = Field(..., description="ISO 8601 datetime string")
    end: str = Field(..., description="ISO 8601 datetime string")
    limit: int = Field(default=5000, ge=1, le=5000)
    direction: str = Field(default="backward")


_FORBIDDEN_LOGQL = ("drop", "delete", "create", "update", "insert")


def _validate_logql(query: str) -> None:
    q_lower = query.lower()
    for kw in _FORBIDDEN_LOGQL:
        if f" {kw} " in f" {q_lower} " or q_lower.startswith(kw):
            raise HTTPException(status_code=400, detail=f"LogQL 包含禁止的关键字: {kw}")


@router.post("/query", response_model=ApiResponse[dict])
async def loki_query(
    body: LokiQueryRequest,
    _admin: TokenData = Depends(require_admin),
):
    _validate_logql(body.query)
    from datetime import datetime

    try:
        start = datetime.fromisoformat(body.start)
        end = datetime.fromisoformat(body.end)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式无效，需为 ISO 8601") from ValueError

    client = await _get_loki()
    result = await client.query_range(
        query=body.query,
        start=start,
        end=end,
        limit=body.limit,
        direction=body.direction,
    )
    return ApiResponse(data=result)


@router.get("/labels", response_model=ApiResponse[list[str]])
async def loki_labels(
    _admin: TokenData = Depends(require_admin),
):
    client = await _get_loki()
    labels = await client.labels()
    return ApiResponse(data=labels)


@router.get("/labels/{name}/values", response_model=ApiResponse[list[str]])
async def loki_label_values(
    name: str,
    _admin: TokenData = Depends(require_admin),
):
    client = await _get_loki()
    values = await client.label_values(name)
    return ApiResponse(data=values)
