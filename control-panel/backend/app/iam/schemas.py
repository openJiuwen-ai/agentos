"""Auth request/response schemas — HTTP contract for IAM endpoints."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    username: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class VerifyRequest(BaseModel):
    token: str
    resource_id: str
    action_id: str


class VerifyResponse(BaseModel):
    valid: bool
    authorized: bool = False
    user_id: str | None = None
    username: str | None = None
    role: str | None = None


class PermissionsResponse(BaseModel):
    user_id: str
    username: str
    role: str
    permissions: dict[str, list[str]]
