"""Abstract interface for pluggable user-system backends.

The IAM layer consumes this interface — it never touches ORM models directly.
Backend selection via ``settings.USER_SYSTEM_BACKEND``.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.user import PaginatedUsers, UserCredentials, UserRecord


class AbstractUserBackend(ABC):
    """Pluggable user-system backend.

    Responsibilities (user CRUD + password verification):
      - Authenticate a raw password against the stored hash
      - Create, read, update, delete users
      - Manage password changes and token_version bumps
      - Seed initial admin at application startup

    What it does **not** own:
      - JWT issuance / verification    (handled by ``iam.tokens``)
      - Permission checks              (handled by ``iam.permissions``)
      - Token revocation               (handled by ``iam.auth_service`` + ``iam.engine``)
      - Auth middleware / FastAPI Depends (handled by ``iam.security``)
    """

    # ── Authentication ──────────────────────────────────────────────

    @abstractmethod
    async def authenticate(
        self, username: str, password: str
    ) -> UserCredentials | None:
        """Verify credentials.  Returns ``None`` on failure."""
        ...

    # ── User CRUD ───────────────────────────────────────────────────

    @abstractmethod
    async def get_user_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        """Look up a single user by UUID."""
        ...

    @abstractmethod
    async def get_user_by_username(self, username: str) -> UserRecord | None:
        """Look up a single user by username."""
        ...

    @abstractmethod
    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        sort: str = "created_at",
        order: str = "desc",
        search: str | None = None,
    ) -> PaginatedUsers:
        """Paginated user list, optionally filtered by username search."""
        ...

    @abstractmethod
    async def create_user(
        self,
        username: str,
        password: str | None = None,
    ) -> tuple[UserRecord, str | None]:
        """Create a user.  Returns ``(record, generated_password_or_None)``."""
        ...

    @abstractmethod
    async def update_user(
        self, user_id: uuid.UUID, update_dict: dict[str, Any]
    ) -> UserRecord:
        """Partial update (role, is_active, etc.)."""
        ...

    @abstractmethod
    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Delete a user and associated resources."""
        ...

    # ── Password management ─────────────────────────────────────────

    @abstractmethod
    async def change_password(
        self, user_id: uuid.UUID, old_password: str, new_password: str
    ) -> None:
        """Verify old, set new, bump token_version.  Raises ValueError."""
        ...

    @abstractmethod
    async def reset_password(self, user_id: uuid.UUID) -> str:
        """Admin-forced password reset.  Returns new plaintext password."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────

    @abstractmethod
    async def seed_initial_admin(self) -> None:
        """Idempotent initial-admin creation."""
        ...

    @abstractmethod
    async def on_startup(self) -> None:
        """Create engine, tables, etc."""
        ...

    @abstractmethod
    async def on_shutdown(self) -> None:
        """Dispose engine, cleanup."""
        ...

    # ── Engine access (for IAM layer DB access) ─────────────────────

    @abstractmethod
    def get_engine(self) -> AsyncEngine | None:
        """Return the backend's engine for IAM layer DB access.

        DB backends return their async engine.
        HTTP backend returns None (no local DB).
        """
        ...
