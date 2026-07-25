"""Pydantic schemas for Agent Registry API requests and responses."""

from datetime import datetime

from pydantic import BaseModel


class AgentInstallerUploadResult(BaseModel):
    agent_name: str
    version: str
    display_name: str
    entrypoint: str


class BuildTaskRequest(BaseModel):
    agent_name: str           # locate installer record + final agent name
    version: str              # locate installer record + final version
    display_name: str         # refresh installer display name
    entrypoint: str           # refresh installer entrypoint


class BuildTaskResponse(BaseModel):
    task_id: str
    status: str
    created_at: datetime | None = None


class BuildStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    image: str | None = None
    image_digest: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    registered: bool = False
