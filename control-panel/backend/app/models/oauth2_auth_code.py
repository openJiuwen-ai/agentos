"""OAuth2 authorization code ORM model + persistence operations."""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, String, delete, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

AUTH_CODE_TTL_MINUTES = 10


class OAuth2AuthorizationCode(Base):
    __tablename__ = "oauth2_authorization_codes"

    code = Column(String(64), primary_key=True)  # secrets.token_hex(32)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    client_id = Column(String(255), nullable=False)
    redirect_uri = Column(String(2048), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: str,
        client_id: str,
        redirect_uri: str,
    ) -> "OAuth2AuthorizationCode":
        """生成 256 位随机授权码并持久化，返回带 code 的实例。"""
        code = secrets.token_hex(32)
        entry = cls(
            code=code,
            user_id=user_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )
        session.add(entry)
        await session.commit()
        return entry

    @classmethod
    async def consume(
        cls, session: AsyncSession, code: str
    ) -> "OAuth2AuthorizationCode | None":
        """查找并原子删除授权码（一次性使用，防重放）。不存在返回 None。"""
        result = await session.execute(
            select(cls).where(cls.code == code).with_for_update()
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        await session.delete(entry)
        await session.commit()
        return entry

    def is_expired(self, *, ttl_minutes: int = AUTH_CODE_TTL_MINUTES) -> bool:
        """是否超过 TTL（created_at 为 naive datetime，用 utcnow 比较）。"""
        cutoff = datetime.utcnow() - timedelta(minutes=ttl_minutes)
        return self.created_at < cutoff

    @classmethod
    async def delete_expired(
        cls, session: AsyncSession, *, ttl_minutes: int = AUTH_CODE_TTL_MINUTES
    ) -> int:
        """删除超过 TTL 的记录，返回删除行数。"""
        cutoff = datetime.utcnow() - timedelta(minutes=ttl_minutes)
        result = await session.execute(delete(cls).where(cls.created_at < cutoff))
        await session.commit()
        return result.rowcount or 0
