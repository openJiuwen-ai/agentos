"""Hardware monitoring API endpoint tests."""

from unittest.mock import AsyncMock, patch

import pytest

from app.main import app
from app.schemas.hardware import (
    CpuInfo,
    DiskInfo,
    DiskIoInfo,
    HardwareNodeSummary,
    HardwareNodesData,
    HardwareSnapshot,
    MemoryInfo,
    NetworkInfo,
    NodeSnapshotData,
    SystemInfo,
)


MOCK_SNAPSHOT = HardwareSnapshot(
    system=SystemInfo(
        hostname="test-host",
        product_name="Test-Device",
        uptime_seconds=12345.0,
        boot_time="2026-07-20T08:30:00+00:00",
    ),
    cpu=CpuInfo(usage=35.2, cores=16, model_name="Intel i7-10700K"),
    memory=MemoryInfo(
        total_bytes=34359738368,
        available_bytes=21474836480,
        used_bytes=12884901888,
        usage=37.5,
        swap_total_bytes=8589934592,
        swap_free_bytes=8589934592,
        swap_usage=0.0,
    ),
    disks=[
        DiskInfo(
            mount_point="/",
            device="/dev/sda1",
            fstype="ext4",
            total_bytes=536870912000,
            used_bytes=214748364800,
            usage=40.0,
        ),
        DiskInfo(
            mount_point="all",
            device="",
            fstype="",
            total_bytes=536870912000,
            used_bytes=214748364800,
            usage=40.0,
        ),
    ],
    disk_io=[
        DiskIoInfo(
            device="sda",
            read_bytes_per_sec=1000000,
            write_bytes_per_sec=500000,
            read_count_per_sec=100,
            write_count_per_sec=50,
        ),
        DiskIoInfo(
            device="all",
            read_bytes_per_sec=1000000,
            write_bytes_per_sec=500000,
            read_count_per_sec=100,
            write_count_per_sec=50,
        ),
    ],
    network=[
        NetworkInfo(
            interface="eth0",
            rx_bytes_per_sec=5000,
            rx_packets_per_sec=20,
            tx_bytes_per_sec=3000,
            tx_packets_per_sec=15,
        ),
        NetworkInfo(
            interface="all",
            rx_bytes_per_sec=5000,
            rx_packets_per_sec=20,
            tx_bytes_per_sec=3000,
            tx_packets_per_sec=15,
        ),
    ],
    npus=[],
    timestamp="2026-07-20T12:00:00+00:00",
)

MOCK_NODES = HardwareNodesData(
    nodes=[
        HardwareNodeSummary(
            id="master",
            role="Master",
            host="192.168.1.10",
            product_name="KunLun G2280",
            status="online",
            error=None,
        )
    ],
    timestamp="2026-07-20T12:00:00+00:00",
)


@pytest.fixture
def hw_state():
    """Inject mocked HardwareService into app.state."""
    hw_svc = AsyncMock()
    hw_svc.list_nodes.return_value = MOCK_NODES
    hw_svc.get_node_snapshot.return_value = NodeSnapshotData(
        node="master",
        status="online",
        error=None,
        snapshot=MOCK_SNAPSHOT,
    )

    app.state.hardware_svc = hw_svc
    yield hw_svc
    if hasattr(app.state, "hardware_svc"):
        del app.state.hardware_svc


@pytest.mark.asyncio
async def test_hardware_nodes_no_token(client, hw_state):
    resp = await client.get("/api/v1/hardware/nodes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_hardware_snapshot_no_token(client, hw_state):
    resp = await client.get("/api/v1/hardware/snapshot", params={"node": "master"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_hardware_snapshot_non_admin(client, test_data, hw_state):
    admin_token = await _get_admin_token(client, test_data)
    cresp = await client.post(
        "/api/v1/users/batch",
        json={"usernames": ["hw_test_user"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_pw = cresp.json()["data"][0]["password"]

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "hw_test_user", "password": user_pw},
    )
    user_token = login_resp.json()["data"]["access_token"]

    resp = await client.get(
        "/api/v1/hardware/snapshot",
        params={"node": "master"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_hardware_nodes_admin(client, admin_tokens, hw_state):
    resp = await client.get(
        "/api/v1/hardware/nodes",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "master"
    assert data["nodes"][0]["role"] == "Master"
    assert data["nodes"][0]["product_name"] == "KunLun G2280"
    assert data["nodes"][0]["error"] is None


@pytest.mark.asyncio
async def test_hardware_snapshot_admin(client, admin_tokens, hw_state):
    resp = await client.get(
        "/api/v1/hardware/snapshot",
        params={"node": "master"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["node"] == "master"
    assert data["status"] == "online"
    assert data["error"] is None
    snapshot = data["snapshot"]
    assert snapshot["system"]["hostname"] == "test-host"
    assert snapshot["cpu"]["usage"] == 35.2
    assert "T" in snapshot["timestamp"]


@pytest.mark.asyncio
async def test_hardware_snapshot_unknown_node(client, admin_tokens, hw_state):
    with patch("app.config.settings") as mock_settings:
        mock_settings.allowed_node_ids = {"master"}
        resp = await client.get(
            "/api/v1/hardware/snapshot",
            params={"node": "worker-99"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_hardware_snapshot_offline(client, admin_tokens, hw_state):
    hw_state.get_node_snapshot.return_value = NodeSnapshotData(
        node="worker-1",
        status="offline",
        error="exporter unreachable",
        snapshot=None,
    )

    with patch("app.config.settings") as mock_settings:
        mock_settings.allowed_node_ids = {"master", "worker-1"}
        mock_settings.resolve_node.return_value = object()
        resp = await client.get(
            "/api/v1/hardware/snapshot",
            params={"node": "worker-1"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "offline"
    assert data["snapshot"] is None
    assert data["error"] == "exporter unreachable"


async def _get_admin_token(client, test_data):
    admin = test_data["admin"]
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": admin["username"], "password": admin["password"]},
    )
    return resp.json()["data"]["access_token"]
