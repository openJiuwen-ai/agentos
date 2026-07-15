"""LitellmUserKey ORM — UID ↔ Key 映射表"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    Text,
    UniqueConstraint,
    Index,
    select,
    func,
    delete,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


@dataclass
class CreateKeyExtras:
    """收敛 ``create()`` 的可选参数（满足参数个数限制）。"""

    model: str | None = None
    expires_at: datetime | None = None
    key_name: str | None = None


class LitellmUserKey(Base):
    __tablename__ = "litellm_user_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(255), nullable=False)
    key_alias: Mapped[str] = mapped_column(String(512), nullable=False)
    key_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    bound_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("uid", "key_alias", name="uq_user_key_uid_alias"),
        Index("idx_user_key_uid", "uid"),
    )

    @staticmethod
    async def exists_by_uid(db: AsyncSession, uid: str) -> bool:
        result = await db.execute(
            select(LitellmUserKey).where(LitellmUserKey.uid == uid).limit(1)
        )
        return result.scalars().first() is not None

    @staticmethod
    async def create(
        db: AsyncSession,
        uid: str,
        key_alias: str,
        key: str,
        extras: CreateKeyExtras | None = None,
    ) -> "LitellmUserKey":
        extras = extras or CreateKeyExtras()
        record = LitellmUserKey(
            uid=uid,
            key_alias=key_alias,
            key_name=extras.key_name,
            bound_model=extras.model,
            key=key,
            expires_at=extras.expires_at,
        )
        db.add(record)
        await db.flush()
        return record

    @staticmethod
    async def count_by_uid(db: AsyncSession, uid: str) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(LitellmUserKey)
            .where(LitellmUserKey.uid == uid)
        )
        return result.scalar() or 0

    @staticmethod
    async def list_by_uid(db: AsyncSession, uid: str) -> list["LitellmUserKey"]:
        result = await db.execute(
            select(LitellmUserKey)
            .where(LitellmUserKey.uid == uid)
            .order_by(LitellmUserKey.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_alias(
        db: AsyncSession,
        key_alias: str,
    ) -> "LitellmUserKey | None":
        result = await db.execute(
            select(LitellmUserKey).where(LitellmUserKey.key_alias == key_alias)
        )
        return result.scalars().first()

    @staticmethod
    async def get_by_uid_and_alias(
        db: AsyncSession,
        uid: str,
        key_alias: str,
    ) -> "LitellmUserKey | None":
        result = await db.execute(
            select(LitellmUserKey).where(
                LitellmUserKey.uid == uid,
                LitellmUserKey.key_alias == key_alias,
            )
        )
        return result.scalars().first()

    @staticmethod
    async def delete_by_uid(db: AsyncSession, uid: str) -> int:
        result = await db.execute(
            delete(LitellmUserKey).where(LitellmUserKey.uid == uid)
        )
        await db.flush()
        return result.rowcount

    @staticmethod
    async def delete_by_uid_and_alias(
        db: AsyncSession,
        uid: str,
        key_alias: str,
    ) -> bool:
        result = await db.execute(
            delete(LitellmUserKey).where(
                LitellmUserKey.uid == uid,
                LitellmUserKey.key_alias == key_alias,
            )
        )
        await db.flush()
        return result.rowcount > 0
