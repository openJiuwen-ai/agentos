"""TokenService — JWT issuance, verification, refresh, and revocation.

Backend-agnostic: consumes ``AbstractUserBackend`` for user lookups,
uses ``UserRevocation`` directly (IAM infrastructure, not backend-specific).
"""

import secrets
import time
import uuid
from dataclasses import dataclass

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user_revocation import UserRevocation
from app.services.base import AbstractUserBackend


@dataclass
class TokenData:
    """Decoded access-token payload.  Zero-IO — extracted from JWT claims."""

    user_id: str  # UUID
    username: str
    role: str


class TokenService:
    """Stateless JWT issuance, verification, and refresh validation."""

    # ── Issuance ────────────────────────────────────────────────────

    @staticmethod
    def create_access_token(user_id: str, username: str, role: str) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "sub": user_id,
                "username": username,
                "role": role,
                "type": "access",
                "jti": secrets.token_hex(16),
                "iat": now,
                "exp": now + settings.AGENTOS_JWT_ACCESS_EXPIRE_MINUTES * 60,
            },
            settings.AGENTOS_JWT_SECRET_KEY,
            algorithm=settings.AGENTOS_JWT_ALGORITHM,
        )

    @staticmethod
    def create_refresh_token(user_id: str, token_version: int) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "sub": user_id,
                "type": "refresh",
                "tv": token_version,
                "jti": secrets.token_hex(16),
                "iat": now,
                "exp": now + settings.AGENTOS_JWT_REFRESH_EXPIRE_DAYS * 86400,
            },
            settings.AGENTOS_JWT_SECRET_KEY,
            algorithm=settings.AGENTOS_JWT_ALGORITHM,
        )

    # ── Verification (zero-IO) ──────────────────────────────────────

    @staticmethod
    def verify_access_token(token: str) -> TokenData | None:
        """Hot path.  Zero IO — pure JWT decode."""
        try:
            payload = jwt.decode(
                token,
                settings.AGENTOS_JWT_SECRET_KEY,
                algorithms=[settings.AGENTOS_JWT_ALGORITHM],
                options={"require_exp": True},
            )
        except JWTError:
            return None
        if payload.get("type") != "access":
            return None
        return TokenData(
            user_id=payload["sub"],
            username=payload["username"],
            role=payload["role"],
        )

    @staticmethod
    def decode_refresh_token(token: str) -> dict | None:
        """Decode and validate refresh token (signature + type check).  Zero IO."""
        try:
            payload = jwt.decode(
                token,
                settings.AGENTOS_JWT_SECRET_KEY,
                algorithms=[settings.AGENTOS_JWT_ALGORITHM],
                options={"require_exp": True},
            )
        except JWTError:
            return None
        if payload.get("type") != "refresh":
            return None
        return payload

    # ── Refresh (cold path — DB access for revocation + user lookup) ─

    @staticmethod
    async def refresh_tokens(
        refresh_token: str,
        db: AsyncSession | None,
        backend: AbstractUserBackend,
    ) -> dict | None:
        """Cold path: validate refresh_token, check revocation + token_version,
        issue new pair.

        Uses *backend* for the user lookup (backend-agnostic).
        Uses *db* directly for ``UserRevocation`` when available (IAM infrastructure).
        When *db* is ``None`` (HTTP backend), revocation check is skipped.
        """
        payload = TokenService.decode_refresh_token(refresh_token)
        if not payload:
            return None

        user_id = payload["sub"]

        # Revocation check — only when DB is available
        if db is not None:
            result = await db.execute(
                select(UserRevocation).where(UserRevocation.user_id == user_id)
            )
            rev = result.scalar_one_or_none()
            if rev and payload["iat"] < rev.revoked_after:
                return None  # token issued before revocation → invalid

        # Look up user via backend (not direct ORM)
        user = await backend.get_user_by_id(uuid.UUID(user_id))
        if user is None or not user.is_active:
            return None

        # Check token_version
        if payload.get("tv", 0) != user.token_version:
            return None

        return {
            "access_token": TokenService.create_access_token(
                user.user_id, user.username, user.role
            ),
            "refresh_token": TokenService.create_refresh_token(
                user.user_id, user.token_version
            ),
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
        }

    # ── Revocation ──────────────────────────────────────────────────

    @staticmethod
    async def revoke_user_tokens(user_id: str, db: AsyncSession) -> None:
        """Upsert ``user_revocation`` with current Unix timestamp.

        All refresh tokens for this user issued before this moment become
        invalid.
        """
        now = time.time()
        result = await db.execute(
            select(UserRevocation).where(UserRevocation.user_id == user_id)
        )
        rev = result.scalar_one_or_none()
        if rev:
            rev.revoked_after = now
            rev.updated_at = None  # let DB default kick in on commit
        else:
            db.add(UserRevocation(user_id=user_id, revoked_after=now))
        await db.commit()
