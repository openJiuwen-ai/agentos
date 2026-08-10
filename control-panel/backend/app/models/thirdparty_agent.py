"""BuildTask and AgentRegistration ORM models — pure SQLAlchemy 2.0."""

from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.thirdparty_agent.exceptions import ThirdpartyAgentError


class ConcurrentBuildLimitError(ThirdpartyAgentError):
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
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    @staticmethod
    async def get_by_installer_path(session: AsyncSession, installer_path: str
                                    ) -> list["BuildTask"]:
        result = await session.execute(
            select(BuildTask)
            .where(BuildTask.installer_path == installer_path)
            .order_by(BuildTask.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, task_id: str) -> "BuildTask | None":
        return await session.get(BuildTask, task_id)

    @staticmethod
    async def count_active(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(BuildTask)
            .where(BuildTask.status.in_(["pending", "building"])))
        return result.scalar() or 0

    @staticmethod
    async def try_insert(
        session: AsyncSession, task: "BuildTask", *,
        max_concurrent: int,
    ) -> tuple["BuildTask", bool]:
        """Atomically insert *task* if no active task exists for the same installer_path
        and the concurrency limit has not been reached.

        Returns ``(task, True)`` when the task was inserted,
        ``(existing, False)`` when an active task already exists.
        Raises ``ConcurrentBuildLimitError`` when *max_concurrent* has
        been reached.
        """
        # All checks and insert happen inside a single savepoint/transaction
        # to prevent TOCTOU races: two concurrent callers cannot both pass.
        # FastAPI's request session often already auto-began after a prior
        # query (e.g. AgentInstaller.get), so nest when needed.
        tx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx:
            # 1. Active task for same agent+version?
            result = await session.execute(
                select(BuildTask)
                .where(BuildTask.installer_path == task.installer_path,
                       BuildTask.status.in_(["pending", "building"]))
                .order_by(BuildTask.created_at.desc())
            )
            existing = result.scalars().first()
            if existing is not None:
                return (existing, False)

            # 2. Concurrency limit?
            count_r = await session.execute(
                select(func.count()).select_from(BuildTask)
                .where(BuildTask.status.in_(["pending", "building"])))
            if (count_r.scalar() or 0) >= max_concurrent:
                raise ConcurrentBuildLimitError(
                    f"max concurrent builds ({max_concurrent}) reached")

            # 3. All clear — insert; commit/savepoint release on scope exit.
            session.add(task)
            return (task, True)

    @staticmethod
    async def mark_building(session: AsyncSession, task_id: str) -> "BuildTask | None":
        task = await session.get(BuildTask, task_id)
        if task is None:
            return None
        task.status = "building"
        task.started_at = datetime.now(timezone.utc)
        await session.commit()
        return task

    @staticmethod
    async def update_progress(session: AsyncSession, task_id: str, progress: int) -> None:
        task = await session.get(BuildTask, task_id)
        if task is not None:
            task.progress = progress
            await session.commit()

    @staticmethod
    async def mark_done(session: AsyncSession, task_id: str, image: str, image_digest: str) -> None:
        task = await session.get(BuildTask, task_id)
        if task is not None:
            task.status = "done"
            task.progress = 100
            task.image = image
            task.image_digest = image_digest
            task.finished_at = datetime.now(timezone.utc)
        await session.commit()

    @staticmethod
    async def mark_failed(session: AsyncSession, task_id: str,
                          error_message: str = "") -> None:
        task = await session.get(BuildTask, task_id)
        if task is not None:
            task.status = "failed"
            task.finished_at = datetime.now(timezone.utc)
            if error_message:
                task.error_message = error_message
        await session.commit()


@dataclass
class CreateAgentRegistrationParams:
    """Parameters for AgentRegistration.create."""
    framework: str
    framework_version: str
    installer_path: str
    agent_name: str
    display_name: str


class AgentRegistration(Base):
    """Maps tgz installer_path → registry (framework, framework_version)."""

    __tablename__ = "agent_registrations"

    framework: Mapped[str] = mapped_column(String(256), primary_key=True)
    framework_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    installer_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    @staticmethod
    async def get(session: AsyncSession, framework: str, framework_version: str
                   ) -> "AgentRegistration | None":
        result = await session.execute(
            select(AgentRegistration).where(
                AgentRegistration.framework == framework,
                AgentRegistration.framework_version == framework_version))
        return result.scalar_one_or_none()

    @staticmethod
    async def exists_by_path(session: AsyncSession, installer_path: str) -> bool:
        result = await session.execute(
            select(AgentRegistration).where(
                AgentRegistration.installer_path == installer_path))
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(
        session: AsyncSession,
        params: CreateAgentRegistrationParams,
    ) -> "AgentRegistration":
        reg = AgentRegistration(
            framework=params.framework,
            framework_version=params.framework_version,
            installer_path=params.installer_path,
            agent_name=params.agent_name,
            display_name=params.display_name)
        session.add(reg)
        await session.commit()
        return reg
