"""Registry-based factory for pluggable user-system backends.

Usage::

    from app.services import get_user_backend
    backend = get_user_backend()
"""

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.base import AbstractUserBackend

logger = logging.getLogger(__name__)

# ── Registry ────────────────────────────────────────────────────────

_BACKEND_REGISTRY: dict[str, str] = {
    "local-users": "app.services.local_users.LocalUsersBackend",
}

# ── Singleton ───────────────────────────────────────────────────────

_backend: "AbstractUserBackend | None" = None


def get_user_backend() -> "AbstractUserBackend":
    """Lazy-load and cache the configured user-system backend singleton.

    Only the selected backend's package is imported — other backends'
    code is never loaded into the process.
    """
    global _backend
    if _backend is not None:
        return _backend

    from app.config import settings

    name = settings.USER_SYSTEM_BACKEND
    if name not in _BACKEND_REGISTRY:
        raise ValueError(
            f"Unknown USER_SYSTEM_BACKEND: {name!r}. "
            f"Available: {list(_BACKEND_REGISTRY)}"
        )

    class_path = _BACKEND_REGISTRY[name]
    module_path, class_name = class_path.rsplit(".", 1)

    logger.info("Loading user-system backend: %s (%s)", name, class_path)

    module = importlib.import_module(module_path)
    backend_class = getattr(module, class_name)
    _backend = backend_class()

    return _backend


def reset_user_backend() -> None:
    """Reset the cached backend (useful for tests that swap configs)."""
    global _backend
    _backend = None


def register_backend(name: str, class_path: str) -> None:
    """Register a new backend type at runtime (for plugins)."""
    _BACKEND_REGISTRY[name] = class_path
