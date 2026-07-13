"""IAM engine — manages revocation table lifecycle.

The revocation table is IAM infrastructure, not backend-specific.
It lives on the same database as the user tables but is managed
by the IAM layer.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.base import Base

# Register the revocation table (IAM infrastructure)
from app.models import user_revocation  # noqa: F401

logger = logging.getLogger(__name__)


async def ensure_iam_tables(engine: AsyncEngine) -> None:
    """Create IAM-specific tables (revocation) on the backend's engine.

    Called during startup after the backend has initialized its engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("IAM tables (revocation) ensured.")
