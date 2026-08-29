"""Unit tests for thirdparty_agent schemas and card listing."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.thirdparty_agent import AgentRegistration
from app.schemas.thirdparty_agent import CardDetail, PublishAccepted
from app.services.agent_register_client import AgentRegisterError
from app.services.thirdparty_agent_service import (
    ThirdpartyAgentService,
    _semantic_version_key,
)
from app.thirdparty_agent.card_view import CardViewProjector


@pytest.fixture(autouse=True)
def _mock_local_card_store():
    with (
        patch.object(AgentRegistration, "list_all", AsyncMock(return_value=[])),
        patch.object(AgentRegistration, "get", AsyncMock(return_value=None)),
        patch.object(AgentRegistration, "delete_by_key", AsyncMock()),
    ):
        yield


def test_publish_accepted_fields():
    r = PublishAccepted(digest="abc", request_id="build-1")
    assert r.digest == "abc"


def test_card_detail_optional_paths():
    d = CardDetail(framework="demo", framework_version="1.0")
    assert d.package_path is None


def test_projector_user_strips_paths():
    p = CardViewProjector()
    dto = p.for_user(
        {
            "framework": "demo",
            "framework_version": "1.0",
            "package_path": "/secret.tgz",
        }
    )
    assert "package_path" not in dto
    assert "description" not in dto
    assert dto["is_default"] is False


def test_projector_admin_counts_and_paths():
    p = CardViewProjector()
    dto = p.for_admin(
        {"framework": "demo", "framework_version": "1.0", "package_path": "/p"},
        total_count=2,
        running_count=1,
        include_paths=True,
    )
    assert dto["total_instances"] == 2
    assert dto["running_instances"] == 1
    assert dto["package_path"] == "/p"
    assert dto["is_default"] is False


def test_projector_keeps_default_flag():
    p = CardViewProjector()
    dto = p.for_user(
        {"framework": "demo", "framework_version": "2.0", "is_default": True}
    )
    assert dto["is_default"] is True


@pytest.mark.asyncio
async def test_list_cards_user_view():
    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [{"framework": "demo", "framework_version": "1.0", "package_path": "/p"}],
            1,
        )
    )
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    result = await svc.list_cards(AsyncMock(), is_admin=False)
    assert result.total == 1
    assert "package_path" not in result.items[0]
    registry.list_instances.assert_not_called()


@pytest.mark.asyncio
async def test_list_cards_merges_local_metadata_without_hiding_registry_card():
    registry = AsyncMock()
    registry.list_images.return_value = (
        [
            {
                "framework": "demo",
                "framework_version": "1.0",
            }
        ],
        1,
    )
    local = AgentRegistration(
        framework="demo",
        framework_version="1.0",
        installer_path="/local/demo.tgz",
        agent_name="demo-agent",
        display_name="Local description",
    )
    with patch.object(AgentRegistration, "list_all", AsyncMock(return_value=[local])):
        result = await ThirdpartyAgentService(
            factory=AsyncMock(),
            registry=registry,
        ).list_cards(AsyncMock(), is_admin=True)
    assert "description" not in result.items[0]
    assert result.items[0]["framework"] == "demo"


@pytest.mark.asyncio
async def test_list_cards_admin_adds_counts():
    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [{"framework": "demo", "framework_version": "1.0"}],
            1,
        )
    )
    registry.list_instances = AsyncMock(
        return_value=[
            {"framework": "demo", "framework_version": "1.0", "status": "运行"},
            {"framework": "demo", "framework_version": "1.0", "status": "停止"},
        ]
    )
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    result = await svc.list_cards(AsyncMock(), is_admin=True)
    assert result.items[0]["total_instances"] == 2
    assert result.items[0]["running_instances"] == 1


@pytest.mark.asyncio
async def test_delete_card_allows_idle_default_last_version():
    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [
                {
                    "framework": "demo",
                    "framework_version": "1.0",
                    "is_default": True,
                    "imageurl": "demo:1",
                    "package_path": "",
                    "image_archive_path": "",
                }
            ],
            1,
        )
    )
    registry.list_instances = AsyncMock(return_value=[])
    factory = AsyncMock()
    svc = ThirdpartyAgentService(factory=factory, registry=registry)
    await svc.delete_card(AsyncMock(), "demo", "1.0")
    registry.set_default_version.assert_not_called()
    registry.delete_image.assert_awaited_once_with("demo", "1.0")


@pytest.mark.asyncio
async def test_delete_card_promotes_sibling_when_deleting_default():
    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [
                {
                    "framework": "demo",
                    "framework_version": "1.0",
                    "is_default": True,
                    "imageurl": "demo:1",
                    "package_path": "",
                    "image_archive_path": "",
                },
                {"framework": "demo", "framework_version": "2.0", "is_default": False},
            ],
            2,
        )
    )
    registry.list_instances = AsyncMock(return_value=[])
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    await svc.delete_card(AsyncMock(), "demo", "1.0")
    registry.set_default_version.assert_awaited_once_with("demo", "2.0")
    registry.delete_image.assert_awaited_once_with("demo", "1.0")


@pytest.mark.asyncio
async def test_delete_card_promotes_highest_semantic_version():
    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [
                {"framework": "demo", "framework_version": "1.0.0", "is_default": True},
                {
                    "framework": "demo",
                    "framework_version": "2.9.0",
                    "is_default": False,
                },
                {
                    "framework": "demo",
                    "framework_version": "2.10.0-rc.1",
                    "is_default": False,
                },
                {
                    "framework": "demo",
                    "framework_version": "2.10.0",
                    "is_default": False,
                },
            ],
            4,
        )
    )
    registry.list_instances = AsyncMock(return_value=[])
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    await svc.delete_card(AsyncMock(), "demo", "1.0.0")
    registry.set_default_version.assert_awaited_once_with("demo", "2.10.0")


def test_semantic_version_key_supports_common_version_forms():
    versions = ["2.9.0", "2.10.0-rc.2", "2.10.0-rc.10", "2.10.0+build.7"]
    assert max(versions, key=_semantic_version_key) == "2.10.0+build.7"
    assert _semantic_version_key("v2.10") == _semantic_version_key("2.10.0+build.7")


@pytest.mark.asyncio
async def test_delete_card_refuses_when_instances():
    from app.thirdparty_agent.exceptions import CardHasInstancesError

    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [
                {
                    "framework": "demo",
                    "framework_version": "1.0",
                    "is_default": True,
                    "imageurl": "demo:1",
                }
            ],
            1,
        )
    )
    registry.list_instances = AsyncMock(return_value=[{"service_id": "s1"}])
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    with pytest.raises(CardHasInstancesError):
        await svc.delete_card(AsyncMock(), "demo", "1.0")
    registry.delete_image.assert_not_called()


@pytest.mark.asyncio
async def test_delete_card_refuses_when_instance_query_fails():
    from app.thirdparty_agent.exceptions import AgentServiceError

    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [{"framework": "demo", "framework_version": "1.0", "is_default": True}],
            1,
        )
    )
    registry.list_instances = AsyncMock(side_effect=AgentRegisterError("unavailable"))
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    with pytest.raises(AgentServiceError, match="agent registry unavailable"):
        await svc.delete_card(AsyncMock(), "demo", "1.0")
    registry.delete_image.assert_not_called()


@pytest.mark.asyncio
async def test_get_card_maps_registry_failure_to_service_error():
    from app.thirdparty_agent.exceptions import AgentServiceError

    registry = AsyncMock()
    registry.list_images = AsyncMock(side_effect=AgentRegisterError("unavailable"))
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    with pytest.raises(AgentServiceError, match="agent registry unavailable"):
        await svc.get_card(AsyncMock(), is_admin=True, framework="demo", version="1.0")


@pytest.mark.asyncio
async def test_delete_card_cleans_and_unregisters():
    registry = AsyncMock()
    registry.list_images = AsyncMock(
        return_value=(
            [
                {
                    "framework": "demo",
                    "framework_version": "1.0",
                    "imageurl": "demo:1",
                    "package_path": "",
                    "image_archive_path": "",
                }
            ],
            1,
        )
    )
    registry.list_instances = AsyncMock(return_value=[])
    factory = AsyncMock()
    factory.remove_loaded_image = AsyncMock()
    svc = ThirdpartyAgentService(factory=factory, registry=registry)
    await svc.delete_card(AsyncMock(), "demo", "1.0")
    factory.remove_loaded_image.assert_awaited_once_with("demo:1")
    registry.delete_image.assert_awaited_once_with("demo", "1.0")


@pytest.mark.asyncio
async def test_delete_card_reads_nested_registry_image_tag():
    registry = AsyncMock()
    registry.list_images.return_value = (
        [
            {
                "framework": "demo",
                "framework_version": "1.0",
                "runtime_spec": {"rootfs": {"imageurl": "demo:1.0"}},
            }
        ],
        1,
    )
    registry.list_instances.return_value = []
    factory = AsyncMock()
    await ThirdpartyAgentService(factory=factory, registry=registry).delete_card(
        AsyncMock(),
        "demo",
        "1.0",
    )
    factory.remove_loaded_image.assert_awaited_once_with("demo:1.0")


@pytest.mark.asyncio
async def test_set_default_version():
    registry = AsyncMock()
    svc = ThirdpartyAgentService(factory=AsyncMock(), registry=registry)
    await svc.set_default_version("demo", "2.0")
    registry.set_default_version.assert_awaited_once_with("demo", "2.0")
