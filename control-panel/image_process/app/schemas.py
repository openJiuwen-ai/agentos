"""Request / response schemas for image_process API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BuildCreateRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)
    agent_name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=64)
    installer_path: str = Field(..., min_length=1, max_length=1024)
    output_dir: str = Field(..., min_length=1, max_length=1024)
    work_dir: str | None = Field(default=None, max_length=1024)


class BuildCreateResponse(BaseModel):
    task_id: str
    status: Literal["pending", "building"] = "pending"


class BuildStatusResponse(BaseModel):
    task_id: str
    status: Literal["pending", "building", "done", "failed"]
    progress: int = 0
    image: str | None = None
    image_digest: str | None = None
    image_path: str | None = None
    base_image: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
