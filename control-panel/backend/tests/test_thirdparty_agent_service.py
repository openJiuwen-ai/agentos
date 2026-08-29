"""Service tests for publish / retry / unregistered delete."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.thirdparty_agent_service import ThirdpartyAgentService
from app.thirdparty_agent.exceptions import (
    AgentNotFoundError,
    InvalidUploadError,
    PackageLockedError,
)


@pytest.mark.asyncio
async def test_retry_missing_digest(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "THIRDPARTY_AGENT_PACKAGE_DIR", str(tmp_path))
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=AsyncMock())
    with patch(
        "app.services.thirdparty_agent_service.BuildTask.get_by_path",
        AsyncMock(
            return_value=[],
        ),
    ):
        with pytest.raises(AgentNotFoundError):
            await svc.retry(AsyncMock(), "0" * 64, "demo", "admin")


@pytest.mark.asyncio
async def test_retry_requires_launch_command():
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=AsyncMock())
    with pytest.raises(InvalidUploadError, match="must not be empty"):
        await svc.retry(AsyncMock(), "0" * 64, " ", "admin")


@pytest.mark.asyncio
async def test_delete_unregistered_refuses_lock(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "THIRDPARTY_AGENT_PACKAGE_DIR", str(tmp_path))
    digest = "0" * 64
    task = MagicMock(status="building")
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=AsyncMock())
    with patch(
        "app.services.thirdparty_agent_service.BuildTask.get_by_path",
        AsyncMock(
            return_value=[task],
        ),
    ):
        with pytest.raises(PackageLockedError):
            await svc.delete_unregistered(AsyncMock(), digest)
