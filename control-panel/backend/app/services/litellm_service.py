"""LitellmService — LiteLLM 模型管理核心类

职责：LiteLLM HTTP 调用 + 本地 DB 读写 + 业务编排。
路由层仅做参数提取 + 调用 Service 方法。
"""

import asyncio
import os
import base64

import logging
from dataclasses import dataclass
from datetime import datetime
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


# ─── 辅助 dataclass ──────────────────────────────────────────────────────────────


@dataclass
class CreateModelExtras:
    """收敛 create_model 的可选参数（满足参数个数限制）。"""

    model_info: dict | None = None
    instance_url: str | None = None
    max_concurrent: int | None = None
    inference_engine: str | None = None


@dataclass
class UpdateModelExtras:
    """收敛 update_model 的可选参数（满足参数个数限制）。"""

    model_info: dict | None = None
    instance_url: str | None = None
    max_concurrent: int | None = None
    inference_engine: str | None = None


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
        "instance_url": local.instance_url if local else None,
        "max_concurrent": local.max_concurrent if local else None,
        "inference_engine": local.inference_engine if local else None,
        "grafana_job_name": _grafana_job_from_local(local),
        "status": status,
        "created_at": local.created_at if local else None,
        "updated_at": local.updated_at if local else None,
    }


def _grafana_job_from_local(local: LitellmModelParams | None) -> str | None:
    """从本地 extra_params.grafana_job_name 取出 job 名。"""
    if not local or not local.extra_params:
        return None
    value = local.extra_params.get(METRICS_JOB_KEY)
    if value is not None and str(value).strip():
        return str(value).strip()
    return None


def _require_inference_engine(
    inference_engine: str | None = None,
    local: LitellmModelParams | None = None,
) -> str:
    """取得用于拼 job 的推理引擎名

    job 格式固定为 ``{inference_engine}-{target}``，由 agent_metrics_config.build_job 生成。
    """
    for value in (inference_engine, local.inference_engine if local else None):
        if value is not None and str(value).strip():
            return str(value).strip()
    raise LitellmServiceError(
        "缺少 inference_engine（部署框架），无法维护 agent-metrics.json "
        "（job 必须为 inference_engine-target）"
    )


def _metrics_extra_from_local(local: LitellmModelParams | None) -> dict[str, str]:
    job = _grafana_job_from_local(local)
    if not job:
        return {}
    return {METRICS_JOB_KEY: job}


async def _sync_metrics_on_create(
    model_name: str,
    instance_url: str | None,
    inference_engine: str | None = None,
) -> dict[str, str] | None:
    if not instance_url:
        return None
    engine = _require_inference_engine(inference_engine)
    try:
        # job = f"{inference_engine}-{target}"（引擎名小写）
        job = await asyncio.to_thread(
            agent_metrics_config.add_entry, engine, instance_url,
        )
    except agent_metrics_config.AgentMetricsConfigError as e:
        logger.exception(
            "Failed to update agent-metrics.json on create for model '%s'",
            model_name,
        )
        raise LitellmServiceError(str(e)) from e
    return {METRICS_JOB_KEY: job}


async def _sync_metrics_on_update(
    model_name: str,
    local: LitellmModelParams | None,
    instance_url: str | None,
    inference_engine: str | None = None,
) -> dict[str, str] | None:
    effective_url = instance_url
    if effective_url is None and local:
        effective_url = local.instance_url
    if not effective_url:
        return None

    old_extra = _metrics_extra_from_local(local)
    old_job = old_extra.get(METRICS_JOB_KEY)
    engine = _require_inference_engine(inference_engine, local)
    try:
        # job = f"{inference_engine}-{target}"（引擎名小写）
        job = await asyncio.to_thread(
            agent_metrics_config.update_entry,
            old_job,
            engine,
            effective_url,
        )
    except agent_metrics_config.AgentMetricsConfigError as e:
        logger.exception(
            "Failed to update agent-metrics.json on update for model '%s'",
            model_name,
        )
        raise LitellmServiceError(str(e)) from e
    return {METRICS_JOB_KEY: job}


async def _sync_metrics_on_delete(
    model_name: str,
    local: LitellmModelParams | None,
) -> None:
    if not local:
        return
    old_job = _grafana_job_from_local(local)
    if not old_job and not local.instance_url:
        return
    engine = local.inference_engine
    try:
        await asyncio.to_thread(
            agent_metrics_config.remove_entry,
            old_job,
            local.instance_url,
            engine,
        )
    except agent_metrics_config.AgentMetricsConfigError as e:
        logger.exception(
            "Failed to update agent-metrics.json on delete for model '%s'",
            model_name,
        )
        raise LitellmServiceError(str(e)) from e


