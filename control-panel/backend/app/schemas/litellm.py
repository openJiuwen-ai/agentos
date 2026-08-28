"""Pydantic 请求/响应模型 — LitellmService（模型管理）"""

from datetime import date, datetime
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
    allowed_openai_params: list[str] = Field(
        default_factory=lambda: ["reasoning_effort", "tools", "thinking"],
        description="允许透传给上游的 OpenAI 参数（如 reasoning_effort、tools、thinking），默认允许 reasoning_effort、tools、thinking",
    )

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
    context_window: int | None = Field(
        None,
        description="上下文窗口大小",
        ge=1,
        le=2147483647,
    )


class MetricsEndpoint(BaseModel):
    """模型监控抓取点：部署框架 + 监控 URL（可多条，支持双机）。"""

    inference_engine: str = Field(
        ...,
        min_length=1,
        description="部署框架（如 vLLM / SGLang）",
        examples=["vLLM"],
    )
    instance_url: str = Field(
        ...,
        min_length=1,
        description="推理引擎监控地址（含端口），用于 /metrics 抓取",
        examples=["http://192.168.1.10:8000"],
    )
    grafana_job_name: str | None = Field(
        None,
        description="VictoriaMetrics/Grafana job 名（后端生成，只读）",
    )


class ModelCreate(BaseModel):
    """添加模型请求"""

    model_name: str = Field(
        ...,
        description="模型注册名称",
        examples=["deepseek-chat"],
    )
    litellm_params: LitellmParams = Field(..., description="LiteLLM 模型参数")
    model_info: ModelInfo | None = Field(None, description="模型信息")
    metrics_endpoints: list[MetricsEndpoint] = Field(
        default_factory=list,
        description="监控抓取点列表（可空；双机可填多条，允许不同部署框架）",
    )
    max_concurrent: int | None = Field(
        None,
        ge=1,
        description="最大等待并发数",
    )


class ModelUpdate(BaseModel):
    """更新模型请求"""

    model_name: str | None = Field(None, description="模型名称")
    litellm_params: LitellmParams = Field(..., description="LiteLLM 模型参数")
    model_info: ModelInfo | None = Field(None, description="模型信息")
    metrics_endpoints: list[MetricsEndpoint] | None = Field(
        None,
        description="监控抓取点列表；传 [] 清空；省略则不改",
    )
    max_concurrent: int | None = Field(
        None,
        ge=1,
        description="最大等待并发数",
    )


class ModelItem(BaseModel):
    """模型列表项"""

    id: str
    model_name: str
    litellm_params: dict | None = None
    model_info: dict | None = None
    metrics_endpoints: list[MetricsEndpoint] = Field(default_factory=list)
    max_concurrent: int | None = None
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
    metrics_endpoints: list[MetricsEndpoint] = Field(default_factory=list)
    max_concurrent: int | None = None
    created_at: datetime | None = None


class ModelUpdated(BaseModel):
    """模型更新结果"""

    id: str
    model_name: str
    metrics_endpoints: list[MetricsEndpoint] = Field(default_factory=list)
    max_concurrent: int | None = None
    updated_at: datetime | None = None


class OkResult(BaseModel):
    """通用成功结果"""

    ok: bool = True


# ─── Key 管理 ─────────────────────────────────────────────────────────────────


class KeyApplyRequest(BaseModel):
    """申请 Key 请求"""

    model: str | None = Field(None, description="绑定的模型，None=所有模型可用")
    key_name: str | None = Field(
        None,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Key 名称（可选，仅允许字母/数字/下划线/连字符）",
    )


class KeyItem(BaseModel):
    """Key 列表项"""

    uid: str = Field(..., description="所属用户 ID")
    key_preview: str = Field(..., description="Key 掩码（前 8 位 + '***'），用于辨识")
    key_alias: str
    key_name: str | None = None
    is_default: bool = False
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

    start_date: date
    end_date: date
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
    username: str | None = None
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
    start_date: date
    end_date: date
    daily_activity: list[DailyActivity]
    success_rate: float = 0.0


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
    active_users: int = 0


class ModelTrendItem(BaseModel):
    """模型趋势项（按天+模型）"""

    date: str
    model: str
    tokens: int = 0
    requests: int = 0
    cost: float = 0.0


class ModelTrendResponse(BaseModel):
    """模型趋势响应"""

    start_date: date
    end_date: date
    items: list[ModelTrendItem]


class OverviewResponse(BaseModel):
    """全部用户总览"""

    start_date: date
    end_date: date
    users: list[OverviewUserItem]
    daily: list[OverviewDailyItem]
    success_rate: float = 0.0
