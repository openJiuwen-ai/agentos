"""Third-party agent table lifecycle."""

from app.models.thirdparty_agent import AgentRegistration, Base, BuildTask


async def ensure_thirdparty_agent_tables(engine):
    """Create the existing third-party agent tables without altering their schema."""
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BuildTask.__table__, AgentRegistration.__table__],
        )
