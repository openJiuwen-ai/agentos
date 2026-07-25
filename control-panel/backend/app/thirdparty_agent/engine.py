"""Table lifecycle for thirdparty_agent module."""

from app.models.thirdparty_agent import AgentInstaller, BuildTask
from app.models.base import Base


async def ensure_thirdparty_agent_tables(engine) -> None:
    """Create thirdparty_agent tables and reset stale build tasks."""
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AgentInstaller.__table__, BuildTask.__table__],
        )

    # Mark any pending/building tasks from a previous run as failed.
    from sqlalchemy import update
    async with engine.begin() as conn:
        await conn.execute(
            update(BuildTask)
            .where(BuildTask.status.in_(["pending", "building"]))
            .values(status="failed")
        )
