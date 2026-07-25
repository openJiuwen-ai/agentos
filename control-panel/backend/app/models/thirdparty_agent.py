"""AgentInstaller and BuildTask ORM models — pure SQLAlchemy 2.0."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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
    async def count_active(session: AsyncSession) -> int:
        from sqlalchemy import func
        result = await session.execute(
            select(func.count()).select_from(BuildTask)
            .where(BuildTask.status.in_(["pending", "building"])))
        return result.scalar() or 0

    @staticmethod
    async def create(session: AsyncSession, agent_name: str, version: str, task_id: str
                     ) -> "BuildTask":
        task = BuildTask(
            task_id=task_id, agent_name=agent_name, version=version,
            status="pending", progress=0, created_at=datetime.now(timezone.utc))
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task

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
    async def mark_failed(session: AsyncSession, task_id: str) -> None:
        task = await session.get(BuildTask, task_id)
        if task is not None:
            task.status = "failed"
            task.finished_at = datetime.now(timezone.utc)
        await session.commit()
