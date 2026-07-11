"""UserRevocation model — revoke refresh tokens by user-level timestamp."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRevocation(Base):
    __tablename__ = "user_revocation"

    user_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, nullable=False
    )
    revoked_after: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
