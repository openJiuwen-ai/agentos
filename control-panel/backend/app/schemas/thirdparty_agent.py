"""Pydantic schemas for third-party agent cards."""

from fastapi import Query
from pydantic import BaseModel, Field


class PublishAccepted(BaseModel):
    digest: str
    request_id: str


class CardItem(BaseModel):
    framework: str
    framework_version: str
    is_default: bool = False
    total_instances: int | None = None
    running_instances: int | None = None


class CardDetail(CardItem):
    package_path: str | None = None


class CardListResponse(BaseModel):
    items: list[dict]
    total: int


class CardListQuery(BaseModel):
    framework: str = Query("")
    size: int = Query(20)
    page: int = Query(1, ge=1)


class SetDefaultRequest(BaseModel):
    framework_version: str = Field(..., min_length=1, max_length=128)


class UnregisteredItem(BaseModel):
    digest: str
    original_filename: str
    package_path: str
    locked: bool
    last_error: str | None = None
    request_id: str | None = None


class UnregisteredListResponse(BaseModel):
    items: list[UnregisteredItem]


class UnregisteredStatus(UnregisteredItem):
    status: str = "idle"
    progress: int = 0
