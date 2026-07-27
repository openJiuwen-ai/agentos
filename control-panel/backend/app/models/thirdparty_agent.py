"""AgentInstaller and BuildTask ORM models — pure SQLAlchemy 2.0."""

from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.thirdparty_agent.exceptions import ThirdpartyAgentError


class ConcurrentBuildLimitError(ThirdpartyAgentError):
    """Too many builds are already in progress."""


@dataclass
class InstallerCreate:
    """Parameters for AgentInstaller.create."""
    agent_name: str
    display_name: str
    version: str
    entrypoint: str
    installer_path: str
    uploaded_by: str


@dataclass
class InstallerUpdate:
    """Parameters for AgentInstaller.update (all optional except keys)."""
    display_name: str = ""
    entrypoint: str = ""
    image_digest: str = ""
    image_path: str = ""
    base_image: str = ""


class AgentInstaller(Base):
    __tablename__ = "agent_installers"

    agent_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    installer_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_image: Mapped[str] = mapped_column(String(256), default="agent-base:1.0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    @staticmethod
    async def exists(session: AsyncSession, agent_name: str, version: str) -> bool:
        return await AgentInstaller.get(session, agent_name, version) is not None

    @staticmethod
    async def get(session: AsyncSession, agent_name: str, version: str) -> "AgentInstaller | None":
        result = await session.execute(
            select(AgentInstaller).where(
                and_(AgentInstaller.agent_name == agent_name, AgentInstaller.version == version)))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(session: AsyncSession) -> list["AgentInstaller"]:
        result = await session.execute(
            select(AgentInstaller).order_by(AgentInstaller.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def create(session: AsyncSession, params: InstallerCreate) -> "AgentInstaller":
        installer = AgentInstaller(
            agent_name=params.agent_name, display_name=params.display_name,
            version=params.version, entrypoint=params.entrypoint,
            installer_path=params.installer_path,
            uploaded_by=params.uploaded_by)
        session.add(installer)
        await session.commit()
        await session.refresh(installer)
        return installer

    @staticmethod
    async def update(
        session: AsyncSession, agent_name: str, version: str, *,
        params: InstallerUpdate,
    ) -> None:
        installer = await AgentInstaller.get(session, agent_name, version)
        if installer is not None:
            if params.display_name:
                installer.display_name = params.display_name
            if params.entrypoint:
                installer.entrypoint = params.entrypoint
            if params.image_digest:
                installer.image_digest = params.image_digest
            if params.image_path:
                installer.image_path = params.image_path
            if params.base_image:
                installer.base_image = params.base_image
            await session.commit()


class BuildTask(Base):
    __tablename__ = "build_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
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
    async def get_by_name(session: AsyncSession, agent_name: str, version: str
                          ) -> list["BuildTask"]:
        result = await session.execute(
            select(BuildTask)
            .where(and_(BuildTask.agent_name == agent_name, BuildTask.version == version))
            .order_by(BuildTask.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, task_id: str) -> "BuildTask | None":
        return await session.get(BuildTask, task_id)

    @staticmethod
    async def latest_for(session: AsyncSession, agent_name: str, version: str
                         ) -> "BuildTask | None":
        result = await session.execute(
            select(BuildTask)
            .where(and_(BuildTask.agent_name == agent_name,
                        BuildTask.version == version))
            .order_by(BuildTask.created_at.desc())
            .limit(1))
        return result.scalars().first()

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
        """Atomically insert *task* if no active task exists for the same key
        and the concurrency limit has not been reached.

        Returns ``(task, True)`` when the task was inserted,
        ``(existing, False)`` when an active task already exists.
        Raises ``ConcurrentBuildLimitError`` when *max_concurrent* has
        been reached.
        """
        # Use a savepoint (nested transaction) so this is safe to call
        # inside an existing transaction without side effects.
        async with session.begin_nested():
            # 1. Active task for same agent+version?
            result = await session.execute(
                select(BuildTask)
                .where(and_(BuildTask.agent_name == task.agent_name,
                            BuildTask.version == task.version),
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

            # 3. All clear — insert and commit on scope exit.
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
