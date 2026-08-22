"""Auth middleware: FastAPI dependencies for JWT verification and permission checks.

All dependencies are zero-IO (pure JWT decode + in-memory permission lookup).
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from app.iam.permissions import PermissionService
from app.iam.tokens import TokenData, TokenService
from app.services.base import AbstractUserBackend

security = HTTPBearer(auto_error=False)


async def get_user_backend() -> AbstractUserBackend:
    """Inject the configured user-system backend.

    Uses lazy-loading factory so the backend is only instantiated once.
    Must be defined before ``get_current_oauth_user`` because the latter
    references it as a default argument (``Depends(get_user_backend)``),
    which is evaluated at function-definition time during module import.
    """
    from app.services import get_user_backend as _get_backend

    return _get_backend()


async def get_current_user(
    credentials=Depends(security),
) -> TokenData:
    """Zero-IO JWT verification.  Every authenticated request calls this."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
        )
    token_data = TokenService.verify_access_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )
    return token_data


async def get_current_oauth_user(
    credentials=Depends(security),
    backend: AbstractUserBackend = Depends(get_user_backend),
) -> dict:
    """OAuth2 access token 校验 + 查库确认用户存在且 active。

    仿照 ``get_current_user``：用 ``HTTPBearer`` 抽取 Bearer token，
    再用 ``TokenService.verify_oauth2_access_token`` 校验 JWT（仅接受
    ``type=oauth2_access``，拒绝登录 JWT）；JWT 通过后查库确认用户存在
    且 ``is_active``，禁用的用户 token 立即失效。

    返回 RFC 6749 风格的用户身份 ``{id, username, login, name}``。
    失败统一 401 ``{"error": "invalid_token"}``。
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    payload = TokenService.verify_oauth2_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    user = await backend.get_user_by_id(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    username = user.username
    return {
        "id": payload["sub"],
        "username": username,
        "login": username,
        "name": username,
    }


def require_admin(
    user: TokenData = Depends(get_current_user),
) -> TokenData:
    """Admin-only routes.  Zero IO — string comparison."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user


def require_permission(resource: str, action: str):
    """Resource-level permission guard.  Zero IO.

    Usage::

        @router.get("/models")
        async def list_models(
            user: TokenData = Depends(require_permission(Resource.INFERENCE_MODELS, Action.READ)),
        ):
            ...
    """

    async def checker(
        user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        if not PermissionService.check(user.role, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要权限: {action} on {resource}",
            )
        return user

    return checker
