"""LitellmService — LiteLLM 模型管理核心类

职责：LiteLLM HTTP 调用 + 本地 DB 读写 + 业务编排。
路由层仅做参数提取 + 调用 Service 方法。
"""

import asyncio
import os
import uuid
import base64

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from app.config import settings
from app.models.litellm_model_params import LitellmModelParams, LocalModelExtension
from app.services import agent_metrics_config
from app.models.litellm_user_key import LitellmUserKey, CreateKeyExtras

logger = logging.getLogger(__name__)

METRICS_JOB_KEY = "grafana_job_name"

# ── LiteLLM 系统内部 key 名（写死在 LiteLLM 源码中，用于从统计中过滤系统流量）──
# 这些 key 不是真实用户生成的，LiteLLM 用它们发起内部请求，若混入用量统计会虚增数据：
# - _SYSTEM_API_KEY_HEALTH_CHECK: LiteLLM 对模型发心跳探活请求时使用的 key
# - _SYSTEM_API_KEY_MASTER:      管理员 master key 发起的请求（如管理面初始化时的探测）
# - _SYSTEM_API_KEY_NONE:        某些异常/无 key 的请求，LiteLLM 会记成字符串 "None"
_SYSTEM_API_KEY_HEALTH_CHECK = "litellm-internal-health-check"
_SYSTEM_API_KEY_MASTER = "litellm_proxy_master_key"
_SYSTEM_API_KEY_NONE = "None"


# ─── 辅助 dataclass ──────────────────────────────────────────────────────────────


@dataclass
class CreateModelExtras:
    """收敛 create_model 的可选参数（满足参数个数限制）。"""

    model_info: dict | None = None
    metrics_endpoints: list[dict] | None = None
    max_concurrent: int | None = None


@dataclass
class UpdateModelExtras:
    """收敛 update_model 的可选参数（满足参数个数限制）。"""

    model_info: dict | None = None
    metrics_endpoints: list[dict] | None = None
    max_concurrent: int | None = None


@dataclass
class CreateUserExtras:
    """收敛 create_user 的可选参数（满足参数个数限制）。"""

    auto_create_key: bool = False
    rpm_limit: int | None = None
    max_parallel_requests: int | None = None
    tpm_limit: int | None = None


# ─── 异常类 ────────────────────────────────────────────────────────────────────


class LitellmServiceError(Exception):
    """LitellmService 基础异常"""


class LitellmConnectionError(LitellmServiceError):
    """网络不通/超时"""


class LitellmUpstreamError(LitellmServiceError):
    """LiteLLM 返回非 2xx"""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"LiteLLM upstream error {status_code}: {detail}")


class MaxKeysReachedError(LitellmServiceError):
    """Key 数量已达上限"""


class KeyNotFoundError(LitellmServiceError):
    """Key 不存在或不属于当前用户"""


# ─── LiteLLM 状态码语义 ────────────────────────────────────────────
# 创建类接口：目标已存在。LiteLLM 实测返回 409，保留 400 兼容旧版本。
USER_ALREADY_EXISTS_STATUS_CODES = (400, 409)
# 删除类接口：目标不存在 → 幂等成功。
RESOURCE_NOT_FOUND_STATUS_CODE = 404
# 模型删除：已删除/不存在的模型可能返回 404 或 400，均视为幂等成功。
MODEL_DELETE_IDEMPOTENT_STATUS_CODES = (RESOURCE_NOT_FOUND_STATUS_CODE, 400)
# 上游响应无内容（空 body）时的状态码。
NO_CONTENT_STATUS_CODE = 204
# 上游返回错误响应的状态码阈值（>= 该值视为错误）。
ERROR_RESPONSE_STATUS_THRESHOLD = 400


# ─── Key 加密工具 ──────────────────────────────────────────────────────────────


def _get_aesgcm() -> AESGCM:
    """Return an AESGCM instance for authenticated encryption.

    AES-256-GCM provides authenticated encryption with associated data (AEAD).
    Suitable for encrypting API keys at rest in the database.
    The encryption key is sourced from ``LITELLM_KEY_ENCRYPTION_KEY``
    (environment variable), 256-bit hex-encoded, never hard-coded.

    Raises ValueError if the key is not exactly 64 hex characters (32 bytes).
    """
    key = settings.LITELLM_KEY_ENCRYPTION_KEY
    try:
        key_bytes = bytes.fromhex(key)
    except ValueError:
        raise ValueError(
            "LITELLM_KEY_ENCRYPTION_KEY must be a hex-encoded 256-bit key "
            "(64 hex characters). Generate with: openssl rand -hex 32"
        ) from None
    if len(key_bytes) != 32:
        raise ValueError(
            f"LITELLM_KEY_ENCRYPTION_KEY must decode to 32 bytes (256 bits), "
            f"got {len(key_bytes)} bytes"
        )
    return AESGCM(key_bytes)


def encrypt_key(plain_key: str) -> str:
    """Encrypt using AES-256-GCM with a random 96-bit nonce.

    Returns ``base64(nonce):base64(ciphertext)`` — safe to store as a string.
    Nonce is randomly generated per encryption, so encrypting the same
    plaintext twice produces different ciphertexts.
    """
    aesgcm = _get_aesgcm()
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plain_key.encode(), None)
    return (
        base64.urlsafe_b64encode(nonce).decode()
        + ":"
        + base64.urlsafe_b64encode(ct).decode()
    )


def decrypt_key(encrypted_key: str) -> str:
    """Decrypt a value produced by :func:`encrypt_key`."""
    aesgcm = _get_aesgcm()
    nonce_b64, ct_b64 = encrypted_key.split(":", 1)
    nonce = base64.urlsafe_b64decode(nonce_b64)
    ct = base64.urlsafe_b64decode(ct_b64)
    return aesgcm.decrypt(nonce, ct, None).decode()


def _mask_key(key: str, show: int = 8) -> str:
    if len(key) <= show:
        return key
    return key[:show] + "***"


