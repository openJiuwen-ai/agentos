"""Table lifecycle for thirdparty_agent module."""

import logging

from sqlalchemy import update

from app.models.thirdparty_agent import AgentInstaller, BuildTask
from app.models.base import Base

logger = logging.getLogger(__name__)


async def ensure_thirdparty_agent_tables(engine) -> None:
    """Create thirdparty_agent tables and reset stale build tasks."""
    logger.info("creating tables if not exist")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AgentInstaller.__table__, BuildTask.__table__],
        )

    # Mark any pending/building tasks from a previous run as failed.
    async with engine.begin() as conn:
        result = await conn.execute(
            update(BuildTask)
            .where(BuildTask.status.in_(["pending", "building"]))
            .values(status="failed")
        )
    if result.rowcount:
        logger.info("reset %d stale build tasks to failed", result.rowcount)
