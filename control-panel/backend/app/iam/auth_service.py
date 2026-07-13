"""Auth service — login / refresh / logout orchestration.

Calls ``AbstractUserBackend`` for user operations, delegates token work to
``TokenService``.  Backend-agnostic.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.tokens import TokenService
from app.services.base import AbstractUserBackend


async def login(
    username: str,
    password: str,
    backend: AbstractUserBackend,
) -> dict | None:
    """Authenticate via *backend*, issue dual tokens via ``TokenService``."""
    creds = await backend.authenticate(username, password)
    if creds is None:
        return None

    return {
        "access_token": TokenService.create_access_token(
            creds.user_id, creds.username, creds.role
        ),
        "refresh_token": TokenService.create_refresh_token(
            creds.user_id, creds.token_version
        ),
        "user_id": creds.user_id,
        "username": creds.username,
        "role": creds.role,
    }


async def refresh_tokens(
    refresh_token: str,
    db: AsyncSession,
    backend: AbstractUserBackend,
) -> dict | None:
    """Validate refresh_token and issue a new token pair.

    Delegates to ``TokenService.refresh_tokens`` which handles revocation
    checks and user lookup via the backend.
    """
    return await TokenService.refresh_tokens(refresh_token, db, backend)


async def revoke_user_tokens(user_id: str, db: AsyncSession) -> None:
    """Revoke all refresh tokens for *user_id*."""
    await TokenService.revoke_user_tokens(user_id, db)
