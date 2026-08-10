"""Third-party agent table lifecycle."""

import logging

from sqlalchemy import update

from app.models.thirdparty_agent import AgentRegistration, Base, BuildTask

logger = logging.getLogger(__name__)


async def ensure_thirdparty_agent_tables(engine):
    """Create thirdparty agent tables and reset stale tasks on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all,
                            tables=[BuildTask.__table__, AgentRegistration.__table__])

    from app.database import async_session_maker
    async with async_session_maker() as session:
        result = await session.execute(
            update(BuildTask)
            .where(BuildTask.status.in_(["pending", "building"]))
            .values(status="failed", error_message="server restarted"))
        await session.commit()
    if result.rowcount:
        logger.info("reset %d stale build tasks to failed", result.rowcount)
