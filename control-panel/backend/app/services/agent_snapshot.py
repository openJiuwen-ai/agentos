"""Agent instance snapshot service.

Maintains an in-memory snapshot of all agent instances fetched from the
agent register.  All filtering / sorting / pagination is done on the
snapshot — the agent register backend is only called on first access or explicit
refresh.

Module-level globals (``_snapshot``, ``_lock``) are intentional: the
snapshot is shared across all admin users and has no lifecycle
management needs (no connection pool, no resource cleanup).
"""

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SnapshotQuery:
    """收敛 query() 的查询参数。"""

    page: int = 1
    size: int = 10
    sort: str | None = None
    keyword: str | None = None
    status: str | None = None
    framework: str | None = None

# ── 可排序字段（不含 framework 和 status — 这两个有筛选无排序） ──
_SORTABLE_FIELDS = frozenset(
    {
        "service_id",
        "framework_version",
        "address",
        "node",
        "user",
        "created_at",
        "last_active_at",
    }
)

# ── 搜索字段（9 个可见字段） ──
_SEARCH_FIELDS = (
    "service_id",
    "framework",
    "status",
    "user",
    "framework_version",
    "address",
    "node",
    "created_at",
    "last_active_at",
)

_FETCH_TIMEOUT = 30.0


# ─── 私有辅助函数 ──────────────────────────────────────────────────────────────


def _compute_overview(snapshot: list[dict[str, Any]]) -> dict[str, int]:
    """计算全量概览计数（仅在快照加载/刷新时调用一次）。"""
    running = 0
    abnormal = 0
    stopped = 0
    for i in snapshot:
        status = i.get("status")
        if status == "运行":
            running += 1
        elif status == "异常":
            abnormal += 1
        elif status is None:
            # 注册中心只返回 "运行"/"异常" 两种状态；缺失(None)归一为"已停止"
            stopped += 1
    return {
        "total": len(snapshot),
        "running": running,
        "abnormal": abnormal,
        "stopped": stopped,
    }


def _match_keyword(item: dict[str, Any], kw_lower: str) -> bool:
    """检查实例是否匹配关键词（9 字段部分匹配）。"""
    for f in _SEARCH_FIELDS:
        val = item.get(f)
        if val is not None:
            if kw_lower in str(val).lower():
                return True
    return False


def _match_status(item: dict[str, Any], status_list: list[str]) -> bool:
    """检查实例状态是否在选中列表中。"""
    status = item.get("status")
    # 注册中心只返回 "运行"/"异常"；缺失(None)归一为"已停止"。
    # 筛选协议：运行/异常 用中文(=数据原值)，stopped 用英文合成 sentinel
    # (None 无法作为 checkbox value)，故命名不一致属有意为之。
    if status is None:
        return "stopped" in status_list
    return status in status_list


def _version_key(v: str) -> tuple:
    """版本号排序 key：数字段按数值比、非数字段按字符串比，类型隔离保证可比。

    例：``v1.10.0`` 正确大于 ``v1.4.0``（字典序会误判）。无法解析的纯文本
    段归入第 1 组，排在数字版本之后。
    """
    key: list[tuple[int, int, str]] = []
    for p in re.split(r"(\d+)", v.lstrip("vV")):
        if p.isdigit():
            key.append((0, int(p), ""))
        elif p:
            key.append((1, 0, p))
    return tuple(key)


# ─── 异常类 ────────────────────────────────────────────────────────────────────


class AgentSnapshotError(Exception):
    """快照服务基础异常。子类设置 status_code 和 detail。"""

    status_code: int = 500
    detail: str = "服务内部错误"


class AgentRegisterNotConfiguredError(AgentSnapshotError):
    status_code = 503

    def __init__(self):
        self.detail = "注册中心服务未配置，智能体监控不可用"
        logger.warning("Agent register backend not configured (AGENT_REGISTER_URL empty)")
        super().__init__(self.detail)


class AgentRegisterUnreachableError(AgentSnapshotError):
    status_code = 502

    def __init__(self):
        self.detail = "注册中心后端不可达"
        logger.warning("Agent register unreachable")
        super().__init__(self.detail)


class AgentRegisterTimeoutError(AgentSnapshotError):
    status_code = 504
    detail = "注册中心后端响应超时（30s）"


class AgentRegisterUpstreamError(AgentSnapshotError):
    status_code = 502

    def __init__(self, upstream_status: int, upstream_detail: str = ""):
        self.detail = f"注册中心后端返回错误：{upstream_status}"
        logger.warning("Agent register upstream error: %d %s", upstream_status, upstream_detail)
        super().__init__(self.detail)


class AgentRegisterDataFormatError(AgentSnapshotError):
    status_code = 502
    detail = "注册中心后端返回数据格式异常"


# ─── 模块级全局 ────────────────────────────────────────────────────────────────

_snapshot: list[dict[str, Any]] | None = None
_overview: dict[str, int] = {"total": 0, "running": 0, "abnormal": 0, "stopped": 0}
_lock: asyncio.Lock | None = None


