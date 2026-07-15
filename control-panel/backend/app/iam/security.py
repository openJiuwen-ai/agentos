"""Auth middleware: FastAPI dependencies for JWT verification and permission checks.

All dependencies are zero-IO (pure JWT decode + in-memory permission lookup).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from app.iam.permissions import PermissionService
from app.iam.tokens import TokenData, TokenService
from app.services.base import AbstractUserBackend

security = HTTPBearer(auto_error=False)


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


async def get_user_backend() -> AbstractUserBackend:
    """Inject the configured user-system backend.

    Uses lazy-loading factory so the backend is only instantiated once.
    """
    from app.services import get_user_backend as _get_backend

    return _get_backend()
