import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.iam.deps import TokenData
from app.iam.security import require_admin
from app.schemas.litellm import ApiResponse
from app.schemas.log import CATEGORY_LABELS, LOG_CATEGORIES
from app.services.log_export import create_loki_export_task
from app.services.loki_export import LokiQueryClient
from app.services.log_component_config import get_components, merge_relative_paths

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


class LokiExportRequest(BaseModel):
    category: str | None = Field(None, max_length=64)
    keyword: str | None = Field(None, max_length=4096)
    host: str | None = Field(None, max_length=256)
    ip: str | None = Field(None, max_length=256)
    filename: str | None = Field(None, max_length=1024)
    start: str = Field(..., description="ISO 8601 datetime string")
    end: str = Field(..., description="ISO 8601 datetime string")
    limit: int = Field(default=5000, ge=1, le=5000)


_FORBIDDEN_LOGQL = ("drop", "delete", "create", "update", "insert")

_UNSAFE_SELECTOR_CHARS = ('"', "{", "}", "`", "\n", "\r")


def _validate_logql(query: str) -> None:
    q_lower = query.lower()
    for kw in _FORBIDDEN_LOGQL:
        if f" {kw} " in f" {q_lower} " or q_lower.startswith(kw):
            raise HTTPException(status_code=400, detail=f"LogQL 包含禁止的关键字: {kw}")


def _safe_regex_value(value: str | None, field: str) -> str:
    value = (value or "").strip()
    if any(ch in value for ch in _UNSAFE_SELECTOR_CHARS):
        raise HTTPException(status_code=400, detail=f"{field} 包含非法字符")
    return value or ".+"


def _normalize_loki_ip(ip: str | None) -> str | None:
    """主节点 Alloy 的 ip 标签为部署时生成的主节点地址（deploy.sh 用 NODE_EXPORTER_HOST
    替换模板默认值 127.0.0.1，缺省为本机检测 IP），而前端拿到的主节点地址同样是
    NODE_EXPORTER_HOST，这里做归一化映射"""
    if not ip:
        return ip
    master_host = settings.NODE_EXPORTER_HOST.strip()
    if master_host and ip in ("127.0.0.1", master_host, "0.0.0.0"):
        return master_host
    return ip


def _build_export_logql(
    category: str | None,
    host: str | None,
    ip: str | None,
    filename: str | None,
    keyword: str | None,
) -> str:
    selectors = [
        f'category=~"{_safe_regex_value(category, "category")}"',
        f'host=~"{_safe_regex_value(host, "host")}"',
        f'filename=~"{_safe_regex_value(filename, "filename")}"',
    ]
    loki_ip = _normalize_loki_ip(ip)
    if loki_ip:
        selectors.append(f'ip="{_safe_regex_value(loki_ip, "ip")}"')
    query = "{" + ",".join(selectors) + "}"
    kw = (keyword or "").strip()
    if kw:
        kw = kw.replace("\\", "\\\\").replace('"', '\\"')
        query += f' |~ "(?i){kw}"'
    return query


@router.post("/query", response_model=ApiResponse[dict])
async def loki_query(
    body: LokiQueryRequest,
    _admin: TokenData = Depends(require_admin),
):
    _validate_logql(body.query)

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


@router.post("/export", response_model=ApiResponse[dict])
async def loki_export_task(
    body: LokiExportRequest,
    session: AsyncSession = Depends(get_session),
    admin: TokenData = Depends(require_admin),
):
    """创建 Loki 日志导出任务（进入任务中心）。"""
    try:
        start = datetime.fromisoformat(body.start)
        end = datetime.fromisoformat(body.end)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式无效，需为 ISO 8601") from ValueError
    if start >= end:
        raise HTTPException(status_code=400, detail="start 必须早于 end")

    if body.category and body.category not in LOG_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效的 category: {body.category}")

    query = _build_export_logql(body.category, body.host, body.ip, body.filename, body.keyword)
    _validate_logql(query)

    spec = {
        "query": query,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": body.limit,
        "filename": body.filename,
    }
    source_name = CATEGORY_LABELS.get(body.category or "", "Loki日志")
    task_id = await create_loki_export_task(
        session, spec, source_name, uuid.UUID(admin.user_id)
    )
    return ApiResponse(data={"task_id": task_id, "status": "pending"})


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
    query: str | None = Query(None, description="可选 LogQL 选择器，过滤标签值"),
    _admin: TokenData = Depends(require_admin),
):
    client = await _get_loki()
    values = await client.label_values(name, query=query)
    return ApiResponse(data=values)


# 节点地址允许 IP/主机名字符，禁止引号、花括号、空格等，避免 LogQL 注入
_IP_RE = re.compile(r"^[0-9A-Za-z.:_-]+$")


@router.get("/filenames", response_model=ApiResponse[list[str]])
async def loki_filenames(
    ip: str = Query(..., description="节点 IP（主节点/从节点）"),
    category: str | None = Query(None, description="日志分类，用于限定路径范围"),
    _admin: TokenData = Depends(require_admin),
):
    """获取指定节点已采集日志的文件路径列表（供日志中心抽屉构建目录树）。

    数据来源 Loki，不再直接读文件系统：
    1. GET /loki/api/v1/label/filename/values 获取全部已采集文件路径
    2. 执行 query={ip="xxx"}（label values API 原生支持 query 过滤，等价于两步合并）
    """
    if not _IP_RE.fullmatch(ip):
        raise HTTPException(status_code=400, detail="无效的节点 IP")

    # 主节点 Alloy 的 ip 标签为部署时生成的主节点地址（deploy.sh 用 NODE_EXPORTER_HOST
    # 替换模板默认值 127.0.0.1，缺省为本机检测 IP），而前端拿到的主节点地址同样是
    # NODE_EXPORTER_HOST，这里做归一化映射
    loki_ip = _normalize_loki_ip(ip) or ip

    selector = f'{{ip="{loki_ip}"'
    if category:
        if not get_components(category):
            raise HTTPException(status_code=404, detail="COMPONENT_NOT_FOUND")
        selector += f', category="{category}"'
    selector += "}"

    client = await _get_loki()

    # 直接用 range 查询提取 filename 标签（Loki 3.x instant query 不支持纯日志选择器）
    now = datetime.now(timezone.utc)
    result = await client.query_range(
        selector,
        start=now - timedelta(days=30),
        end=now,
        limit=5000,
    )
    values = sorted(
        {
            stream.get("stream", {}).get("filename")
            for stream in result.get("data", {}).get("result", [])
            if stream.get("stream", {}).get("filename")
        }
    )

    # 转换为组件相对路径（便于前端构建目录树，也兼容日志预览的路径解析）
    if category:
        comp = get_components(category)[0]
        base = comp.path.rstrip("/")
        relative_paths: list[str] = []
        for path in values:
            if path == base:
                # 组件本身就是一个文件（如 agent-gateway 的 gateway.log）
                rel = os.path.basename(base)
            elif path.startswith(base + "/"):
                rel = os.path.relpath(path, base)
            else:
                continue
            if rel and rel != ".":
                relative_paths.append(rel)
        return ApiResponse(data=merge_relative_paths(comp, relative_paths))

    return ApiResponse(data=sorted(set(values)))
