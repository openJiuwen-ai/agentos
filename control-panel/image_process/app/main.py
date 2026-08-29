"""image_process FastAPI entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app import tasks
from app.builder import BuildError
from app.factory.models import FactoryError
from app.schemas import (
    BuildCreateRequest,
    BuildCreateResponse,
    BuildStatusResponse,
    ImageRemoveRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("image_process")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ok = await tasks.docker_available()
    logger.info("image_process starting; docker_available=%s", ok)
    yield


app = FastAPI(title="AgentOS image_process", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    ok = await tasks.docker_available()
    if not ok:
        raise HTTPException(
            status_code=503, detail={"message": "docker daemon not available"}
        )
    return {"status": "ok", "docker": True}


@app.post("/v1/builds", response_model=BuildCreateResponse, status_code=202)
async def create_build(body: BuildCreateRequest) -> BuildCreateResponse:
    try:
        rec = await tasks.enqueue_build(body)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)}) from e
    except (BuildError, FactoryError) as e:
        raise HTTPException(status_code=400, detail={"message": str(e)}) from e
    return BuildCreateResponse(request_id=rec.request_id, status="pending")


@app.get("/v1/builds/{request_id}", response_model=BuildStatusResponse)
async def get_build(request_id: str) -> BuildStatusResponse:
    status = tasks.list_task_status(request_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"build task not found: {request_id}"},
        )
    return status


@app.post("/v1/images/remove")
async def remove_image(body: ImageRemoveRequest) -> dict:
    try:
        await tasks.remove_loaded_image(body.tag)
    except FactoryError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)}) from e
    return {"status": "removed", "tag": body.tag}
