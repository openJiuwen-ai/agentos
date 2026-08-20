"""LitellmService 模型管理测试 fixtures — 纯 UT，默认 SQLite，可通过 TEST_DB_URL 切 PostgreSQL"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import StaticPool, NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker,
)

# ── 注册模型 ──────────────────────────────────────────────────────────────
import app.models.litellm_model_params   # noqa: F401
import app.models.litellm_user_key       # noqa: F401
import app.models.user_default_key       # noqa: F401
from app.models.base import Base

# ── 测试专用配置覆盖（避免 encrypt_key 因密钥为空报错） ───────────────
# litellm 子目录使用独立引擎/fixture，不经过根 conftest 的 _configure_for_test，
# 需在此显式设置，否则 settings.LITELLM_KEY_ENCRYPTION_KEY 为空，
# encrypt_key() 会抛 ValueError: must decode to 32 bytes, got 0 bytes
from app.config import settings
settings.LITELLM_KEY_ENCRYPTION_KEY = "0" * 64   # 256-bit 全零密钥，仅测试用
settings.LITELLM_ADMIN_URL = "http://localhost:4000"
settings.LITELLM_MASTER_KEY = "test-master-key"
settings.LITELLM_DATABASE_URL = "sqlite+aiosqlite://"

# ── 数据库引擎（TEST_DB_URL 环境变量切换 PostgreSQL，默认 SQLite 内存）─────
_TEST_DB_URL = os.getenv("TEST_DB_URL", "sqlite+aiosqlite://")

if "postgresql" in _TEST_DB_URL or "asyncpg" in _TEST_DB_URL:
    _engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
else:
    _engine = create_async_engine(
        _TEST_DB_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
_session_maker = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """session 级别：建一次表，StaticPool 保证所有操作共享同一连接"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── 注册路由 + 挂载 svc ──────────────────────────────────────────────────
# 注意: app.main 已注册 litellm router 并在 lifespan 中创建 LitellmService,
# 这里仅确保 app.state.litellm_svc 在测试环境中可用 (无需触发 lifespan).
from app.main import app
from app.services.litellm_service import LitellmService

# 避免重复注册: main.py 已在模块级 app.include_router(litellm_router)
# 仅当 state 上尚无 svc 时才挂载 (不覆盖 lifespan 创建的实例)
if not hasattr(app.state, "litellm_svc") or app.state.litellm_svc is None:
    app.state.litellm_svc = LitellmService()


# ── 覆盖 get_session → 测试引擎 ──────────────────────────────────────────
async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


from app.database import get_session as _orig_get_session
from app.iam.deps import get_current_user as _orig_get_current_user
from app.iam.deps import require_admin as _orig_require_admin
from app.iam.deps import require_permission as _orig_require_permission


async def _override_get_current_user():
    from app.iam.tokens import TokenData
    return TokenData(user_id="test-user-001", username="test-user", role="user")


async def _override_require_admin():
    from app.iam.tokens import TokenData
    return TokenData(user_id="test-admin-001", username="test-admin", role="admin")


async def _override_require_permission():
    from app.iam.tokens import TokenData
    return TokenData(user_id="test-user-001", username="test-user", role="user")


def _apply_litellm_overrides():
    """Apply dependency overrides for litellm tests."""
    _app = app
    _app.dependency_overrides[_orig_get_session] = _override_get_session
    _app.dependency_overrides[_orig_get_current_user] = _override_get_current_user
    _app.dependency_overrides[_orig_require_admin] = _override_require_admin
    _app.dependency_overrides[_orig_require_permission] = _override_require_permission


def _remove_litellm_overrides():
    """Remove litellm dependency overrides from the global app."""
    _app = app
    for _key in (
        _orig_get_session,
        _orig_get_current_user,
        _orig_require_admin,
        _orig_require_permission,
    ):
        _app.dependency_overrides.pop(_key, None)


@pytest.fixture(scope="package", autouse=True)
def _litellm_overrides():
    """Apply overrides for litellm tests, restore on teardown."""
    _apply_litellm_overrides()
    yield
    _remove_litellm_overrides()


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def db_session():
    """每个测试后清空 litellm 表"""
    async with _session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
        finally:
            await session.close()
    from sqlalchemy import text as _t

    async with _engine.connect() as c:
        await c.execute(_t("DELETE FROM litellm_user_key"))
        await c.execute(_t("DELETE FROM litellm_model_params"))
        await c.commit()
