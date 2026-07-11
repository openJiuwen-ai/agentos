"""Minimal FastAPI entry — demonstrates backend startup with the local-users backend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.core.logging import setup_file_logging
from app.services import get_user_backend

logger = setup_file_logging()


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings.validate_required()
    backend = get_user_backend()
    await backend.on_startup()
    await backend.seed_initial_admin()
    logger.info("backend-api started (backend: %s)", type(backend).__name__)
    yield
    await backend.on_shutdown()
    logger.info("backend-api shut down.")


app = FastAPI(
    title="AgentOS Panel — Backend API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {"service": "AgentOS Panel Backend API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
