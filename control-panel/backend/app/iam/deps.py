"""Convenience re-exports — import from one place.

Usage::

    from app.iam.deps import (
        get_current_user, require_admin, require_permission,
        get_user_backend, TokenData, TokenService,
        PermissionService, Resource, Action,
    )
"""

from app.database import get_async_session as get_db_session
from app.iam.permissions import Action, PermissionService, Resource
from app.iam.security import (
    get_current_oauth_user,
    get_current_user,
    get_user_backend,
    require_admin,
    require_permission,
)
from app.iam.tokens import TokenData, TokenService


__all__ = [
    "Action",
    "PermissionService",
    "Resource",
    "TokenData",
    "TokenService",
    "get_current_oauth_user",
    "get_current_user",
    "get_db_session",
    "get_user_backend",
    "require_admin",
    "require_permission",
]
