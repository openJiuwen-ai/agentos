"""FastAPI entry point — wires backend, IAM, LiteLLM, and API routes together."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.thirdparty_agent import router as thirdparty_agent_router
from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.litellm_key import router as litellm_key_router
from app.api.v1.litellm_model import router as litellm_router, config_router as mass_config_router
from app.api.v1.litellm_usage import router as litellm_usage_router
from app.api.v1.logs import router as logs_router
from app.api.v1.logs_ws import ws_router as logs_ws_router
from app.api.v1.users import router as users_router
from app.api.v1.hardware import router as hardware_router
from app.core.logging import setup_file_logging
from app.iam.engine import ensure_iam_tables
from app.services import get_user_backend
from app.services.litellm_service import LitellmService
from app.services.log_export import start_log_services, stop_log_services
from app.thirdparty_agent import ensure_thirdparty_agent_tables

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # 0. Set up file logging (deferred from module import — no FS side effects).
    setup_file_logging()

    # 1. Create the shared database engine (single source of truth).
    import app.database as _db

    _db.init_engine()

    # 2. Start the user-system backend (uses the shared engine).
    backend = get_user_backend()
    await backend.on_startup()
    await backend.seed_initial_admin()

    # 3. Create IAM and thirdparty_agent tables on the same engine.
    engine = backend.get_engine()
    if engine is not None:
        await ensure_iam_tables(engine)
        await _create_log_tables(engine)
        await ensure_thirdparty_agent_tables(engine)

    logger.info("backend-api started (backend: %s)", type(backend).__name__)

    # 4. LiteLLM 模型管理服务
    litellm_svc = LitellmService()
    fastapi_app.state.litellm_svc = litellm_svc
    from app.services import register_litellm_svc

    register_litellm_svc(litellm_svc)
    logger.info("LitellmService attached to app.state")

    # 4.5 确保 admin 已同步到 LiteLLM（best-effort，失败不阻断启动）
    await _ensure_admin_in_litellm(backend, litellm_svc)

    # 5. Hardware monitoring service
    from app.services.hardware_service import HardwareService

    hw_svc = HardwareService()
    fastapi_app.state.hardware_svc = hw_svc
    logger.info("HardwareService attached to app.state")

    # 6. 日志中心 — 定时任务 + 导出 Worker
    await start_log_services()

    yield

    # ── 清理 ──────────────────────────────────────────────────────────────
    await hw_svc.close()
    await stop_log_services()
    await litellm_svc.close()
    await backend.on_shutdown()
    await _db.dispose_engine()
    logger.info("backend-api shut down.")


async def _create_log_tables(engine):
    from app.models.base import Base
    from app.models.log import LogComponent, LogExportTask  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _ensure_admin_in_litellm(backend, litellm_svc) -> None:
    """启动时确保 admin 已在 LiteLLM 侧创建（best-effort）。

    - admin 在本地 users 表已存在（seed_initial_admin 保证）
    - 如果 LiteLLM 侧尚未创建，则调 /user/new 同步
    - 已存在（400）或 LiteLLM 不可达均不阻断启动
    """
    from app.config import settings
    from app.services.litellm_service import LitellmUpstreamError, LitellmConnectionError

    try:
        admin = await backend.get_user_by_username(settings.AGENTOS_ADMIN_USERNAME)
        if admin is None:
            logger.warning("Admin user not found in local DB, skip LiteLLM sync")
            return

        try:
            await litellm_svc.create_user(uid=str(admin.user_id))
            logger.info("Admin user synced to LiteLLM (uid=%s)", admin.user_id)
        except LitellmUpstreamError as e:
            if e.status_code == 400:
                logger.info("Admin user already exists in LiteLLM, skip sync")
            else:
                logger.warning("LiteLLM upstream error creating admin user: %s %s", e.status_code, e.detail)
        except LitellmConnectionError:
            logger.warning("LiteLLM unreachable, skip admin user sync")
    except Exception:
        logger.warning("Failed to ensure admin in LiteLLM", exc_info=True)


app = FastAPI(
    title="AgentOS Panel — Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── 注册路由 ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(agent_router)
app.include_router(litellm_router)
app.include_router(mass_config_router)
app.include_router(litellm_key_router)
app.include_router(litellm_usage_router)
app.include_router(hardware_router)
app.include_router(logs_router)
app.include_router(logs_ws_router)
app.include_router(thirdparty_agent_router)


@app.get("/")
async def root():
    return {"service": "AgentOS Panel Backend API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
