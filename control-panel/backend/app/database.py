"""SQLAlchemy async engine and session factory — single source of truth.

The app creates the engine once at startup via ``init_engine()``.
All modules (backend, IAM, etc.) reuse it via ``get_async_session()``.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine: AsyncEngine | None = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the async engine and session factory.  Called once at startup."""
    global engine, async_session_maker
    settings.validate_required()
    url = database_url or settings.AGENTOS_DATABASE_URL
    engine = create_async_engine(url, echo=False)
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session from the shared engine."""
    if async_session_maker is None:
        raise RuntimeError(
            "database.init_engine() must be called before get_async_session()"
        )
    async with async_session_maker() as session:
        yield session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — same as ``get_async_session`` but auto-commits on success.

    On normal exit the session is committed; on exception it is rolled back.
    Suitable for litellm CRUD routes.
    """
    async for session in get_async_session():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the shared async engine.  Call during application shutdown."""
    global engine, async_session_maker
    if engine is not None:
        await engine.dispose()
        engine = None
        async_session_maker = None
