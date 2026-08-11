"""Auth API routes: login, refresh, logout, verify, permissions.

Thin orchestration layer — delegates to ``iam.auth_service`` for logic and
``iam.deps`` for dependency injection.  Backend-agnostic.
"""

import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.database import get_async_session
from app.iam.auth_service import login, refresh_tokens, revoke_user_tokens
from app.iam.deps import (
    get_current_user,
    get_user_backend,
    PermissionService,
    TokenData,
    TokenService,
)
from app.iam.schemas import LoginRequest, LogoutRequest, RefreshRequest, VerifyRequest
from app.services.base import AbstractUserBackend

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login_endpoint(
    body: LoginRequest,
    backend: AbstractUserBackend = Depends(get_user_backend),
):
    """Login with username + password, return dual tokens."""
    result = await login(body.username, body.password, backend)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"code": 200, "message": "success", "data": result}


@router.post("/refresh")
async def refresh_endpoint(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_async_session),
    backend: AbstractUserBackend = Depends(get_user_backend),
):
    """Exchange refresh_token for new token pair."""
    result = await refresh_tokens(body.refresh_token, db, backend)
    if result is None:
        raise HTTPException(status_code=401, detail="refresh_token 无效或已被吊销")
    return {"code": 200, "message": "success", "data": result}


@router.post("/logout")
async def logout_endpoint(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_async_session),
    _user: TokenData = Depends(get_current_user),
):
    """Revoke refresh_token by updating user_revocation."""
    payload = TokenService.decode_refresh_token(body.refresh_token)
    if payload:
        await revoke_user_tokens(payload["sub"], db)
    return {"code": 200, "message": "success", "data": {"ok": True}}


@router.post("/verify")
async def verify_endpoint(body: VerifyRequest):
    """Verify token + resource-level permission.  For iframe apps and middleware."""
    token_data = TokenService.verify_access_token(body.token)
    if not token_data:
        return {"code": 200, "data": {"valid": False, "authorized": False}}

    authorized = PermissionService.check(
        token_data.role, body.resource_id, body.action_id
    )
    return {
        "code": 200,
        "data": {
            "valid": True,
            "authorized": authorized,
            "user_id": token_data.user_id,
            "username": token_data.username,
            "role": token_data.role,
        },
    }


@router.get("/permissions")
async def permissions_endpoint(
    user: TokenData = Depends(get_current_user),
):
    """Return full permission matrix for current user.  Zero IO."""
    perms = PermissionService.get_permissions(user.role)
    return {
        "code": 200,
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "permissions": perms,
        },
    }


def _parse_token_from_uri(uri: str) -> str:
    """从 URI 的 query string 中提取 token 参数."""
    if "?" not in uri:
        return ""
    query = uri.split("?", 1)[1]
    parsed = parse_qs(query)
    return parsed.get("token", [""])[0]


@router.get("/proxy-verify")
async def proxy_verify_endpoint(
    request: Request
):
    """nginx auth_request 回查端点 — 从 Header / cookie 读取 JWT。

    nginx 通过 ``auth_request /auth-proxy`` 调用此端点，并通过
    ``proxy_set_header X-Original-URI $request_uri`` 传递原始请求 URI。
    URI 中 token 只用一次（首次页面加载），之后走 cookie。
    成功后从响应头 ``X-WEBAUTH-USER`` 获取用户名注入 Grafana 请求。
    """
    token = ""

    original_uri = request.headers.get("X-Original-URI", "")
    if original_uri:
        token = _parse_token_from_uri(original_uri)
        
    if not token:
        token = request.cookies.get("grafana_token", "")

    if not token:
        logger.warning("proxy-verify: no token in URI or cookie")
        raise HTTPException(status_code=401, detail="未登录")

    token_data = TokenService.verify_access_token(token)
    if not token_data:
        logger.warning("proxy-verify: token verify failed")
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    if token_data.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问日志 Dashboard")

    resp = Response(
        status_code=200,
        headers={
            "X-WEBAUTH-USER": token_data.username,
            "X-WEBAUTH-ROLE": token_data.role,
            "Cache-Control": "no-store",
        },
    )
    return resp
