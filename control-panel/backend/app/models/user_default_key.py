"""UserDefaultKey ORM — 每个用户的默认 Key 标记表。"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserDefaultKey(Base):
    __tablename__ = "user_default_key"

    uid: Mapped[str] = mapped_column(String(255), primary_key=True)
    key_id: Mapped[int] = mapped_column(
        ForeignKey("litellm_user_key.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    @staticmethod
    async def get_by_uid(db: AsyncSession, uid: str) -> "UserDefaultKey | None":
        result = await db.execute(
            select(UserDefaultKey).where(UserDefaultKey.uid == uid)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def set_default(db: AsyncSession, uid: str, key_id: int) -> None:
        existing = await UserDefaultKey.get_by_uid(db, uid)
        if existing:
            existing.key_id = key_id
        else:
            db.add(UserDefaultKey(uid=uid, key_id=key_id))
        await db.flush()

    @staticmethod
    async def delete_by_uid(db: AsyncSession, uid: str) -> None:
        await db.execute(
            delete(UserDefaultKey).where(UserDefaultKey.uid == uid)
        )
        await db.flush()

    @staticmethod
    async def is_default_key(db: AsyncSession, uid: str, key_id: int) -> bool:
        row = await UserDefaultKey.get_by_uid(db, uid)
        return row is not None and row.key_id == key_id
