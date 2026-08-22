"""IAM engine — manages IAM and OAuth2 table lifecycle.

These tables are IAM infrastructure, not backend-specific.
They live on the same database as the user tables but are managed
by the IAM layer. Each ensure function only creates its own module's
tables — never the full shared metadata.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.base import Base

# 导入即向 Base.metadata 注册模型；create_all 时用显式 tables= 参数限定范围
from app.models.user_revocation import UserRevocation  # noqa: F401
from app.models.oauth2_auth_code import OAuth2AuthorizationCode  # noqa: F401

logger = logging.getLogger(__name__)


async def ensure_iam_tables(engine: AsyncEngine) -> None:
    """Create IAM-specific tables (revocation) on the backend's engine.

    Called during startup after the backend has initialized its engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[UserRevocation.__table__]
        )
    logger.info("IAM tables (revocation) ensured.")


async def ensure_oauth2_tables(engine: AsyncEngine) -> None:
    """Create OAuth2-specific tables (authorization codes) on the backend's engine.

    Called during startup when the OAuth2 Provider is enabled.
    """
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[OAuth2AuthorizationCode.__table__]
        )
    logger.info("OAuth2 tables (authorization codes) ensured.")
