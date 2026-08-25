"""FastAPI entry point — wires backend, IAM, LiteLLM, and API routes together."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.thirdparty_agent import router as thirdparty_agent_router
from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.litellm_key import router as litellm_key_router
from app.api.v1.litellm_model import router as litellm_router, config_router as mass_config_router
from app.api.v1.litellm_usage import router as litellm_usage_router
from app.api.v1.logs import router as logs_router
from app.api.v1.logs_ws import ws_router as logs_ws_router
from app.api.v1.log_loki import router as log_loki_router
from app.api.v1.users import router as users_router
from app.api.v1.oauth2 import oauth2_router
from app.api.v1.hardware import router as hardware_router
from app.api.v1.node_service import router as node_service_router
from app.config import settings
from app.core.logging import setup_file_logging
from app.iam.engine import ensure_iam_tables, ensure_oauth2_tables
from app.services import get_user_backend
from app.services.litellm_service import LitellmService
from app.services.log_export import start_log_services, stop_log_services
from app.thirdparty_agent import ensure_thirdparty_agent_tables

logger = logging.getLogger("app")

# OAuth2 Provider 是否启用：client_id / client_secret / client_name 均已配置
_OAUTH2_ENABLED = bool(
    settings.OAUTH2_CLIENT_ID
    and settings.OAUTH2_CLIENT_SECRET
    and settings.OAUTH2_CLIENT_NAME
)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # 0. Set up file logging (deferred from module import — no FS side effects).
    setup_file_logging()

    # 1. Create the shared database engine (single source of truth).
    from app import database

    database.init_engine()

    # 2. Start the user-system backend (uses the shared engine).
    backend = get_user_backend()
    await backend.on_startup()

    # 3. Create IAM and thirdparty_agent tables on the same engine.
    engine = backend.get_engine()
    if engine is not None:
        await ensure_iam_tables(engine)
        await _create_log_tables(engine)
        await ensure_thirdparty_agent_tables(engine)

        # 4. Create OAuth2 tables (only when enabled)
        if _OAUTH2_ENABLED:
            await ensure_oauth2_tables(engine)

    logger.info("backend-api started (backend: %s)", type(backend).__name__)

    # 4. LiteLLM 模型管理服务
    litellm_svc = LitellmService()
    fastapi_app.state.litellm_svc = litellm_svc
    from app.services import register_litellm_svc

    register_litellm_svc(litellm_svc)
    logger.info("LitellmService attached to app.state")

    # 4.5 嗅探推理服务并自动注册模型
    await _seed_initial_model(litellm_svc)

    # 4.6 初始化管理员（建用户 + 同步 LiteLLM + 申请 Key + 建目录 + 写 config）
    await backend.seed_initial_admin()

    # 5. Hardware monitoring service
    from app.services.hardware_service import HardwareService

    hw_svc = HardwareService()
    fastapi_app.state.hardware_svc = hw_svc
    logger.info("HardwareService attached to app.state")

    # 5. Start OAuth2 auth code cleanup task (only when enabled)
    if _OAUTH2_ENABLED:
        from app.services.oauth_service import auth_code_cleanup_task

        _oauth2_cleanup_task = asyncio.create_task(auth_code_cleanup_task())
    else:
        _oauth2_cleanup_task = None

    # 6. 日志中心 — 定时任务 + 导出 Worker
    await start_log_services()

    yield

    # ── 清理 ──────────────────────────────────────────────────────────────
    from app.api.v1.litellm_model import _sync_timer_task as _agentos_timer
    if _agentos_timer is not None and not _agentos_timer.done():
        _agentos_timer.cancel()
        try:
            await _agentos_timer
        except asyncio.CancelledError:
            pass

    if _oauth2_cleanup_task is not None:
        _oauth2_cleanup_task.cancel()
        try:
            await _oauth2_cleanup_task
        except asyncio.CancelledError:
            pass
    await hw_svc.close()
    await stop_log_services()
    await litellm_svc.close()
    from app.api.v1.node_service import close_client as close_ns_client
    await close_ns_client()
    await backend.on_shutdown()
    await database.dispose_engine()
    logger.info("backend-api shut down.")


async def _create_log_tables(engine):
    from app.models.base import Base
    from app.models.log import LogComponent, LogExportTask  # noqa: F401
    from sqlalchemy import text
    from app.models.user_default_key import UserDefaultKey  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会为已存在的表补充新列，这里做轻量迁移
        await conn.execute(
            text("ALTER TABLE log_export_task ADD COLUMN IF NOT EXISTS query_spec TEXT")
        )


async def _seed_initial_model(litellm_svc: LitellmService) -> None:
    """注册初始模型到 LiteLLM。

    优先读 INITIAL_MODELS（JSON 字符串，deploy 脚本嗅探后写入）。
    INITIAL_MODELS 为空时，回退到管理面嗅探推理服务。
    部署框架和监控地址由 deploy 脚本处理，后端只注册模型和 context_window。
    """
    import json

    # 获取模型列表：优先 INITIAL_MODELS，回退到嗅探
    if settings.INITIAL_MODELS:
        try:
            models_str = settings.INITIAL_MODELS.strip().strip("'").strip('"')
            model_list = json.loads(models_str)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"INITIAL_MODELS JSON 解析失败: {e}。"
                f"请检查 .env 中 INITIAL_MODELS 的格式"
            ) from e
        if not isinstance(model_list, list) or not model_list:
            raise RuntimeError(
                "INITIAL_MODELS 为空或格式异常，未找到可注册的模型。"
                "请检查 deploy 脚本是否正确嗅探并写入了模型信息"
            )
        logger.info("从 INITIAL_MODELS 读取到 %d 个模型: %s", len(model_list), [m.get("id") for m in model_list])
    else:
        # 回退：管理面嗅探推理服务
        api_base = settings.INITIAL_MODEL_API_BASE
        if not api_base:
            logger.info("未配置 INITIAL_MODELS 和 INITIAL_MODEL_API_BASE，跳过初始模型注册")
            return

        api_base = api_base.rstrip("/")

        import httpx
        headers = {}
        if settings.INITIAL_MODEL_API_KEY:
            headers["Authorization"] = f"Bearer {settings.INITIAL_MODEL_API_KEY}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{api_base}/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"推理服务 {api_base}/models 返回错误状态码 {e.response.status_code}。"
                f"请检查 INITIAL_MODEL_API_KEY 是否正确"
            ) from e
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
            raise RuntimeError(
                f"无法连接推理服务 {api_base}/models: {e}。"
                f"请检查 INITIAL_MODEL_API_BASE 是否正确、推理服务是否已启动"
            ) from e

        model_list = data.get("data") if isinstance(data, dict) else None
        if not model_list or not isinstance(model_list, list):
            raise RuntimeError(
                f"推理服务 {api_base}/models 返回为空或格式异常，未找到可注册的模型。"
                f"请检查推理服务是否已加载模型"
            )
        logger.info("嗅探到 %d 个模型: %s", len(model_list), [m.get("id") for m in model_list])

    from app.database import async_session_maker
    from app.services.litellm_service import CreateModelExtras

    # 查 LiteLLM 已有模型列表
    try:
        llm_data = await litellm_svc.request("GET", "/model/info")
        llm_names = set()
        if isinstance(llm_data, dict) and "data" in llm_data:
            llm_names = {m.get("model_name") for m in llm_data["data"] if m.get("model_name")}
        elif isinstance(llm_data, list):
            llm_names = {m.get("model_name") for m in llm_data if m.get("model_name")}
    except Exception:
        logger.warning("查询 LiteLLM 已有模型失败，将注册所有模型", exc_info=True)
        llm_names = set()

    # api_base 用于注册到 LiteLLM（LiteLLM 转发推理请求用）
    if not settings.INITIAL_MODEL_API_BASE:
        logger.info("未配置 INITIAL_MODEL_API_BASE，跳过初始模型注册")
        return
    api_base = settings.INITIAL_MODEL_API_BASE.rstrip("/")

    async with async_session_maker() as session:
        for m in model_list:
            model_name = m.get("id", "")
            if not model_name:
                continue

            if model_name in llm_names:
                logger.info("模型 '%s' 在 LiteLLM 已存在，跳过", model_name)
                continue

            # context_window：优先从模型信息取
            context_window = m.get("context_window")
            if context_window is None:
                context_window = m.get("max_model_len")
            model_info = {}
            if context_window is not None:
                model_info["context_window"] = int(context_window)

            litellm_params: dict = {
                "model": f"openai/{model_name}",
                "api_base": api_base,
                # LiteLLM 对 openai/* 模型强制要求 api_key 字段，未配置时用占位符
                "api_key": settings.INITIAL_MODEL_API_KEY or "sk-1234",
            }

            try:
                await litellm_svc.create_model(
                    session,
                    model_name=model_name,
                    litellm_params=litellm_params,
                    extras=CreateModelExtras(
                        model_info=model_info if model_info else None,
                    ),
                )
                await session.commit()
                logger.info("模型 '%s' 注册成功", model_name)
            except Exception:
                await session.rollback()
                logger.warning("注册模型 '%s' 失败", model_name, exc_info=True)


app = FastAPI(
    title="AgentOS Panel — Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── 注册路由 ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(agent_router)
app.include_router(litellm_router)
app.include_router(mass_config_router)
app.include_router(litellm_key_router)
app.include_router(litellm_usage_router)
app.include_router(hardware_router)
app.include_router(node_service_router)
app.include_router(logs_router)
app.include_router(logs_ws_router)
app.include_router(log_loki_router)
app.include_router(thirdparty_agent_router)

# OAuth2 Provider — 仅当 client_id / client_secret / client_name 均已配置时才启用
if not _OAUTH2_ENABLED:
    logger.warning(
        "OAuth2 Provider 未启用 (OAUTH2_CLIENT_ID=%r, OAUTH2_CLIENT_SECRET=%s, OAUTH2_CLIENT_NAME=%r)，"
        "OAuth2 路由未注册。"
        "如需启用请在 .env 中设置 OAUTH2_CLIENT_ID / OAUTH2_CLIENT_SECRET / OAUTH2_CLIENT_NAME。",
        settings.OAUTH2_CLIENT_ID,
        "已设置" if settings.OAUTH2_CLIENT_SECRET else "为空",
        settings.OAUTH2_CLIENT_NAME or "为空",
    )
else:
    logger.info(
        "OAuth2 Provider enabled (client_id=%s, client_name=%s)",
        settings.OAUTH2_CLIENT_ID, settings.OAUTH2_CLIENT_NAME,
    )
    app.include_router(oauth2_router)


@app.get("/")
async def root():
    return {"service": "AgentOS Panel Backend API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