# ─── 辅助函数 ────────────────────────────────────────────────────────────────────


async def _build_health_map(svc: "LitellmService") -> dict[str, str]:
    """调用 LiteLLM /health，构建 litellm_params.model|api_base -> status 的映射。"""
    try:
        data = await svc.request("GET", "/health")
    except (LitellmConnectionError, LitellmUpstreamError):
        return {}

    if not isinstance(data, dict):
        return {}

    result: dict[str, str] = {}
    for ep in data.get("healthy_endpoints") or []:
        key = f"{ep.get('model', '')}|{ep.get('api_base', '')}"
        result[key] = "healthy"
    for ep in data.get("unhealthy_endpoints") or []:
        key = f"{ep.get('model', '')}|{ep.get('api_base', '')}"
        result[key] = "unhealthy"
    return result


def _fetch_model_detail(
    svc: "LitellmService",
    m: dict,
    local: "LitellmModelParams | None",
    health_map: dict[str, str] | None = None,
) -> dict | None:
    """合并 LiteLLM 模型信息与本地扩展字段。"""
    model_id = m.get("model_name", "") or m.get("id", "")
    if not model_id:
        return None

    # 通过 litellm_params.model + api_base 匹配健康状态
    status = "unknown"
    if health_map is not None:
        llm_model = (m.get("litellm_params") or {}).get("model") or ""
        api_base = (m.get("litellm_params") or {}).get("api_base") or ""
        key = f"{llm_model}|{api_base}"
        status = health_map.get(key, "unknown")

    return {
        "id": m.get("model_info", {}).get("id") or model_id,
        "model_name": local.model_name if local else model_id,
        "litellm_params": m.get("litellm_params"),
        "model_info": m.get("model_info"),
        "metrics_endpoints": _endpoints_from_local(local),
        "max_concurrent": local.max_concurrent if local else None,
        "status": status,
        "created_at": local.created_at if local else None,
        "updated_at": local.updated_at if local else None,
    }


def _endpoints_from_local(local: LitellmModelParams | None) -> list[dict]:
    if not local or not local.metrics_endpoints:
        return []
    if not isinstance(local.metrics_endpoints, list):
        return []
    return [ep for ep in local.metrics_endpoints if isinstance(ep, dict)]


def _normalize_endpoint_input(raw: list[dict] | None) -> list[dict]:
    """校验并规范化前端传入的 endpoints（不含 grafana_job_name）。"""
    if not raw:
        return []
    cleaned: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise LitellmServiceError("metrics_endpoints 元素必须是对象")
        engine = str(item.get("inference_engine") or "").strip()
        url = str(item.get("instance_url") or "").strip()
        if not engine:
            raise LitellmServiceError("metrics_endpoints 缺少 inference_engine（部署框架）")
        if not url:
            raise LitellmServiceError("metrics_endpoints 缺少 instance_url（模型监控 URL）")
        try:
            target = agent_metrics_config.normalize_target(url)
            job = agent_metrics_config.build_job(engine, target)
        except agent_metrics_config.AgentMetricsConfigError as e:
            raise LitellmServiceError(str(e)) from e
        if job in seen:
            continue
        seen.add(job)
        cleaned.append({
            "inference_engine": engine,
            "instance_url": url,
        })
    return cleaned


def _jobs_from_endpoints(endpoints: list[dict] | None) -> set[str]:
    jobs: set[str] = set()
    for ep in endpoints or []:
        job = ep.get("grafana_job_name")
        if job is not None and str(job).strip():
            jobs.add(str(job).strip())
    return jobs


@dataclass(frozen=True)
class _MetricsJobCleanup:
    """收敛 scrape job 清理参数（满足 G.FNM.03 参数个数限制）。"""

    model_name: str
    job: str
    instance_url: str | None = None
    inference_engine: str | None = None
    exclude_id: str | None = None


async def _remove_job_if_unreferenced(
    db: AsyncSession,
    cleanup: _MetricsJobCleanup,
) -> bool:
    """若 job 无其他模型引用则删除 scrape 条目。返回是否清理失败。"""
    count = await LitellmModelParams.count_by_grafana_job(
        db, cleanup.job, exclude_id=cleanup.exclude_id,
    )
    if count > 0:
        logger.info(
            "job '%s' 仍被其他模型引用，跳过 agent-metrics 清理 (model='%s')",
            cleanup.job, cleanup.model_name,
        )
        return False
    try:
        await asyncio.to_thread(
            agent_metrics_config.remove_entry,
            cleanup.job,
            cleanup.instance_url,
            cleanup.inference_engine,
        )
    except (agent_metrics_config.AgentMetricsConfigError, OSError) as e:
        logger.warning(
            "Failed to clean agent-metrics.json for model '%s' job '%s': %s. "
            "Manual cleanup may be required.",
            cleanup.model_name, cleanup.job, e,
        )
        return True
    return False


async def _sync_metrics_endpoints(
    db: AsyncSession,
    model_name: str,
    local: LitellmModelParams | None,
    desired_raw: list[dict] | None,
    *,
    replace: bool,
) -> list[dict] | None:
    """同步 metrics_endpoints 到 agent-metrics.json，返回带 grafana_job_name 的列表。

    replace=False 且 desired_raw is None：不改动（返回 None）。
    replace=True：按 desired 全量替换（含空列表）。
    """
    if not replace:
        return None

    desired = _normalize_endpoint_input(desired_raw)
    old_endpoints = _endpoints_from_local(local)
    old_jobs = _jobs_from_endpoints(old_endpoints)

    synced: list[dict] = []
    new_jobs: set[str] = set()
    try:
        for ep in desired:
            job = await asyncio.to_thread(
                agent_metrics_config.add_entry,
                ep["inference_engine"],
                ep["instance_url"],
            )
            new_jobs.add(job)
            synced.append({
                "inference_engine": ep["inference_engine"],
                "instance_url": ep["instance_url"],
                "grafana_job_name": job,
            })
    except agent_metrics_config.AgentMetricsConfigError as e:
        logger.exception(
            "Failed to update agent-metrics.json for model '%s'",
            model_name,
        )
        raise LitellmServiceError(str(e)) from e

    obsolete = old_jobs - new_jobs
    for job in obsolete:
        old_ep = next(
            (e for e in old_endpoints if e.get("grafana_job_name") == job),
            {},
        )
        await _remove_job_if_unreferenced(
            db,
            _MetricsJobCleanup(
                model_name=model_name,
                job=job,
                instance_url=old_ep.get("instance_url"),
                inference_engine=old_ep.get("inference_engine"),
                exclude_id=local.id if local else None,
            ),
        )

    return synced


