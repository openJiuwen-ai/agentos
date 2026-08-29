"""Build task and agent registration models."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


@dataclass
class CreateAgentRegistrationParams:
    framework: str
    framework_version: str
    installer_path: str
    agent_name: str
    display_name: str


class AgentRegistration(Base):
    """Local metadata supplement for a card registered remotely."""

    __tablename__ = "agent_registrations"

    framework: Mapped[str] = mapped_column(String(256), primary_key=True)
    framework_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    installer_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    @classmethod
    async def list_all(cls, session: AsyncSession) -> list["AgentRegistration"]:
        result = await session.execute(select(cls))
        return list(result.scalars().all())

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        framework: str,
        framework_version: str,
    ) -> "AgentRegistration | None":
        return await session.get(cls, (framework, framework_version))

    @classmethod
    async def upsert(
        cls,
        session: AsyncSession,
        params: CreateAgentRegistrationParams,
    ) -> "AgentRegistration":
        record = await session.merge(cls(**vars(params)))
        await session.commit()
        return record

    @classmethod
    async def delete_by_key(
        cls,
        session: AsyncSession,
        framework: str,
        framework_version: str,
    ) -> None:
        record = await cls.get(session, framework, framework_version)
        if record is not None:
            await session.delete(record)
            await session.commit()


class ConcurrentBuildLimitError(Exception):
    """Too many builds are already in progress."""


class BuildTask(Base):
    __tablename__ = "build_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    installer_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    @classmethod
    async def list_all(cls, session: AsyncSession) -> list["BuildTask"]:
        result = await session.execute(select(cls).order_by(cls.created_at.desc()))
        return list(result.scalars().all())

    @classmethod
    async def get_by_path(cls, session: AsyncSession, path: str) -> list["BuildTask"]:
        result = await session.execute(
            select(cls)
            .where(cls.installer_path == path)
            .order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_by_id(cls, session: AsyncSession, task_id: str) -> "BuildTask | None":
        return await session.get(cls, task_id)

    @classmethod
    async def try_insert(
        cls,
        session: AsyncSession,
        task: "BuildTask",
        *,
        max_concurrent: int = 2,
    ) -> tuple["BuildTask", bool]:
        active = await session.execute(
            select(cls)
            .where(
                cls.installer_path == task.installer_path,
                cls.status.in_(["pending", "building"]),
            )
            .order_by(cls.created_at.desc())
        )
        existing = active.scalars().first()
        if existing is not None:
            return existing, False
        count = await session.scalar(
            select(func.count())
            .select_from(cls)
            .where(cls.status.in_(["pending", "building"]))
        )
        if (count or 0) >= max_concurrent:
            raise ConcurrentBuildLimitError(
                f"max concurrent builds ({max_concurrent}) reached"
            )
        session.add(task)
        await session.commit()
        return task, True

    @classmethod
    async def mark_building(cls, session: AsyncSession, task_id: str) -> None:
        task = await cls.get_by_id(session, task_id)
        if task is not None:
            task.status = "building"
            task.started_at = datetime.now(timezone.utc)
            await session.commit()

    @classmethod
    async def update_progress(
        cls, session: AsyncSession, task_id: str, progress: int
    ) -> None:
        task = await cls.get_by_id(session, task_id)
        if task is not None:
            task.progress = progress
            await session.commit()

    @classmethod
    async def mark_done(
        cls,
        session: AsyncSession,
        task_id: str,
        image: str,
        image_digest: str,
    ) -> None:
        task = await cls.get_by_id(session, task_id)
        if task is not None:
            task.status = "done"
            task.progress = 100
            task.image = image
            task.image_digest = image_digest
            task.finished_at = datetime.now(timezone.utc)
            await session.commit()

    @classmethod
    async def mark_failed(
        cls, session: AsyncSession, task_id: str, message: str
    ) -> None:
        task = await cls.get_by_id(session, task_id)
        if task is not None:
            task.status = "failed"
            task.error_message = message[:1024]
            task.finished_at = datetime.now(timezone.utc)
            await session.commit()

    @classmethod
    async def delete_by_path(cls, session: AsyncSession, path: str) -> None:
        await session.execute(delete(cls).where(cls.installer_path == path))
        await session.commit()
