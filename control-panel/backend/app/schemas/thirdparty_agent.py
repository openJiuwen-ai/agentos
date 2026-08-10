"""Pydantic schemas for Agent Registry API requests and responses."""

from datetime import datetime

from fastapi import Query
from pydantic import BaseModel


class InstallerListItem(BaseModel):
    """Single installer in a list response (GET) or upload result (POST)."""
    agent_name: str
    version: str
    display_name: str
    entrypoint: str


class InstallerListResponse(BaseModel):
    """Paginated list response for GET /installers."""
    items: list[InstallerListItem]
    total: int


class BuildTaskRequest(BaseModel):
    agent_name: str           # locate installer record + final agent name
    version: str              # locate installer record + final version
    display_name: str         # refresh installer display name
    entrypoint: str           # refresh installer entrypoint


class BuildTaskResponse(BaseModel):
    task_id: str
    status: str
    created_at: datetime | None = None


class InstallerListQuery(BaseModel):
    """Query parameters for GET /installers — pagination + framework filter."""

    framework: str = Query("")
    size: int = Query(20)
    page: int = Query(1, ge=1)


class BuildStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    image: str | None = None
    image_digest: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    registered: bool = False
    error_message: str | None = None
