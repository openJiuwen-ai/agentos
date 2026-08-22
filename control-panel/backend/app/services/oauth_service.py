"""OAuth2 Provider 业务逻辑 — 客户端校验、授权码签发/兑换、过期清理。

路由层（api/v1/oauth2.py）只做参数提取、跳转 URL 拼接与错误转换，
业务规则（客户端校验、授权码签发/兑换）全部在此。
数据库操作全部委托给 ``OAuth2AuthorizationCode`` 类方法。

所有 public 接口统一挂在 ``OAuth2Service`` 类下，便于后续依赖注入
与模块拆解。后台清理任务保留为模块级协程（lifespan 启动）。
"""

import asyncio
import logging
import secrets

from app import database  # 模块级导入：async_session_maker 在 init_engine 后晚绑定，须经模块属性访问
from app.config import settings
from app.iam.tokens import TokenService
from app.models.oauth2_auth_code import OAuth2AuthorizationCode

logger = logging.getLogger(__name__)


class OAuth2Error(Exception):
    """OAuth2 业务错误 — 路由层转换为对应 HTTP 响应。"""

    def __init__(self, status_code: int, error: str):
        super().__init__(error)
        self.status_code = status_code
        self.error = error


class OAuth2Service:
    """OAuth2 Provider 业务逻辑：客户端校验、授权码签发/兑换、过期清理。

    所有方法均为静态方法，无状态，便于在路由层直接调用或后续通过
    FastAPI ``Depends`` 注入。
    """

    # ── 客户端/redirect_uri 校验 ───────────────────────────────────────

    @staticmethod
    def validate_client(client_id: str | None, client_secret: str | None) -> None:
        """校验 client 凭据（常量时间比较）；不匹配抛 invalid_client。"""
        if (
            not (client_id and client_secret)
            or client_id != settings.OAUTH2_CLIENT_ID
            or not secrets.compare_digest(client_secret, settings.OAUTH2_CLIENT_SECRET)
        ):
            logger.warning(
                "oauth2: client validation failed got_client_id=%r expected=%r",
                client_id, settings.OAUTH2_CLIENT_ID,
            )
            raise OAuth2Error(401, "invalid_client")

    @staticmethod
    def validate_authorize_params(client_id: str, redirect_uri: str) -> None:
        """授权入口参数校验：client_id 已注册 + redirect_uri 匹配（防开放重定向）。"""
        if client_id != settings.OAUTH2_CLIENT_ID:
            raise OAuth2Error(400, "Unknown client")
        if redirect_uri != settings.OAUTH2_REDIRECT_URI:
            raise OAuth2Error(400, "Invalid redirect_uri")

    # ── 授权码 ─────────────────────────────────────────────────────────

    @staticmethod
    async def create_authorization_code(
        user_id: str, client_id: str, redirect_uri: str
    ) -> str:
        """生成并持久化授权码，返回 code。"""
        async with database.async_session_maker() as session:
            entry = await OAuth2AuthorizationCode.create(
                session,
                user_id=user_id,
                client_id=client_id,
                redirect_uri=redirect_uri,
            )
            return entry.code

    @staticmethod
    async def exchange_code_for_token(
        *, code: str, client_id: str, client_secret: str, grant_type: str
    ) -> dict:
        """授权码换 access_token（原子消费授权码，防重放）。"""
        if grant_type != "authorization_code":
            raise OAuth2Error(400, "unsupported_grant_type")

        OAuth2Service.validate_client(client_id, client_secret)

        if not code:
            raise OAuth2Error(400, "invalid_grant")

        async with database.async_session_maker() as session:
            entry = await OAuth2AuthorizationCode.consume(session, code)

        if entry is None or entry.is_expired():
            logger.warning("oauth2: code invalid or expired")
            raise OAuth2Error(400, "invalid_grant")

        token = TokenService.create_oauth2_access_token(
            user_id=str(entry.user_id), username=""
        )
        logger.info("oauth2: token issued user_id=%s", entry.user_id)
        return {"access_token": token, "token_type": "bearer"}


# ── 过期清理后台任务 ──────────────────────────────────────────────────
# 保留为模块级协程：lifespan 启动时 asyncio.create_task 调度，不参与
# 请求级依赖注入，无需挂在 Service 类下。

async def auth_code_cleanup_task() -> None:
    """每 60 秒清理过期授权码（best-effort）。供 main.py lifespan 以 asyncio task 启动。"""
    while True:
        await asyncio.sleep(60)
        try:
            if database.async_session_maker is None:
                continue
            async with database.async_session_maker() as session:
                deleted = await OAuth2AuthorizationCode.delete_expired(session)
                if deleted:
                    logger.info("oauth2: cleaned up %d expired auth code(s)", deleted)
        except Exception:
            pass  # best-effort cleanup