# ─── 私有：从注册中心拉取全量 ──────────────────────────────────────────────────────


async def _fetch_from_registry() -> list[dict[str, Any]]:
    """调用注册中心 ``GET /api/instances?size=-1&include_unhealthy=true`` 拉全量。

    超时 30s，异常映射为 ``AgentSnapshotError`` 子类。
    """
    if not settings.agent_register_enabled:
        raise AgentRegisterNotConfiguredError()
    url = f"{settings.AGENT_REGISTER_URL.strip().rstrip('/')}/api/instances"
    params = {"size": -1, "include_unhealthy": "true"}

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException as e:
        raise AgentRegisterTimeoutError() from e
    except (httpx.ConnectError, httpx.NetworkError) as e:
        raise AgentRegisterUnreachableError() from e

    if response.status_code >= 400:
        upstream_detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                upstream_detail = str(
                    body.get("detail", body.get("error", body.get("message", "")))
                )
        except Exception:
            upstream_detail = response.text[:200]
        raise AgentRegisterUpstreamError(response.status_code, upstream_detail)

    try:
        data = response.json()
    except Exception as e:
        raise AgentRegisterDataFormatError() from e

    if not isinstance(data, list):
        raise AgentRegisterDataFormatError()

    if not all(isinstance(i, dict) for i in data):
        raise AgentRegisterDataFormatError()

    return data


# ─── 公开：快照管理 ────────────────────────────────────────────────────────────


async def ensure_snapshot(refresh: bool = False) -> None:
    """保证快照已加载。

    - 首次访问（快照为空）：调一次注册中心，存入快照。
    - ``refresh=True``：强制调注册中心，整体替换快照引用。
    - 其他：直接返回，不调注册中心。

    使用 double-checked locking + ``asyncio.Lock`` 保证并发安全。
    """
    global _snapshot, _overview, _lock

    if not refresh and _snapshot is not None:
        return

    if _lock is None:
        _lock = asyncio.Lock()

    async with _lock:
        # Double-check：排队期间可能已被其他请求填充
        if not refresh and _snapshot is not None:
            return

        new_data = await _fetch_from_registry()
        # 原子引用替换，禁止 clear()/extend() 逐条修改
        _snapshot = new_data
        _overview = _compute_overview(new_data)
        logger.info("agent snapshot loaded: %d instances", len(new_data))


# ─── 公开：在快照上查询 ────────────────────────────────────────────────────────


def query(q: SnapshotQuery) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """在快照上做全量计数 + 搜索 + 筛选 + 排序 + 分页。

    返回 ``(items, total, overview_dict)``：
    - ``items``：当前页实例数组
    - ``total``：筛选后总条数（分页用）
    - ``overview_dict``：``{"total", "running", "abnormal", "stopped"}`` 全量计数（概览卡用）
    """
    snapshot = _snapshot or []

    # ── 全量计数（从缓存读取，不受筛选影响） ──
    overview = _overview

    # ── 参数归一化 ──
    effective_page = q.page if q.page and q.page >= 1 else 1
    effective_size = q.size if q.size and q.size >= 1 else 10
    kw = (q.keyword or "").strip()
    fw = (q.framework or "").strip()

    # ── 搜索（在 9 个可见字段中部分匹配） ──
    items: list[dict[str, Any]] = snapshot
    if kw:
        kw_lower = kw.lower()
        items = [i for i in items if _match_keyword(i, kw_lower)]

    # ── 筛选：status（逗号分隔多选）→ framework（部分匹配） ──
    if q.status:
        status_list = [s.strip() for s in q.status.split(",") if s.strip()]
        if status_list:
            items = [i for i in items if _match_status(i, status_list)]

    if fw:
        fw_lower = fw.lower()
        items = [
            i
            for i in items
            if fw_lower in str(i.get("framework") or "").lower()
        ]

    # ── 排序（null 排末尾） ──
    if q.sort:
        parts = [p.strip() for p in q.sort.split(":")]
        field = parts[0] if parts else ""
        order = parts[1] if len(parts) > 1 else "asc"
        if field in _SORTABLE_FIELDS and order in ("asc", "desc"):
            non_null = [i for i in items if i.get(field) is not None]
            null_items = [i for i in items if i.get(field) is None]
            sort_key = (
                (lambda x: _version_key(str(x.get(field))))
                if field == "framework_version"
                else (lambda x: str(x.get(field)))
            )
            non_null.sort(
                key=sort_key,
                reverse=(order == "desc"),
            )
            items = non_null + null_items
        else:
            logger.warning("invalid sort param: %s, ignored", q.sort)

    # ── 分页 ──
    total = len(items)
    start = (effective_page - 1) * effective_size
    end = start + effective_size
    page_items = items[start:end] if start < total else []

    return page_items, total, overview


def total_pages(total: int, size: int) -> int:
    """计算总页数，至少为 1。"""
    effective_size = size if size and size >= 1 else 10
    if total <= 0:
        return 1
    return max(1, math.ceil(total / effective_size))
