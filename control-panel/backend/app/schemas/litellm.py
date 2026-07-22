"""Pydantic 请求/响应模型 — LitellmService（模型管理）"""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


# ─── 统一响应 ─────────────────────────────────────────────────────────────────


class ApiResponse(BaseModel, Generic[T]):
    """统一响应格式"""

    code: int = 200
    message: str = "success"
    data: T | None = None


# ─── 模型管理 ─────────────────────────────────────────────────────────────────


class LitellmParams(BaseModel):
    """LiteLLM 模型参数"""

    model: str = Field(
        ...,
        description="LiteLLM 模型标识，需带 provider 前缀（如 deepseek/deepseek-chat、openai/gpt-4o）",
    )
    api_key: str | None = Field(None, description="API Key")
    api_base: str | None = Field(None, description="API Base URL")

    @field_validator("model")
    @classmethod
    def model_must_have_provider(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError(
                f"model 需要 provider 前缀格式（如 deepseek/{v}、openai/{v}），"
                f"当前值 '{v}' 缺少 '/' 分隔符"
            )
        return v


class ModelInfo(BaseModel):
    """模型信息"""

    description: str | None = Field(None, description="模型描述")
    context_window: int | None = Field(None, description="上下文窗口大小")


class ModelCreate(BaseModel):
    """添加模型请求"""

    model_name: str = Field(
        ...,
        description="模型注册名称",
        examples=["deepseek-chat"],
    )
    litellm_params: LitellmParams = Field(..., description="LiteLLM 模型参数")
    model_info: ModelInfo | None = Field(None, description="模型信息")
    instance_url: str | None = Field(
        None,
        description="推理实例访问 URL",
        examples=["https://example.com:8000/v1"],
    )
    max_concurrent: int | None = Field(
        None,
        ge=1,
        description="最大等待并发数",
    )
    inference_engine: str | None = Field(
        None,
        description="推理引擎名称（仅本地存储，不传给 LiteLLM）",
    )


class ModelUpdate(BaseModel):
    """更新模型请求"""

    model_name: str | None = Field(None, description="模型名称")
    litellm_params: LitellmParams = Field(..., description="LiteLLM 模型参数")
    model_info: ModelInfo | None = Field(None, description="模型信息")
    instance_url: str | None = Field(
        None,
        description="推理实例访问 URL",
    )
    max_concurrent: int | None = Field(
        None,
        ge=1,
        description="最大等待并发数",
    )
    inference_engine: str | None = Field(
        None,
        description="推理引擎名称（仅本地存储，不传给 LiteLLM）",
    )


class ModelItem(BaseModel):
    """模型列表项"""

    id: str
    model_name: str
    litellm_params: dict | None = None
    model_info: dict | None = None
    instance_url: str | None = None
    max_concurrent: int | None = None
    inference_engine: str | None = None
    grafana_job_name: str | None = None
    status: str = "unknown"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedModels(BaseModel):
    """分页模型列表"""

    total: int
    page: int
    page_size: int
    items: list[ModelItem]


class ModelCreated(BaseModel):
    """模型创建结果"""

    id: str
    model_name: str
    instance_url: str | None = None
    max_concurrent: int | None = None
    inference_engine: str | None = None
    grafana_job_name: str | None = None
    created_at: datetime | None = None


class ModelUpdated(BaseModel):
    """模型更新结果"""

    id: str
    model_name: str
    instance_url: str | None = None
    max_concurrent: int | None = None
    inference_engine: str | None = None
    grafana_job_name: str | None = None
    updated_at: datetime | None = None


class OkResult(BaseModel):
    """通用成功结果"""

    ok: bool = True


# ─── Key 管理 ─────────────────────────────────────────────────────────────────


class KeyApplyRequest(BaseModel):
    """申请 Key 请求"""

    model: str | None = Field(None, description="绑定的模型，None=所有模型可用")
    key_name: str | None = Field(None, description="Key 别名（自定义名称）")


class KeyItem(BaseModel):
    """Key 列表项"""

    uid: str = Field(..., description="所属用户 ID")
    key_preview: str = Field(..., description="Key 掩码（前 8 位 + '***'），用于辨识")
    key_alias: str
    key_name: str | None = None
    bound_model: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None


class KeyListResponse(BaseModel):
    """Key 列表响应"""

    keys: list[KeyItem]


class KeyGenerated(BaseModel):
    """Key 生成结果（仅此时返回 Key 原文）"""

    key: str
    key_alias: str
    key_name: str | None = None
    uid: str
    models: list[str] = []
    expires: datetime | None = None


# ─── 使用统计 ─────────────────────────────────────────────────────────────────


class TrendItem(BaseModel):
    """趋势数据点"""

    time: str
    tokens: int = 0
    requests: int = 0
    cost: float = 0.0


class TrendResponse(BaseModel):
    """趋势响应"""

    start_date: str
    end_date: str
    granularity: str
    items: list[TrendItem]


class ModelUsageItem(BaseModel):
    """模型用量项"""

    model: str
    tokens: int = 0
    requests: int = 0
    cost: float = 0.0
    pct: float = 0.0


class ModelUsageResponse(BaseModel):
    """模型用量分布响应"""

    items: list[ModelUsageItem]


class UserUsageItem(BaseModel):
    """用户用量项"""

    user_id: str
    tokens: int = 0
    requests: int = 0
    cost: float = 0.0


class UserUsageRankResponse(BaseModel):
    """用户用量排行响应"""

    items: list[UserUsageItem]


class DailyActivity(BaseModel):
    """每日活动"""

    date: str
    tokens: int = 0
    requests: int = 0
    cost: float = 0.0


class UserUsageDetailResponse(BaseModel):
    """指定用户用量详情"""

    user_id: str
    start_date: str
    end_date: str
    daily_activity: list[DailyActivity]


class OverviewUserItem(BaseModel):
    """总览用户项"""

    user_id: str
    total_tokens: int = 0
    total_requests: int = 0
    total_cost: float = 0.0


class OverviewDailyItem(BaseModel):
    """总览每日项"""

    date: str
    tokens: int = 0
    requests: int = 0
    cost: float = 0.0


class OverviewResponse(BaseModel):
    """全部用户总览"""

    start_date: str
    end_date: str
    users: list[OverviewUserItem]
    daily: list[OverviewDailyItem]
