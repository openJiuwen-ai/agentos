"""User DTOs and request/response schemas.

Backend-agnostic — these describe the interface boundary between IAM and
the user-system backend, plus the HTTP contract for user CRUD endpoints.
"""

from dataclasses import dataclass
from datetime import datetime


# ── Interface DTOs (backend ↔ IAM) ──────────────────────────────────────


@dataclass
class UserCredentials:
    """Minimal user record the IAM layer needs for auth decisions.

    Returned by ``AbstractUserBackend.authenticate()`` — the login flow uses
    this to issue tokens.
    """
    user_id: str          # UUID as string (stable identifier)
    username: str
    role: str             # "admin" | "user"
    token_version: int
    is_active: bool


@dataclass
class UserRecord:
    """Full user record for CRUD operations.  No ORM coupling."""
    user_id: str
    username: str
    role: str
    is_active: bool
    token_version: int = 0
    created_at: datetime | None = None


@dataclass
class PaginatedUsers:
    """Result of a paginated user listing."""
    items: list[UserRecord]
    total: int
