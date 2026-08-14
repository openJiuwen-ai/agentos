"""Unit tests for thirdparty_agent schemas."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.thirdparty_agent import (
    InstallerListItem,
    BuildStatusResponse,
    BuildTaskRequest,
    BuildTaskResponse,
)


def _has_sqlalchemy():
    from importlib.util import find_spec
    return find_spec("sqlalchemy") is not None


_skip_sql = pytest.mark.skipif(not _has_sqlalchemy(), reason="sqlalchemy not installed")


class TestBuildTaskRequest:
    @staticmethod
    def test_all_fields():
        r = BuildTaskRequest(
            agent_name="opencode",
            version="1.1.0",
            display_name="OpenCode v2",
            entrypoint="opencode",
        )
        assert r.agent_name == "opencode"
        assert r.version == "1.1.0"
        assert r.display_name == "OpenCode v2"
        assert r.entrypoint == "opencode"


class TestInstallerListItem:
    @staticmethod
    def test_all_fields():
        r = InstallerListItem(
            agent_name="opencode",
            version="1.0.0",
            display_name="OpenCode",
            entrypoint="opencode",
        )
        assert r.agent_name == "opencode"
        assert r.version == "1.0.0"


class TestBuildTaskResponse:
    @staticmethod
    def test_pending_creation():
        r = BuildTaskResponse(task_id="build-abc123", status="pending")
        assert r.task_id == "build-abc123"
        assert r.status == "pending"
        assert r.created_at is None


class TestBuildStatusResponse:
    @staticmethod
    def test_done():
        from datetime import datetime, timezone

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 15, 12, 5, 0, tzinfo=timezone.utc)
        r = BuildStatusResponse(
            task_id="build-abc", status="done", progress=100,
            image="opencode:1.0.0", image_digest="sha256:abc",
            started_at=now, finished_at=end,
            registered=True,
        )
        assert r.status == "done"
        assert r.progress == 100
        assert r.registered is True
        assert r.image == "opencode:1.0.0"

    @staticmethod
    def test_failed():
        r = BuildStatusResponse(task_id="build-abc", status="failed")
        assert r.status == "failed"
        assert r.registered is False
        assert r.progress == 0

    @staticmethod
    def test_building():
        r = BuildStatusResponse(
            task_id="build-abc", status="building", progress=42,
        )
        assert r.status == "building"
        assert r.progress == 42
        assert r.registered is False


# ═══════════════════════════════════════════════════════════════════════════
# list_installers with framework filter + pagination
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@_skip_sql
class TestListInstallers:

    @staticmethod
    async def test_forwards_framework_and_pagination_params_to_registry():
        """Framework + page/size params are all forwarded to the external registry."""
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, ListInstallersParams,
        )

        mock_images = [
            {"framework": "opencode", "framework_version": "1.0.0"},
            {"framework": "opencode", "framework_version": "1.1.0"},
        ]
        mock_headers = {"X-Total-Count": "2"}
        mock_resp = MagicMock(status_code=200, headers=mock_headers)
        mock_resp.json.return_value = mock_images

        with patch(
            "app.services.thirdparty_agent_service.AgentRegistration"
        ) as mock_reg, patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock
        ) as mock_get, patch(
            "app.services.thirdparty_agent_service.settings"
        ) as mock_settings:
            mock_settings.AGENT_REGISTER_URL = "http://registry"
            mock_get.return_value = mock_resp
            mock_reg.get = AsyncMock(return_value=None)

            result = await ThirdpartyAgentService.list_installers(
                AsyncMock(),
                ListInstallersParams(uploaded_by="admin", framework="opencode", size=20, page=1),
            )

            # Verify all expected params are forwarded to registry
            call_args = mock_get.call_args
            assert call_args is not None
            params = call_args[1]["params"]
            assert params["framework"] == "opencode"
            assert params["uploaded_by"] == "admin"
            assert params["page"] == "1"
            assert params["size"] == "20"
            # total from X-Total-Count header
            assert result.total == 2
            assert len(result.items) == 2

    @staticmethod
    async def test_server_side_pagination():
        """Page 2 with size=2: registry returns only page items + X-Total-Count."""
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, ListInstallersParams,
        )

        # Registry returns only page 2 items (indices 2,3 of 5)
        mock_images = [
            {"framework": "fw2", "framework_version": "v2"},
            {"framework": "fw3", "framework_version": "v3"},
        ]
        mock_headers = {"X-Total-Count": "5"}
        mock_resp = MagicMock(status_code=200, headers=mock_headers)
        mock_resp.json.return_value = mock_images

        with patch(
            "app.services.thirdparty_agent_service.AgentRegistration"
        ) as mock_reg, patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock
        ) as mock_get, patch(
            "app.services.thirdparty_agent_service.settings"
        ) as mock_settings:
            mock_settings.AGENT_REGISTER_URL = "http://registry"
            mock_get.return_value = mock_resp
            mock_reg.get = AsyncMock(return_value=None)

            result = await ThirdpartyAgentService.list_installers(
                AsyncMock(),
                ListInstallersParams(uploaded_by="admin", framework="", size=2, page=2),
            )

            # Params forwarded to registry
            call_args = mock_get.call_args
            assert call_args is not None
            assert call_args[1]["params"]["page"] == "2"
            assert call_args[1]["params"]["size"] == "2"

            # Total from X-Total-Count header, items are what registry returned
            assert result.total == 5
            assert len(result.items) == 2
            assert result.items[0].entrypoint == "fw2"
            assert result.items[1].entrypoint == "fw3"

    @staticmethod
    async def test_registry_error_propagates():
        """Non-2xx from registry raises AgentServiceError."""
        from app.services.thirdparty_agent_service import (
            AgentServiceError, ThirdpartyAgentService, ListInstallersParams)

        mock_resp = MagicMock(status_code=500, text="internal error")
        mock_resp.json.return_value = []

        with patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock
        ) as mock_get, patch(
            "app.services.thirdparty_agent_service.settings"
        ) as mock_settings:
            mock_settings.AGENT_REGISTER_URL = "http://registry"
            mock_get.return_value = mock_resp

            with pytest.raises(AgentServiceError) as exc:
                await ThirdpartyAgentService.list_installers(
                    AsyncMock(),
                    ListInstallersParams(uploaded_by="admin"),
                )
            assert "500" in str(exc.value)

    @staticmethod
    async def test_enriches_with_local_registration():
        """Registry images are enriched with agent_name/display_name from local DB."""
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, ListInstallersParams,
        )
        from app.models.thirdparty_agent import AgentRegistration

        mock_images = [
            {"framework": "opencode", "framework_version": "1.0.0"},
        ]
        mock_resp = MagicMock(status_code=200, headers={})
        mock_resp.json.return_value = mock_images

        mock_reg = AgentRegistration(
            framework="opencode", framework_version="1.0.0",
            installer_path="/tmp/opencode-1.0.0.tgz",
            agent_name="opencode", display_name="OpenCode",
        )

        with patch(
            "app.services.thirdparty_agent_service.AgentRegistration"
        ) as mock_reg_cls, patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock
        ) as mock_get, patch(
            "app.services.thirdparty_agent_service.settings"
        ) as mock_settings:
            mock_settings.AGENT_REGISTER_URL = "http://registry"
            mock_get.return_value = mock_resp
            mock_reg_cls.get = AsyncMock(return_value=mock_reg)

            result = await ThirdpartyAgentService.list_installers(
                AsyncMock(),
                ListInstallersParams(uploaded_by="admin"),
            )

            assert result.total == 1
            item = result.items[0]
            assert item.agent_name == "opencode"
            assert item.display_name == "OpenCode"
            assert item.version == "1.0.0"
            assert item.entrypoint == "opencode"

    @staticmethod
    async def test_default_size_pagination():
        """Default size=20 is forwarded; registry returns page 1 with total count."""
        from app.services.thirdparty_agent_service import (
            ThirdpartyAgentService, ListInstallersParams,
        )

        # 25 items total, registry returns first 20 for page 1
        mock_images = [{"framework": f"fw{i}", "framework_version": "1.0"} for i in range(20)]
        mock_headers = {"X-Total-Count": "25"}
        mock_resp = MagicMock(status_code=200, headers=mock_headers)
        mock_resp.json.return_value = mock_images

        with patch(
            "app.services.thirdparty_agent_service.AgentRegistration"
        ) as mock_reg, patch(
            "httpx.AsyncClient.get", new_callable=AsyncMock
        ) as mock_get, patch(
            "app.services.thirdparty_agent_service.settings"
        ) as mock_settings:
            mock_settings.AGENT_REGISTER_URL = "http://registry"
            mock_get.return_value = mock_resp
            mock_reg.get = AsyncMock(return_value=None)

            result = await ThirdpartyAgentService.list_installers(
                AsyncMock(),
                ListInstallersParams(uploaded_by="admin"),
            )

            # Default page=1, size=20 forwarded
            call_args = mock_get.call_args
            assert call_args is not None
            assert call_args[1]["params"]["page"] == "1"
            assert call_args[1]["params"]["size"] == "20"

            assert result.total == 25
            assert len(result.items) == 20  # page 1
