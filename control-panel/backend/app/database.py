"""SQLAlchemy async engine and session factory.

The module-level ``engine`` and ``async_session_maker`` are set by the
active user-system backend during ``on_startup()``.
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


def _ensure_engine() -> None:
    global engine, async_session_maker
    if engine is None:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
    if async_session_maker is None:
        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    _ensure_engine()
    if async_session_maker is None:
        raise RuntimeError("Database session maker not initialized")
    async with async_session_maker() as session:
        yield session
