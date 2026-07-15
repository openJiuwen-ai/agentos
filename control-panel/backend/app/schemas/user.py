"""User DTOs and request/response schemas.

Backend-agnostic — these describe the interface boundary between IAM and
the user-system backend, plus the HTTP contract for user CRUD endpoints.
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field


# ── Interface DTOs (backend ↔ IAM) ──────────────────────────────────────


@dataclass
class UserCredentials:
    """Minimal user record the IAM layer needs for auth decisions.

    Returned by ``AbstractUserBackend.authenticate()`` — the login flow uses
    this to issue tokens.
    """

    user_id: str  # UUID as string (stable identifier)
    username: str
    role: str  # "admin" | "user"
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


# ── HTTP request / response schemas ─────────────────────────────────────


class BatchCreateRequest(BaseModel):
    usernames: list[str] = Field(..., min_length=1, max_length=100)


class BatchCreateUserItem(BaseModel):
    username: str
    user_id: str | None = None
    password: str | None = None
    error: str | None = None


class UserItem(BaseModel):
    user_id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


class UpdateUserRequest(BaseModel):
    is_active: bool | None = None


class ResetPasswordResponse(BaseModel):
    user_id: str
    new_password: str
