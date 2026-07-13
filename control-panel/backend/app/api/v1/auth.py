"""Auth API routes: login, refresh, logout, verify, permissions.

Thin orchestration layer — delegates to ``iam.auth_service`` for logic and
``iam.deps`` for dependency injection.  Backend-agnostic.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
