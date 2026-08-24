import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

LOG_CATEGORIES = [
    "vllm",
    "control_panel",
    "jiuwenswarm",
    "agent-runtime",
    "agent-gateway",
    "agent-registry",
    "jiuwenbox",
]

CATEGORY_LABELS: dict[str, str] = {
    "vllm": "vLLM",
    "control_panel": "管理面",
    "jiuwenswarm": "jiuwenswarm",
    "agent-runtime": "agent-runtime",
    "agent-gateway": "agent-gateway",
    "agent-registry": "agent-registry",
    "jiuwenbox": "jiuwenbox",
}




class LogComponentCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    log_path: str = Field(..., min_length=1, max_length=512)
    description: str = Field("", max_length=256)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in LOG_CATEGORIES:
            raise ValueError(f"category 必须是以下之一: {', '.join(LOG_CATEGORIES)}")
        return v

    @field_validator("log_path")
    @classmethod
    def validate_log_path(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("log_path 不能包含 '..'")
        if not v.startswith("/"):
            raise ValueError("log_path 必须是绝对路径")
        return v


class LogComponentUpdate(BaseModel):
    category: str | None = Field(None, min_length=1, max_length=32)
    name: str | None = Field(None, min_length=1, max_length=64)
    log_path: str | None = Field(None, max_length=512)
    description: str | None = Field(None, max_length=256)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in LOG_CATEGORIES:
            raise ValueError(f"category 必须是以下之一: {', '.join(LOG_CATEGORIES)}")
        return v

    @field_validator("log_path")
    @classmethod
    def validate_log_path(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if ".." in v:
            raise ValueError("log_path 不能包含 '..'")
        return v


class LogComponentRead(BaseModel):
    id: str
    category: str
    name: str
    log_path: str
    description: str = ""
    size: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class LogCategoryItem(BaseModel):
    key: str
    label: str
    count: int
    component_id: str = ""


class LogExportTaskRead(BaseModel):
    task_id: str
    task_type: str = "export"
    component_id: uuid.UUID | None = None
    component_name: str = ""
    component_category: str = ""
    source_path: str | None = None
    source_name: str | None = None
    query_spec: str | None = None
    line_count: int | None = None
    status: str
    file_path: str | None
    file_size_bytes: int | None
    error_message: str | None
    created_by: uuid.UUID
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