async def _sync_metrics_on_delete(
    db: AsyncSession,
    model_name: str,
    local: LitellmModelParams | None,
    model_id: str,
) -> bool:
    """删除模型时清理所有 agent-metrics 抓取条目。

    - job 被其他模型共用时跳过清理，避免误删
    - 清理失败降级为 warning，不阻断删除
    返回 True 表示有清理失败（需人工介入）。
    """
    if not local:
        return False
    endpoints = _endpoints_from_local(local)
    if not endpoints:
        return False
    failed = False
    for ep in endpoints:
        job = ep.get("grafana_job_name")
        if not job:
            continue
        if await _remove_job_if_unreferenced(
            db,
            _MetricsJobCleanup(
                model_name=model_name,
                job=str(job),
                instance_url=ep.get("instance_url"),
                inference_engine=ep.get("inference_engine"),
                exclude_id=model_id,
            ),
        ):
            failed = True
    return failed


def _merge_extra_params(
    local: LitellmModelParams | None,
    model_info: dict | None,
) -> dict | None:
    merged = dict(local.extra_params) if local and local.extra_params else {}
    if model_info is not None:
        merged["model_info"] = model_info
    return merged or None


# ─── LitellmService ────────────────────────────────────────────────────────────


class LitellmService:
    """LiteLLM 模型管理服务。

    依赖 httpx.AsyncClient → LiteLLM Admin API
         AsyncSession → 本地 PostgreSQL

    用法:
        svc = LitellmService()
        models = await svc.list_models(db, page=1, page_size=20)
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._litellm_engine = None
        self._litellm_sessionmaker = None

    @property
    def client(self) -> httpx.AsyncClient:
        """延迟初始化 httpx AsyncClient（单例复用）。

        强制 IPv4: Windows 上 httpx 解析 localhost 优先尝试 ::1 (IPv6)，
        LiteLLM 默认只监听 0.0.0.0 (IPv4)，导致连接超时。
        """
        if self._client is None:
            base = settings.LITELLM_ADMIN_URL.replace("localhost", "127.0.0.1")
            self._client = httpx.AsyncClient(
                base_url=base,
                headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}"},
                timeout=settings.LITELLM_REQUEST_TIMEOUT,
            )
        return self._client

    async def close(self):
        """关闭 httpx 客户端 + LiteLLM DB 引擎"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._litellm_engine is not None:
            await self._litellm_engine.dispose()
            self._litellm_engine = None
            self._litellm_sessionmaker = None

    # ─── request：封装 httpx 调用 ───────────────────────────────────────────────

    async def request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> dict | list[dict]:
        """封装 httpx 调用，处理鉴权、超时、异常映射。"""
        url = path  # httpx 会基于 base_url 拼接
        try:
            response = await self.client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
            )
        except httpx.TimeoutException as e:
            raise LitellmConnectionError(f"Timeout connecting to LiteLLM: {e}") from e
        except httpx.ConnectError as e:
            raise LitellmConnectionError(f"Cannot connect to LiteLLM: {e}") from e
        except httpx.NetworkError as e:
            raise LitellmConnectionError(f"Network error: {e}") from e

        if response.status_code == NO_CONTENT_STATUS_CODE or not response.content:
            return {}

        try:
            data = response.json()
        except Exception as e:
            text_content = response.text[:500]
            raise LitellmUpstreamError(
                status_code=response.status_code,
                detail=f"Non-JSON response: {text_content}",
            ) from e

        if response.status_code >= ERROR_RESPONSE_STATUS_THRESHOLD:
            detail = ""
            if isinstance(data, dict):
                detail = data.get("error", data.get("detail", str(data)[:500]))
            raise LitellmUpstreamError(
                status_code=response.status_code,
                detail=str(detail),
            )

        return data

    # ═══════════════════════════════════════════════════════════════════════════
    # 模型管理
    # ═══════════════════════════════════════════════════════════════════════════

    async def list_models(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        model_name: str | None = None,
    ) -> dict:
        """获取模型列表，合并 LiteLLM + 本地扩展字段，内存分页。

        model_name: 可选名称过滤，返回所有匹配项。
        """
        llm_data = await self.request("GET", "/model/info")
        llm_models: list[dict] = []
        if isinstance(llm_data, dict) and "data" in llm_data:
            llm_models = llm_data["data"]
        elif isinstance(llm_data, list):
            llm_models = llm_data

        # 名称过滤（模糊匹配，供 keyword / model_name 搜索）
        if model_name:
            keyword = model_name.lower()
            llm_models = [
                m for m in llm_models
                if keyword in (m.get("model_name") or "").lower()
            ]

        llm_names = [m.get("model_name") for m in llm_models if m.get("model_name")]

        # 构建本地记录查找表: 以 model_name 为 key，同时兜底按本地 id 匹配
        local_by_name: dict[str, LitellmModelParams] = {}
        if llm_names:
            from sqlalchemy import select as sa_select

            # 按 model_name 匹配
            name_result = await db.execute(
                sa_select(LitellmModelParams).where(
                    LitellmModelParams.model_name.in_(llm_names),
                )
            )
            for row in name_result.scalars().all():
                local_by_name[row.model_name] = row

        # 健康状态由独立接口 /model/health 按需刷新，避免 list_models 被 /health 阻塞
        tasks = [
            _fetch_model_detail(self, m, local_by_name.get(m.get("model_name")))
            for m in llm_models
        ]
        merged = [r for r in tasks if r is not None]

        total = len(merged)
        start = (page - 1) * page_size
        end = start + page_size
        items = merged[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    async def get_models_health(self) -> dict[str, str]:
        """获取所有模型的健康状态映射 {model_id: status}。

        供前端列表渲染后异步刷新，避免 list_models 被 /health 阻塞。
        """
        llm_data = await self.request("GET", "/model/info")
        llm_models: list[dict] = []
        if isinstance(llm_data, dict) and "data" in llm_data:
            llm_models = llm_data["data"]
        elif isinstance(llm_data, list):
            llm_models = llm_data

        health_map = await _build_health_map(self)

        result: dict[str, str] = {}
        for m in llm_models:
            model_id = m.get("model_info", {}).get("id") or m.get("model_name")
            if not model_id:
                continue
            llm_model = (m.get("litellm_params") or {}).get("model") or ""
            api_base = (m.get("litellm_params") or {}).get("api_base") or ""
            key = f"{llm_model}|{api_base}"
            result[model_id] = health_map.get(key, "unknown")
        return result

    @staticmethod
    def _model_matches(m: dict, model_id: str) -> bool:
        """检查模型数据是否匹配给定的 model_id。"""
        return (
            m.get("model_info", {}).get("id") == model_id
            or m.get("model_name") == model_id
        )

    async def get_model(
        self,
        db: AsyncSession,
        model_id: str,
    ) -> dict | None:
        """获取单个模型详情，合并 LiteLLM + 本地扩展字段，不存在返回 None。"""
        llm_data = await self.request(
            "GET",
            "/model/info",
            params={"litellm_model_id": model_id},
        )
        llm_models: list[dict] = []
        if isinstance(llm_data, dict) and "data" in llm_data:
            llm_models = llm_data["data"]
        elif isinstance(llm_data, list):
            llm_models = llm_data

        target = None
        for m in llm_models:
            if self._model_matches(m, model_id):
                target = m
                break
        if not target:
            return None

        local = await LitellmModelParams.get_by_id(db, model_id)
        return _fetch_model_detail(self, target, local)

    async def create_model(
        self,
        db: AsyncSession,
        model_name: str,
        litellm_params: dict,
        extras: CreateModelExtras | None = None,
    ) -> dict:
        """添加模型。

        1. POST /model/new → LiteLLM
        2. INSERT litellm_model_params → 本地
        3. DB 失败 → POST /model/delete 回滚 LiteLLM
        """
        extras = extras or CreateModelExtras()
        body: dict[str, Any] = {
            "model_name": model_name,
            "litellm_params": litellm_params,
        }
        if extras.model_info:
            body["model_info"] = extras.model_info

        llm_result = await self.request("POST", "/model/new", json_data=body)

        model_id: str | None = None
        if isinstance(llm_result, dict):
            model_id = (
                llm_result.get("model_id") or llm_result.get("model_uuid") or None
            )
            if not model_id:
                model_info_resp = llm_result.get("model_info", {})
                if isinstance(model_info_resp, dict):
                    model_id = model_info_resp.get("id") or None

        if not model_id:
            logger.error(
                "Cannot extract model_id from LiteLLM response for '%s'. "
                "Raw response: %s",
                model_name,
                str(llm_result)[:500],
            )
            try:
                await self.request(
                    "POST",
                    "/model/delete",
                    json_data={"id": model_name},
                )
            except Exception:
                logger.error(
                    "CRITICAL: Failed to rollback LiteLLM model '%s' "
                    "after ID extraction failure. "
                    "MANUAL CLEANUP REQUIRED: delete model '%s' "
                    "from LiteLLM admin.",
                    model_name,
                    model_name,
                )
            raise LitellmServiceError(
                f"Failed to extract model_id from LiteLLM response for "
                f"'{model_name}'. The model has been rolled back."
            )

        metrics_endpoints: list[dict] | None = None
        try:
            metrics_endpoints = await _sync_metrics_endpoints(
                db,
                model_name,
                None,
                extras.metrics_endpoints or [],
                replace=True,
            )
            extra_params = _merge_extra_params(None, extras.model_info)
            row = await LitellmModelParams.upsert(
                db,
                model_id,
                model_name,
                LocalModelExtension(
                    metrics_endpoints=metrics_endpoints if metrics_endpoints is not None else [],
                    max_concurrent=extras.max_concurrent,
                    extra_params=extra_params,
                ),
            )
        except Exception:
            if metrics_endpoints:
                for ep in metrics_endpoints:
                    job = ep.get("grafana_job_name")
                    if not job:
                        continue
                    try:
                        count = await LitellmModelParams.count_by_grafana_job(db, job)
                    except Exception:
                        count = 0
                    if count == 0:
                        try:
                            await asyncio.to_thread(
                                agent_metrics_config.remove_entry,
                                job,
                                ep.get("instance_url"),
                                ep.get("inference_engine"),
                            )
                        except Exception:
                            logger.error(
                                "Failed to rollback agent-metrics.json for model '%s'",
                                model_name,
                            )
            try:
                await self.request(
                    "POST",
                    "/model/delete",
                    json_data={"id": model_id},
                )
            except Exception:
                logger.error(
                    "CRITICAL: Failed to rollback LiteLLM model '%s' "
                    "(id=%s). MANUAL CLEANUP REQUIRED.",
                    model_name,
                    model_id,
                )
            raise

        return {
            "id": model_id,
            "model_name": model_name,
            "metrics_endpoints": metrics_endpoints or [],
            "max_concurrent": extras.max_concurrent,
            "created_at": row.created_at,
        }

    async def update_model(
        self,
        db: AsyncSession,
        model_id: str,
        litellm_params: dict,
        model_name: str | None = None,
        extras: UpdateModelExtras | None = None,
    ) -> dict:
        """更新模型。

        1. 按 ID 查本地 DB 获取记录 → POST /model/update → LiteLLM
        2. UPSERT litellm_model_params → 本地
        3. 本地失败 → 告警并抛异常（更新无法回滚，需管理员介入）

        LiteLLM 的 /model/update 需要 model_info.id (模型 ID) 来定位模型。
        """
        extras = extras or UpdateModelExtras()

        local = await LitellmModelParams.get_by_id(db, model_id)
        if not local:
            raise LitellmServiceError(
                f"Cannot update model '{model_id}': model not found in local DB."
            )

        # 使用新名称或保留原名称
        new_model_name = model_name if model_name else local.model_name

        body: dict[str, Any] = {
            "model_name": new_model_name,
            "litellm_params": litellm_params,
        }
        if extras.model_info:
            body["model_info"] = extras.model_info

        logger.info("LiteLLM PATCH /model/%s/update request body: %s", model_id, body)
        await self.request("PATCH", f"/model/{model_id}/update", json_data=body)

        try:
            replace_endpoints = extras.metrics_endpoints is not None
            synced = await _sync_metrics_endpoints(
                db,
                new_model_name,
                local,
                extras.metrics_endpoints,
                replace=replace_endpoints,
            )
            effective_endpoints = (
                synced if replace_endpoints else _endpoints_from_local(local)
            )
            merged = _merge_extra_params(local, extras.model_info)
            row = await LitellmModelParams.upsert(
                db,
                model_id,
                new_model_name,
                LocalModelExtension(
                    metrics_endpoints=synced if replace_endpoints else None,
                    max_concurrent=extras.max_concurrent,
                    extra_params=merged,
                ),
            )
        except Exception:
            logger.warning(
                "LiteLLM model '%s' updated successfully but local DB "
                "write failed — metrics_endpoints may be stale. "
                "Manual fix required.",
                model_id,
            )
            raise

        return {
            "id": model_id,
            "model_name": new_model_name,
            "metrics_endpoints": effective_endpoints or [],
            "max_concurrent": extras.max_concurrent,
            "updated_at": row.updated_at,
        }

    async def delete_model(
        self,
        db: AsyncSession,
        model_id: str,
    ) -> dict:
        """删除模型。

        1. POST /model/delete → LiteLLM（404/400 幂等）
        2. 清理 agent-metrics 抓取条目（job 被共用时跳过，失败降级告警）
        3. DELETE litellm_model_params → 本地

        当本地记录不存在时，LiteLLM 删除失败不阻塞。
        """
        local = await LitellmModelParams.get_by_id(db, model_id)
        orphan_warning = False

        # 无论本地是否有记录，都尝试从 LiteLLM 删除
        try:
            await self.request(
                "POST",
                "/model/delete",
                json_data={"id": model_id},
            )
        except LitellmUpstreamError as e:
            if e.status_code not in MODEL_DELETE_IDEMPOTENT_STATUS_CODES:
                raise
            # 404/400 视为幂等成功
        except Exception:
            # 本地无记录时 LiteLLM 删除失败不阻塞
            if local:
                raise
            orphan_warning = True
            logger.warning(
                "Model '%s' not found in local DB and LiteLLM deletion failed.",
                model_id,
            )

        metrics_warning = await _sync_metrics_on_delete(
            db,
            local.model_name if local else model_id,
            local,
            model_id,
        )
        await LitellmModelParams.delete_by_id(db, model_id)
        return {
            "ok": True,
            "orphan_warning": orphan_warning,
            "metrics_warning": metrics_warning,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 用户管理
    # ═══════════════════════════════════════════════════════════════════════════

    async def create_user(
        self,
        uid: str,
        extras: CreateUserExtras | None = None,
    ) -> dict:
        """创建 LiteLLM 用户。"""
        extras = extras or CreateUserExtras()
        body: dict[str, Any] = {
            "user_id": uid,
            "auto_create_key": extras.auto_create_key,
        }
        if extras.rpm_limit is not None:
            body["rpm_limit"] = extras.rpm_limit
        if extras.max_parallel_requests is not None:
            body["max_parallel_requests"] = extras.max_parallel_requests
        if extras.tpm_limit is not None:
            body["tpm_limit"] = extras.tpm_limit

        await self.request("POST", "/user/new", json_data=body)
        return {"ok": True, "user_id": uid}

    async def delete_user(self, db: AsyncSession, uid: str) -> dict:
        """删除 LiteLLM 用户，清本地 Key 映射。

        1. POST /user/delete → LiteLLM（404 幂等）
        2. DELETE FROM litellm_user_key WHERE uid
        """
        try:
            await self.request(
                "POST",
                "/user/delete",
                json_data={"user_ids": [uid]},
            )
        except LitellmUpstreamError as e:
            if e.status_code != RESOURCE_NOT_FOUND_STATUS_CODE:
                raise

        await LitellmUserKey.delete_by_uid(db, uid)
        return {"ok": True}

    # ═══════════════════════════════════════════════════════════════════════════
    # Key 管理
    # ═══════════════════════════════════════════════════════════════════════════

    async def list_keys(self, db: AsyncSession, uid: str) -> dict:
        """查询用户 Key 列表（直查本地，不调 LiteLLM）。"""
        from app.models.user_default_key import UserDefaultKey

        records = await LitellmUserKey.list_by_uid(db, uid)
        default_key_id = None
        default_row = await UserDefaultKey.get_by_uid(db, uid)
        if default_row:
            default_key_id = default_row.key_id
        keys = [
            {
                "uid": r.uid,
                "key_preview": _mask_key(decrypt_key(r.key)),
                "key_alias": r.key_alias,
                "key_name": r.key_name,
                "is_default": r.id == default_key_id,
                "bound_model": r.bound_model,
                "created_at": r.created_at,
                "expires_at": r.expires_at,
            }
            for r in records
        ]
        return {"keys": keys}

    async def apply_key(
        self,
        db: AsyncSession,
        uid: str,
        model: str | None = None,
        key_name: str | None = None,
    ) -> dict:
        """申请 Key — 委托 generate_key_for_user。"""
        return await self._generate_key_for_user(db, uid, model, key_name)

    async def delete_key(
        self,
        db: AsyncSession,
        uid: str,
        key_alias: str,
    ) -> dict:
        """删除 Key — 校验归属 + 删远端 + 清本地。

        LiteLLM 的 /key/delete 需要原始 Key 字符串，而非 key_name。
        """
        record = await LitellmUserKey.get_by_alias(db, key_alias)
        if record is None or record.uid != uid:
            raise KeyNotFoundError("KEY_NOT_FOUND")

        from app.models.user_default_key import UserDefaultKey

        if await UserDefaultKey.is_default_key(db, uid, record.id):
            raise LitellmServiceError("DEFAULT_KEY_CANNOT_DELETE: 默认 Key 不可删除")

        try:
            raw_key = decrypt_key(record.key)
        except Exception as e:
            logger.error("Failed to decrypt key for alias=%s: %s", key_alias, e)
            raise LitellmServiceError(f"Key decryption failed for '{key_alias}'") from e

        try:
            await self.request(
                "POST",
                "/key/delete",
                json_data={"keys": [raw_key]},
            )
        except LitellmUpstreamError as e:
            if e.status_code != RESOURCE_NOT_FOUND_STATUS_CODE:
                raise

        await db.delete(record)
        await db.flush()
        return {"ok": True}

    async def _generate_key_for_user(
        self,
        db: AsyncSession,
        uid: str,
        model: str | None = None,
        key_name: str | None = None,
    ) -> dict:
        """为指定用户生成 Key。

        1. 咨询锁 → 2. 数量校验 → 3. 调 LiteLLM → 4. 写本地 → 5. 失败回滚
        """
        # 1. 获取咨询锁（仅 PostgreSQL）
        lock_key = f"key_create:{uid}"
        try:
            bind = db.get_bind()
            engine_url = str(getattr(bind, "engine", bind).url)
        except Exception:
            engine_url = ""
        if "postgresql" in engine_url:
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": lock_key},
            )
        else:
            logger.warning(
                "Advisory lock unavailable on non-PostgreSQL backend; "
                "concurrent key creation may exceed MAX_KEYS_PER_USER=%d",
                settings.MAX_KEYS_PER_USER,
            )

        # 2. 数量校验
        count = await LitellmUserKey.count_by_uid(db, uid)
        if count >= settings.MAX_KEYS_PER_USER:
            raise MaxKeysReachedError("MAX_KEYS_REACHED")

        # 3. 前置校验加密可用
        try:
            encrypt_key("health-check")
        except Exception as e:
            raise LitellmServiceError(f"Key encryption is misconfigured: {e}") from e

        # 4. 调 LiteLLM 生成 Key
        body: dict[str, Any] = {"user_id": uid}
        if model:
            body["models"] = [model]

        llm_result = await self.request(
            "POST",
            "/key/generate",
            json_data=body,
        )

        key = ""
        key_alias = ""
        expires = None
        if isinstance(llm_result, dict):
            key = llm_result.get("key", "")
            key_alias = llm_result.get(
                "key_name",
                llm_result.get("key_alias", key[:20] if key else ""),
            )
            expires_str = llm_result.get("expires", llm_result.get("expires_at"))
            if expires_str:
                try:
                    expires = datetime.fromisoformat(
                        str(expires_str).replace("Z", "+00:00"),
                    )
                except (ValueError, TypeError):
                    pass

        if not key:
            raise LitellmServiceError("LiteLLM returned an empty key")

        if not key_alias:
            key_alias = key[:20]

        # 5. 加密后写本地映射
        encrypted = encrypt_key(key)
        try:
            record = await LitellmUserKey.create(
                db,
                uid=uid,
                key_alias=key_alias,
                key=encrypted,
                extras=CreateKeyExtras(
                    model=model,
                    expires_at=expires,
                    key_name=key_name,
                ),
            )
        except Exception:
            try:
                await self.request(
                    "POST",
                    "/key/delete",
                    json_data={"keys": [key]},
                )
            except Exception:
                logger.warning(
                    "Failed to rollback LiteLLM key deletion for %s",
                    key_alias,
                )
            raise

        return {
            "key": key,
            "key_id": record.id,
            "key_alias": key_alias,
            "key_name": key_name,
            "uid": uid,
            "models": [model] if model else [],
            "expires": expires,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 使用统计（直连 LiteLLM PG 的 LiteLLM_SpendLogs 表，不经过 HTTP API）
    # ═══════════════════════════════════════════════════════════════════════════

    # LiteLLM PG 表名（与 spend 日志同库，通过 LITELLM_DATABASE_URL 连接）
    _SPEND_TABLE = '"LiteLLM_SpendLogs"'                 # 调用日志：每次请求的 token/花费/状态等
    _TOKEN_TABLE = '"LiteLLM_VerificationToken"'        # 活跃 API Key：用户当前持有的 key
    _DELETED_TOKEN_TABLE = '"LiteLLM_DeletedVerificationToken"'  # 已删除 API Key：用户删过的 key（历史数据仍需统计）
    _PROXY_MODEL_TABLE = '"LiteLLM_ProxyModelTable"'    # 模型注册表：model_id → model_name 映射，用于解析日志中的模型名
    # 过滤系统内部流量：key 黑名单 + user 非空 + model_id 非空（确保只统计真实模型调用）
    _USER_TRAFFIC_FILTER = (
        f"AND api_key IS NOT NULL "
        f"AND api_key NOT IN ('{_SYSTEM_API_KEY_HEALTH_CHECK}', '{_SYSTEM_API_KEY_MASTER}', '{_SYSTEM_API_KEY_NONE}') "
        f'AND "user" IS NOT NULL AND "user" != \'\' '
        f'AND model_id IS NOT NULL AND model_id != \'\''
    )

    def _get_spend_session(self) -> AsyncSession:
        """获取 LiteLLM 数据库会话（懒初始化引擎）。

        LiteLLM 独立部署时，spend 表在 LiteLLM 自己的 PG 中，
        与项目数据库分离。通过 ``LITELLM_DATABASE_URL`` 配置连接。
        """
        if self._litellm_engine is None:
            if not settings.LITELLM_DATABASE_URL:
                raise LitellmServiceError(
                    "LITELLM_DATABASE_URL is not configured. "
                    "Please set it in .env to the LiteLLM PostgreSQL URL."
                )
            self._litellm_engine = create_async_engine(
                settings.LITELLM_DATABASE_URL,
                echo=False,
            )
            self._litellm_sessionmaker = async_sessionmaker(
                self._litellm_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._litellm_sessionmaker()

    async def _query_spend(
        self,
        sql: str,
        params: dict,
    ) -> list[Any]:
        """执行 spend 查询 — 自动从 LiteLLM 数据库获取会话，方法内关闭。

        表/列不存在（如 LiteLLM 未初始化）→ 返回空列表，不影响 Dashboard 展示。
        连接断开、权限不足等真实故障 → 异常向上传播，触发 500 告警。
        """
        session = self._get_spend_session()
        try:
            result = await session.execute(text(sql), params)
            return list(result.fetchall())
        except (OperationalError, ProgrammingError) as e:
            logger.warning(
                "Spend table not available — LiteLLM may not be initialized: %s",
                e,
            )
            return []
        finally:
            await session.close()

    # ── SQL 片段：date_column / user_column ──────────────────────────────────
    # LiteLLM_SpendLogs 用 "startTime" 存时间戳、user 存用户 ID

    _DATE_COL = 'date("startTime")'
    _USER_COL = '"user"'

    async def get_usage_trend(
        self,
        start_date: date,
        end_date: date,
        granularity: str = "day",
        user_id: str | None = None,
    ) -> dict:
        """趋势图 — 按天聚合请求级 spend 数据。"""
        user_filter = ""
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
        }
        if user_id:
            user_filter = f"AND {self._USER_COL} = :user_id"
            params["user_id"] = user_id

        sql = f"""
            SELECT
                {self._DATE_COL} AS time_bucket,
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
            {user_filter}
            {self._USER_TRAFFIC_FILTER}
            GROUP BY {self._DATE_COL}
            ORDER BY {self._DATE_COL}
        """

        rows = await self._query_spend(sql, params)

        items = [
            {
                "time": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
            }
            for row in rows
        ]

        return {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity,
            "items": items,
        }

    async def _get_proxy_model_name_map(self) -> dict[str, str]:
        """查询 LiteLLM_ProxyModelTable，返回 model_id -> model_name 映射。

        ProxyModelTable 与 spend 表同库（LiteLLM PG），作为模型名权威来源：
        存在则用其 model_name 展示；查询失败（表未初始化等）返回空 dict，
        调用方会把带 model_id 的记录归为『已删除模型』。
        """
        sql = f'SELECT model_id, model_name FROM {self._PROXY_MODEL_TABLE}'
        rows = await self._query_spend(sql, {})
        return {row[0]: row[1] for row in rows if row[0]}

    async def get_usage_by_model(
        self,
        start_date: date,
        end_date: date,
    ) -> dict:
        """模型用量分布 — GROUP BY model_id + 映射 ProxyModelTable 展示名。"""
        params = {
            "start_date": start_date,
            "end_date": end_date,
        }

        sql = f"""
            SELECT
                COALESCE(NULLIF(model_id, ''), model) AS key_col,
                COALESCE(NULLIF(model_group, ''), model) AS display_model,
                model_id,
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
            GROUP BY key_col, display_model, model_id
            ORDER BY requests DESC
        """

        rows = await self._query_spend(sql, params)

        # 模型名权威来源：LiteLLM_ProxyModelTable（同 spend 库）
        # 有 model_id 的记录（含已删除模型）一律用它映射；查不到 → 已删除模型
        name_map = await self._get_proxy_model_name_map()

        total_cost = sum(float(row[5]) for row in rows) or 1.0

        # 按展示名聚合（有 model_id 用注册名，查不到归为已删除）
        agg: dict[str, dict[str, int | float]] = {}
        for row in rows:
            mid = row[2] or ""
            display = row[1]
            if mid:
                display = name_map.get(mid, "已删除模型")
            if display not in agg:
                agg[display] = {"tokens": 0, "requests": 0, "cost": 0.0}
            agg[display]["tokens"] += row[3]
            agg[display]["requests"] += row[4]
            agg[display]["cost"] += float(row[5])

        items = []
        for display, vals in agg.items():
            items.append({
                "model": display,
                "tokens": vals["tokens"],
                "requests": vals["requests"],
                "cost": vals["cost"],
                "pct": round(vals["cost"] / total_cost * 100, 1),
            })
        items.sort(key=lambda x: x["requests"], reverse=True)

        return {"items": items}

    async def _query_model_trend(
        self,
        start_date: date,
        end_date: date,
        user_id: str | None = None,
    ) -> dict:
        """按天+模型分组查询调用趋势，支持可选用户过滤。"""
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
        }
        user_filter = ""
        if user_id:
            user_filter = f"AND {self._USER_COL} = :user_id"
            params["user_id"] = user_id

        # 排除系统内部流量（含无 model_id 的非模型调用）
        traffic_filter = self._USER_TRAFFIC_FILTER

        sql = f"""
            SELECT
                {self._DATE_COL} AS time_bucket,
                COALESCE(NULLIF(model_group, ''), model) AS display_model,
                model_id,
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
            {user_filter}
            {traffic_filter}
            GROUP BY time_bucket, display_model, model_id
            ORDER BY time_bucket, display_model
        """

        rows = await self._query_spend(sql, params)

        # 模型名权威来源：LiteLLM_ProxyModelTable（同 spend 库）
        # 有 model_id 的记录（含已删除模型）一律用它映射；查不到 → 已删除模型
        name_map = await self._get_proxy_model_name_map()

        # 按 (date, display_model) 聚合：
        # 有 model_id 用 ProxyModelTable 的注册名（已删除的归为"已删除模型"）
        agg: dict[tuple[str, str], dict[str, float | int]] = {}
        for row in rows:
            date_val = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
            date_key = date_val[:10]
            mid = row[2] or ""
            display = row[1]
            if mid:
                display = name_map.get(mid, "已删除模型")
            key = (date_key, display)
            if key not in agg:
                agg[key] = {"tokens": 0, "requests": 0, "cost": 0.0}
            agg[key]["tokens"] += row[3]
            agg[key]["requests"] += row[4]
            agg[key]["cost"] += float(row[5])

        items = [
            {"date": k[0], "model": k[1], "tokens": v["tokens"], "requests": v["requests"], "cost": v["cost"]}
            for k, v in agg.items()
        ]

        return {
            "start_date": start_date,
            "end_date": end_date,
            "items": items,
        }

    async def get_model_trend(
        self,
        start_date: date,
        end_date: date,
    ) -> dict:
        """模型趋势 — 按天+模型分组，用于堆叠柱状图。"""
        return await self._query_model_trend(start_date=start_date, end_date=end_date)


    async def get_usage_by_user(
        self,
        start_date: date,
        end_date: date,
        top: int = 10,
    ) -> dict:
        """用户用量排行 — GROUP BY user + ORDER BY tokens DESC。top=-1 表示全量，top=0 返回空。"""
        params = {
            "start_date": start_date,
            "end_date": end_date,
        }

        # 查询实际用户总数，若 top 超过总数则自动回退到总数（避免 LIMIT 超范围）
        count_sql = f"""
            SELECT COUNT(DISTINCT {self._USER_COL})
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
        """
        count_rows = await self._query_spend(count_sql, params)
        total_users = count_rows[0][0] if count_rows else 0

        limit_clause = ""
        if top == -1:
            pass  # 全量：不加 LIMIT
        elif top == 0:
            limit_clause = "LIMIT 0"
        else:
            limit_clause = "LIMIT :top"
            params["top"] = min(top, total_users) if total_users > 0 else top

        sql = f"""
            SELECT
                {self._USER_COL},
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
            GROUP BY {self._USER_COL}
            ORDER BY tokens DESC, cost DESC
            {limit_clause}
        """

        rows = await self._query_spend(sql, params)

        items = [
            {
                "user_id": row[0],
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
            }
            for row in rows
        ]

        # 补充 username
        from app.services import get_user_backend
        user_backend = get_user_backend()
        for item in items:
            try:
                uid = uuid.UUID(item["user_id"])
                user = await user_backend.get_user_by_id(uid)
                if user:
                    item["username"] = user.username
            except (ValueError, AttributeError):
                pass

        return {"items": items}

    async def get_user_usage(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        """指定用户每日用量明细 — WHERE user + GROUP BY date。"""
        params = {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
        }

        sql = f"""
            SELECT
                {self._DATE_COL},
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._USER_COL} = :user_id
              AND {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
            GROUP BY {self._DATE_COL}
            ORDER BY {self._DATE_COL}
        """

        rows = await self._query_spend(sql, params)

        daily_activity = [
            {
                "date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
            }
            for row in rows
        ]

        # 该用户的成功率
        sql_success = f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success
            FROM {self._SPEND_TABLE}
            WHERE {self._USER_COL} = :user_id
              AND {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
        """
        rows3 = await self._query_spend(sql_success, params)
        total = rows3[0][0] if rows3 else 0
        success = rows3[0][1] if rows3 else 0
        success_rate = round(success / total * 100, 1) if total > 0 else 0.0

        return {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "daily_activity": daily_activity,
            "success_rate": success_rate,
        }

    async def get_user_model_trend(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        """指定用户按天+模型分组 — 用于个人视图堆叠柱状图。"""
        return await self._query_model_trend(user_id=user_id, start_date=start_date, end_date=end_date)


    async def get_usage_overview(
        self,
        start_date: date,
        end_date: date,
    ) -> dict:
        """全部用户总览 — 按 user 聚合总量 + 按 date 聚合每日趋势。"""
        params = {
            "start_date": start_date,
            "end_date": end_date,
        }

        sql_users = f"""
            SELECT
                {self._USER_COL},
                COALESCE(SUM("total_tokens"), 0) AS total_tokens,
                COALESCE(COUNT(*), 0) AS total_requests,
                COALESCE(SUM(spend), 0) AS total_cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
            GROUP BY {self._USER_COL}
            ORDER BY total_cost DESC
        """
        rows1 = await self._query_spend(sql_users, params)
        users = [
            {
                "user_id": row[0],
                "total_tokens": row[1],
                "total_requests": row[2],
                "total_cost": float(row[3]),
            }
            for row in rows1
        ]

        sql_daily = f"""
            SELECT
                {self._DATE_COL},
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost,
                COALESCE(COUNT(DISTINCT {self._USER_COL}), 0) AS active_users
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
            GROUP BY {self._DATE_COL}
            ORDER BY {self._DATE_COL}
        """
        rows2 = await self._query_spend(sql_daily, params)
        daily = [
            {
                "date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
                "active_users": row[4],
            }
            for row in rows2
        ]

        # 成功率
        sql_success = f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
              {self._USER_TRAFFIC_FILTER}
        """
        rows3 = await self._query_spend(sql_success, params)
        total = rows3[0][0] if rows3 else 0
        success = rows3[0][1] if rows3 else 0
        success_rate = round(success / total * 100, 1) if total > 0 else 0.0

        return {
            "start_date": start_date,
            "end_date": end_date,
            "users": users,
            "daily": daily,
            "success_rate": success_rate,
        }
