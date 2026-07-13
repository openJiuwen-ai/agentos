"""FastAPI entry point — wires backend, IAM, and API routes together."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.config import settings
from app.core.logging import setup_file_logging
from app.iam.engine import ensure_iam_tables
from app.services import get_user_backend

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

    # 3. Create IAM tables on the same engine.
    engine = backend.get_engine()
    if engine is not None:
        await ensure_iam_tables(engine)

    logger.info("backend-api started (backend: %s)", type(backend).__name__)
    yield
    await backend.on_shutdown()
    logger.info("backend-api shut down.")


app = FastAPI(
    title="AgentOS Panel — Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(users_router)


@app.get("/")
async def root():
    return {"service": "AgentOS Panel Backend API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
