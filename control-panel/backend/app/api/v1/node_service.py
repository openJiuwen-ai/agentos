"""Node service proxy routes — forwards requests to per-node agentos-node-service.

The frontend never calls node-service directly.  All requests go through this
proxy layer which resolves a node ID (``master``, ``worker-1``, …) to the
actual ``host:port`` and forwards the request with the caller's JWT token.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer

from app.config import settings
from app.iam.deps import Action, Resource, require_permission
from app.iam.tokens import TokenData

logger = logging.getLogger("app.node_service")

router = APIRouter(prefix="/api/v1/node-service", tags=["推理服务管理"])

_require_admin = require_permission(Resource.NODE_SERVICE, Action.MANAGE)

_bearer = HTTPBearer(auto_error=False)

# Shared async client — created lazily, closed in lifespan cleanup.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


# ── Helpers ──────────────────────────────────────────────────────────────


def _resolve_url(node: str) -> str:
    """Resolve node ID → node-service base URL."""
    target = settings.resolve_node(node)
    if not target:
        raise HTTPException(status_code=404, detail=f"未知节点: {node}")
    host = settings.NODE_SERVICE_HOST or target.host
    return f"http://{host}:{settings.NODE_SERVICE_PORT}"


def _auth_headers(credentials) -> dict[str, str]:
    """Build forwarding headers with the caller's JWT token."""
    headers: dict[str, str] = {"Accept": "application/json"}
    if credentials and hasattr(credentials, "credentials"):
        headers["Authorization"] = f"Bearer {credentials.credentials}"
    return headers


async def _proxy_get(
    node: str,
    path: str,
    params: dict | None = None,
    credentials=None,
) -> dict:
    """Forward a GET request to the target node-service."""
    base = _resolve_url(node)
    url = f"{base}{path}"
    headers = _auth_headers(credentials)
    try:
        resp = await _get_client().get(url, headers=headers, params=params)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"节点 {node} 的 node-service 不可达",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"节点 {node} 的 node-service 响应超时",
        ) from exc
    return _relay(resp)


async def _proxy_post(
    node: str,
    path: str,
    json: dict | None = None,
    credentials=None,
) -> dict:
    """Forward a POST request to the target node-service."""
    base = _resolve_url(node)
    url = f"{base}{path}"
    headers = _auth_headers(credentials)
    try:
        resp = await _get_client().post(url, headers=headers, json=json)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"节点 {node} 的 node-service 不可达",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"节点 {node} 的 node-service 响应超时",
        ) from exc
    return _relay(resp)


async def _proxy_put(
    node: str,
    path: str,
    json: dict | None = None,
    credentials=None,
) -> dict:
    """Forward a PUT request to the target node-service."""
    base = _resolve_url(node)
    url = f"{base}{path}"
    headers = _auth_headers(credentials)
    try:
        resp = await _get_client().put(url, headers=headers, json=json)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"节点 {node} 的 node-service 不可达",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"节点 {node} 的 node-service 响应超时",
        ) from exc
    return _relay(resp)


def _relay(resp: httpx.Response) -> dict:
    """Relay the upstream response body, preserving status code on error."""
    try:
        body = resp.json()
    except Exception:
        body = {"message": resp.text}
    if resp.status_code >= 400:
        # 提取 node-service 返回的错误信息，避免双重包装
        detail = body.get("detail") or body.get("message") or str(body)
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return body


# ── Routes ───────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config(
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """获取节点的当前简化配置。"""
    return await _proxy_get(node, "/inference/config", credentials=credentials)


@router.put("/config")
async def update_config(
    node: str = Query(..., description="节点 ID"),
    body: dict = ...,
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """局部更新节点配置（merge 语义）。"""
    return await _proxy_put(node, "/inference/config", json=body, credentials=credentials)


@router.post("/start")
async def start_service(
    node: str = Query(..., description="节点 ID"),
    body: dict | None = None,
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """异步启动推理服务（返回 202，轮询 /status 获取进度）。"""
    return await _proxy_post(node, "/inference/start", json=body or {}, credentials=credentials)


@router.post("/stop")
async def stop_service(
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """停止并移除推理服务容器。"""
    return await _proxy_post(node, "/inference/stop", credentials=credentials)


@router.post("/restart")
async def restart_service(
    node: str = Query(..., description="节点 ID"),
    body: dict | None = None,
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """异步重启推理服务（先停再起，返回 202）。"""
    return await _proxy_post(node, "/inference/restart", json=body or {}, credentials=credentials)


@router.get("/status")
async def get_status(
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """获取推理服务状态（含启动进度 start_progress）。"""
    return await _proxy_get(node, "/inference/status", credentials=credentials)


@router.get("/health")
async def get_health(
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """获取推理服务健康状态。"""
    return await _proxy_get(node, "/inference/health", credentials=credentials)


@router.get("/logs")
async def get_logs(
    node: str = Query(..., description="节点 ID"),
    lines: int = Query(100, ge=1, le=1000, description="返回日志行数"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """获取推理服务最近日志。"""
    return await _proxy_get(
        node, "/inference/logs", params={"lines": lines}, credentials=credentials
    )


@router.get("/templates")
async def get_templates(
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """获取可用配置模板列表（系统预设 + 用户自定义）。"""
    return await _proxy_get(node, "/inference/templates", credentials=credentials)


@router.get("/templates/{name}")
async def get_template(
    name: str,
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """获取指定配置模板内容。"""
    return await _proxy_get(
        node, f"/inference/templates/{name}", credentials=credentials
    )


@router.post("/templates")
async def save_template(
    node: str = Query(..., description="节点 ID"),
    body: dict = ...,
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """将当前配置保存为新模板。"""
    return await _proxy_post(
        node, "/inference/templates", json=body, credentials=credentials
    )


@router.delete("/templates/{name}")
async def delete_template(
    name: str,
    node: str = Query(..., description="节点 ID"),
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """删除用户自定义模板（系统预设不可删）。"""
    base = _resolve_url(node)
    url = f"{base}/inference/templates/{name}"
    headers = _auth_headers(credentials)
    try:
        resp = await _get_client().delete(url, headers=headers)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"节点 {node} 的 node-service 不可达",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"节点 {node} 的 node-service 响应超时",
        ) from exc
    return _relay(resp)


@router.post("/config/apply-template")
async def apply_template(
    node: str = Query(..., description="节点 ID"),
    body: dict = ...,
    _user: TokenData = Depends(_require_admin),
    credentials=Depends(_bearer),
):
    """应用模板（覆盖当前 user_config + 简化配置）。"""
    return await _proxy_post(
        node, "/inference/config/apply-template", json=body, credentials=credentials
    )
