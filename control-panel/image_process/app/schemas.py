"""Request / response schemas for image_process API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BuildCreateRequest(BaseModel):
    package_path: str = Field(..., min_length=1, max_length=1024)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)
    options: dict[str, Any] | None = None


class BuildCreateResponse(BaseModel):
    request_id: str
    status: Literal["pending", "building"] = "pending"


class BuildStatusResponse(BaseModel):
    request_id: str
    status: Literal["pending", "building", "done", "failed"]
    progress: int = 0
    name: str | None = None
    version: str | None = None
    image_ref: str | None = None
    archive_path: str | None = None
    runtime_spec: dict | None = None
    recipe_id: str | None = None
    base_ref: str | None = None
    image_digest: str | None = None
    image_module_version: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImageRemoveRequest(BaseModel):
    tag: str = Field(..., min_length=1, max_length=256)