def _merge_extra_params(
    local: LitellmModelParams | None,
    metrics_extra: dict[str, str] | None,
) -> dict | None:
    if metrics_extra is None:
        return None
    merged = dict(local.extra_params) if local and local.extra_params else {}
    merged.update(metrics_extra)
    return merged


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

        if response.status_code == 204 or not response.content:
            return {}

        try:
            data = response.json()
        except Exception as e:
            text_content = response.text[:500]
            raise LitellmUpstreamError(
                status_code=response.status_code,
                detail=f"Non-JSON response: {text_content}",
            ) from e

        if response.status_code >= 400:
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

        # 获取健康状态
        health_map = await _build_health_map(self)

        tasks = [
            _fetch_model_detail(self, m, local_by_name.get(m.get("model_name")), health_map)
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

        metrics_extra = None
        try:
            metrics_extra = await _sync_metrics_on_create(
                model_name,
                extras.instance_url,
                extras.inference_engine,
            )
            row = await LitellmModelParams.upsert(
                db,
                model_id,
                model_name,
                LocalModelExtension(
                    instance_url=extras.instance_url,
                    max_concurrent=extras.max_concurrent,
                    inference_engine=extras.inference_engine,
                    extra_params=metrics_extra,
                ),
            )
        except Exception:
            if metrics_extra:
                try:
                    await asyncio.to_thread(
                        agent_metrics_config.remove_entry,
                        metrics_extra.get(METRICS_JOB_KEY),
                        extras.instance_url,
                        extras.inference_engine,
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
            "instance_url": extras.instance_url,
            "max_concurrent": extras.max_concurrent,
            "inference_engine": extras.inference_engine,
            "grafana_job_name": (metrics_extra or {}).get(METRICS_JOB_KEY),
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
            # 本地记录不存在，先创建
            local = await LitellmModelParams.upsert(
                db,
                model_id,
                model_name or model_id,
                LocalModelExtension(),
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
            metrics_extra = await _sync_metrics_on_update(
                new_model_name,
                local,
                extras.instance_url,
                extras.inference_engine,
            )
            row = await LitellmModelParams.upsert(
                db,
                model_id,
                new_model_name,
                LocalModelExtension(
                    instance_url=extras.instance_url,
                    max_concurrent=extras.max_concurrent,
                    inference_engine=extras.inference_engine,
                    extra_params=_merge_extra_params(local, metrics_extra),
                ),
            )
        except Exception:
            logger.warning(
                "LiteLLM model '%s' updated successfully but local DB "
                "write failed — instance_url may be stale. "
                "Manual fix required.",
                model_id,
            )
            raise

        return {
            "id": model_id,
            "model_name": new_model_name,
            "instance_url": extras.instance_url,
            "max_concurrent": extras.max_concurrent,
            "inference_engine": extras.inference_engine,
            "grafana_job_name": (
                (metrics_extra or {}).get(METRICS_JOB_KEY)
                or _grafana_job_from_local(row)
            ),
            "updated_at": row.updated_at,
        }

    async def delete_model(
        self,
        db: AsyncSession,
        model_id: str,
    ) -> dict:
        """删除模型。

        1. 按 ID 查本地 DB → POST /model/delete → LiteLLM（404/400 幂等）
        2. DELETE litellm_model_params → 本地

        当本地记录不存在时，跳过 LiteLLM 调用并告警。
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
            if e.status_code not in (404, 400):
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

        await LitellmModelParams.delete_by_id(db, model_id)
        await _sync_metrics_on_delete(
            local.model_name if local else model_id, local,
        )
        return {"ok": True, "orphan_warning": orphan_warning}

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
            if e.status_code != 404:
                raise

        await LitellmUserKey.delete_by_uid(db, uid)
        return {"ok": True}

    # ═══════════════════════════════════════════════════════════════════════════
    # Key 管理
    # ═══════════════════════════════════════════════════════════════════════════

    async def list_keys(self, db: AsyncSession, uid: str) -> dict:
        """查询用户 Key 列表（直查本地，不调 LiteLLM）。"""
        records = await LitellmUserKey.list_by_uid(db, uid)
        keys = [
            {
                "uid": r.uid,
                "key_preview": _mask_key(decrypt_key(r.key)),
                "key_alias": r.key_alias,
                "key_name": r.key_name,
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
            if e.status_code != 404:
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
            await LitellmUserKey.create(
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
            "key_alias": key_alias,
            "key_name": key_name,
            "uid": uid,
            "models": [model] if model else [],
            "expires": expires,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 使用统计（直连 LiteLLM PG 的 LiteLLM_SpendLogs 表，不经过 HTTP API）
    # ═══════════════════════════════════════════════════════════════════════════

    _SPEND_TABLE = '"LiteLLM_SpendLogs"'

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
        db: AsyncSession | None,
        sql: str,
        params: dict,
    ) -> list[Any]:
        """执行 spend 查询。

        - ``db`` 非 None 时使用传入的会话（测试/兼容），调用方负责关闭。
        - ``db`` 为 None 时自动从 LiteLLM 数据库获取会话，方法内关闭。

        表/列不存在（如 LiteLLM 未初始化）→ 返回空列表，不影响 Dashboard 展示。
        连接断开、权限不足等真实故障 → 异常向上传播，触发 500 告警。
        """
        session = db or self._get_spend_session()
        owns = db is None
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
            if owns:
                await session.close()

    # ── SQL 片段：date_column / user_column ──────────────────────────────────
    # LiteLLM_SpendLogs 用 "startTime" 存时间戳、user 存用户 ID

    _DATE_COL = 'date("startTime")'
    _USER_COL = '"user"'

    @staticmethod
    def _to_date(s: str):
        """字符串 → date 对象（asyncpg 不接受字符串与 PG date 列比较）。"""
        from datetime import date

        return date.fromisoformat(s)

    async def get_usage_trend(
        self,
        db: AsyncSession | None = None,
        start_date: str = "",
        end_date: str = "",
        granularity: str = "day",
        user_id: str | None = None,
    ) -> dict:
        """趋势图 — 按天聚合请求级 spend 数据。"""
        user_filter = ""
        params: dict[str, Any] = {
            "start_date": self._to_date(start_date),
            "end_date": self._to_date(end_date),
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
            GROUP BY {self._DATE_COL}
            ORDER BY {self._DATE_COL}
        """

        rows = await self._query_spend(db, sql, params)

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

    async def get_usage_by_model(
        self,
        db: AsyncSession | None = None,
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """模型用量分布 — GROUP BY model + 占比计算。"""
        params = {
            "start_date": self._to_date(start_date),
            "end_date": self._to_date(end_date),
        }

        sql = f"""
            SELECT
                model,
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
            GROUP BY model
            ORDER BY cost DESC
        """

        rows = await self._query_spend(db, sql, params)

        total_cost = sum(float(row[3]) for row in rows) or 1.0

        items = [
            {
                "model": row[0],
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
                "pct": round(float(row[3]) / total_cost * 100, 1),
            }
            for row in rows
        ]

        return {"items": items}

    async def get_usage_by_user(
        self,
        db: AsyncSession | None = None,
        start_date: str = "",
        end_date: str = "",
        top: int = 10,
    ) -> dict:
        """用户用量排行 — GROUP BY user + ORDER BY cost DESC LIMIT N。"""
        params = {
            "start_date": self._to_date(start_date),
            "end_date": self._to_date(end_date),
            "top": top,
        }

        sql = f"""
            SELECT
                {self._USER_COL},
                COALESCE(SUM("total_tokens"), 0) AS tokens,
                COALESCE(COUNT(*), 0) AS requests,
                COALESCE(SUM(spend), 0) AS cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
            GROUP BY {self._USER_COL}
            ORDER BY cost DESC
            LIMIT :top
        """

        rows = await self._query_spend(db, sql, params)

        items = [
            {
                "user_id": row[0],
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
            }
            for row in rows
        ]

        return {"items": items}

    async def get_user_usage(
        self,
        db: AsyncSession | None = None,
        user_id: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """指定用户每日用量明细 — WHERE user + GROUP BY date。"""
        params = {
            "user_id": user_id,
            "start_date": self._to_date(start_date),
            "end_date": self._to_date(end_date),
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
            GROUP BY {self._DATE_COL}
            ORDER BY {self._DATE_COL}
        """

        rows = await self._query_spend(db, sql, params)

        daily_activity = [
            {
                "date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                "tokens": row[1],
                "requests": row[2],
                "cost": float(row[3]),
            }
            for row in rows
        ]

        return {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "daily_activity": daily_activity,
        }

    async def get_usage_overview(
        self,
        db: AsyncSession | None = None,
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """全部用户总览 — 按 user 聚合总量 + 按 date 聚合每日趋势。"""
        params = {
            "start_date": self._to_date(start_date),
            "end_date": self._to_date(end_date),
        }

        sql_users = f"""
            SELECT
                {self._USER_COL},
                COALESCE(SUM("total_tokens"), 0) AS total_tokens,
                COALESCE(COUNT(*), 0) AS total_requests,
                COALESCE(SUM(spend), 0) AS total_cost
            FROM {self._SPEND_TABLE}
            WHERE {self._DATE_COL} BETWEEN :start_date AND :end_date
            GROUP BY {self._USER_COL}
            ORDER BY total_cost DESC
        """
        rows1 = await self._query_spend(db, sql_users, params)
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
            GROUP BY {self._DATE_COL}
            ORDER BY {self._DATE_COL}
        """
        rows2 = await self._query_spend(db, sql_daily, params)
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

        return {
            "start_date": start_date,
            "end_date": end_date,
            "users": users,
            "daily": daily,
        }
