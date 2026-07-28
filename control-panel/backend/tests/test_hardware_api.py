"""Hardware monitoring API endpoint tests.

Tests permission checks (401 unauthenticated, 403 non-admin, 200 admin).
The client fixture does NOT run the lifespan, so app.state services are not set.
We inject mocked services into app.state before each test that needs them.
"""

from unittest.mock import AsyncMock

import pytest

from app.main import app
from app.schemas.hardware import (
    HardwareSnapshot, SystemInfo, CpuInfo, MemoryInfo, DiskInfo, DiskIoInfo, NetworkInfo, NpuInfo,
)


MOCK_SNAPSHOT = HardwareSnapshot(
    system=SystemInfo(
        hostname="test-host", product_name="Test-Device",
        uptime_seconds=12345.0, boot_time="2026-07-20T08:30:00+00:00",
    ),
    cpu=CpuInfo(usage=35.2, cores=16, model_name="Intel i7-10700K"),
    memory=MemoryInfo(
        total_bytes=34359738368, available_bytes=21474836480, used_bytes=12884901888,
        usage=37.5, swap_total_bytes=8589934592, swap_free_bytes=8589934592, swap_usage=0.0,
    ),
    disks=[
        DiskInfo(mount_point="/", device="/dev/sda1", fstype="ext4",
                 total_bytes=536870912000, used_bytes=214748364800, usage=40.0),
        DiskInfo(mount_point="all", device="", fstype="",
                 total_bytes=536870912000, used_bytes=214748364800, usage=40.0),
    ],
    disk_io=[
        DiskIoInfo(device="sda", read_bytes_per_sec=1000000, write_bytes_per_sec=500000,
                   read_count_per_sec=100, write_count_per_sec=50),
        DiskIoInfo(device="all", read_bytes_per_sec=1000000, write_bytes_per_sec=500000,
                   read_count_per_sec=100, write_count_per_sec=50),
    ],
    network=[
        NetworkInfo(interface="eth0", rx_bytes_per_sec=5000, rx_packets_per_sec=20,
                    tx_bytes_per_sec=3000, tx_packets_per_sec=15),
        NetworkInfo(interface="all", rx_bytes_per_sec=5000, rx_packets_per_sec=20,
                    tx_bytes_per_sec=3000, tx_packets_per_sec=15),
    ],
    npus=[],
    timestamp="2026-07-20T12:00:00+00:00",
)


@pytest.fixture
def hw_state():
    """Inject mocked services into app.state, clean up after test."""
    hw_svc = AsyncMock()
    hw_svc.get_snapshot.return_value = MOCK_SNAPSHOT
    npu_monitor = AsyncMock()
    npu_monitor.get_npu_info.return_value = []

    app.state.hardware_svc = hw_svc
    app.state.npu_monitor = npu_monitor

    yield hw_svc, npu_monitor

    if hasattr(app.state, "hardware_svc"):
        del app.state.hardware_svc
    if hasattr(app.state, "npu_monitor"):
        del app.state.npu_monitor


@pytest.mark.asyncio
async def test_hardware_snapshot_no_token(client, hw_state):
    """未登录 → 401。"""
    resp = await client.get("/api/v1/hardware/snapshot")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_hardware_snapshot_non_admin(client, test_data, hw_state):
    """非 admin 用户（无 HARDWARE:READ）→ 403。"""
    admin_token = await _get_admin_token(client, test_data)
    cresp = await client.post("/api/v1/users/batch", json={
        "usernames": ["hw_test_user"],
    }, headers={"Authorization": f"Bearer {admin_token}"})
    user_pw = cresp.json()["data"][0]["password"]

    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "hw_test_user", "password": user_pw,
    })
    user_token = login_resp.json()["data"]["access_token"]

    resp = await client.get("/api/v1/hardware/snapshot", headers={
        "Authorization": f"Bearer {user_token}",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_hardware_snapshot_admin(client, admin_tokens, hw_state):
    """admin 用户 → 200，返回硬件快照数据。"""
    resp = await client.get("/api/v1/hardware/snapshot", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["message"] == "success"

    hw = data["data"]
    assert hw["system"]["hostname"] == "test-host"
    assert hw["cpu"]["usage"] == 35.2
    assert hw["cpu"]["cores"] == 16
    assert hw["memory"]["usage"] == 37.5
    assert len(hw["disks"]) == 2
    assert len(hw["network"]) == 2
    assert hw["npus"] == []
    assert "T" in hw["timestamp"]


@pytest.mark.asyncio
async def test_hardware_snapshot_with_npus(client, admin_tokens):
    """admin + NPU 可用 → 返回 NPU 数据。"""
    npu_data = [
        NpuInfo(device_id="0", usage=75.5, hbm_used_mb=17179869184,
                hbm_total_mb=34359738368, hbm_usage=50.0,
                temperature=65.0, power_watts=150.5, health=1),
        NpuInfo(device_id="all", usage=75.5, hbm_used_mb=17179869184,
                hbm_total_mb=34359738368, hbm_usage=50.0,
                temperature=65.0, power_watts=150.5, health=1),
    ]
    mock_npu = AsyncMock()
    mock_npu.get_npu_info.return_value = npu_data

    hw_svc = AsyncMock()
    hw_svc.get_snapshot.return_value = MOCK_SNAPSHOT
    app.state.hardware_svc = hw_svc
    app.state.npu_monitor = mock_npu

    try:
        resp = await client.get("/api/v1/hardware/snapshot", headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["npus"]) == 2
        assert data["npus"][0]["device_id"] == "0"
        assert data["npus"][0]["usage"] == 75.5
        assert data["npus"][1]["device_id"] == "all"
    finally:
        if hasattr(app.state, "hardware_svc"):
            del app.state.hardware_svc
        if hasattr(app.state, "npu_monitor"):
            del app.state.npu_monitor


@pytest.mark.asyncio
async def test_hardware_snapshot_npu_unreachable(client, admin_tokens, hw_state):
    """NPU 不可达 → npus 返回空列表，不影响其他数据。"""
    resp = await client.get("/api/v1/hardware/snapshot", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["npus"] == []
    assert data["cpu"]["usage"] == 35.2


async def _get_admin_token(client, test_data):
    """Helper: get admin access token."""
    admin = test_data["admin"]
    resp = await client.post("/api/v1/auth/login", json={
        "username": admin["username"], "password": admin["password"],
    })
    return resp.json()["data"]["access_token"]
