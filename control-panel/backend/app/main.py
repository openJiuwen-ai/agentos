"""FastAPI entry point — wires backend, IAM, LiteLLM, and API routes together."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.thirdparty_agent import router as thirdparty_agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.litellm_key import router as litellm_key_router
from app.api.v1.litellm_model import router as litellm_router
from app.api.v1.litellm_usage import router as litellm_usage_router
from app.api.v1.users import router as users_router
from app.core.logging import setup_file_logging
from app.iam.engine import ensure_iam_tables
from app.services import get_user_backend
from app.services.litellm_service import LitellmService
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
        await ensure_thirdparty_agent_tables(engine)

    logger.info("backend-api started (backend: %s)", type(backend).__name__)

    # 4. LiteLLM 模型管理服务
    litellm_svc = LitellmService()
    fastapi_app.state.litellm_svc = litellm_svc
    from app.services import register_litellm_svc

    register_litellm_svc(litellm_svc)
    logger.info("LitellmService attached to app.state")

    yield

    # ── 清理 ──────────────────────────────────────────────────────────────
    await litellm_svc.close()
    await backend.on_shutdown()
    await _db.dispose_engine()
    logger.info("backend-api shut down.")


app = FastAPI(
    title="AgentOS Panel — Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── 注册路由 ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(litellm_router)
app.include_router(litellm_key_router)
app.include_router(litellm_usage_router)
app.include_router(thirdparty_agent_router)


@app.get("/")
async def root():
    return {"service": "AgentOS Panel Backend API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
