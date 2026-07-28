"""Hardware monitoring Pydantic model tests."""

import pytest
from app.schemas.hardware import (
    CpuInfo,
    DiskInfo,
    DiskIoInfo,
    HardwareSnapshot,
    MemoryInfo,
    NetworkInfo,
    NpuInfo,
    SystemInfo,
)


class TestSystemInfo:
    @staticmethod
    def test_valid_system_info():
        info = SystemInfo(
            hostname="test-host",
            product_name="Atlas-800T-A3",
            uptime_seconds=12345.0,
            boot_time="2026-07-20T08:30:00+00:00",
        )
        assert info.hostname == "test-host"
        assert info.product_name == "Atlas-800T-A3"
        assert info.uptime_seconds == 12345.0

    @staticmethod
    def test_missing_field_raises():
        with pytest.raises(Exception):
            SystemInfo(hostname="host")  # type: ignore


class TestCpuInfo:
    @staticmethod
    def test_valid_cpu_info():
        info = CpuInfo(usage=35.2, cores=16, model_name="Intel i7")
        assert info.usage == 35.2
        assert info.cores == 16

    @staticmethod
    def test_zero_usage():
        info = CpuInfo(usage=0.0, cores=1, model_name="CPU")
        assert info.usage == 0.0

    @staticmethod
    def test_full_usage():
        info = CpuInfo(usage=100.0, cores=8, model_name="CPU")
        assert info.usage == 100.0


class TestMemoryInfo:
    @staticmethod
    def test_valid_memory_info():
        info = MemoryInfo(
            total_bytes=34359738368,
            available_bytes=21474836480,
            used_bytes=12884901888,
            usage=37.5,
            swap_total_bytes=8589934592,
            swap_free_bytes=8589934592,
            swap_usage=0.0,
        )
        assert info.total_bytes == 34359738368
        assert info.usage == 37.5
        assert info.swap_usage == 0.0

    @staticmethod
    def test_no_swap():
        info = MemoryInfo(
            total_bytes=1000000000,
            available_bytes=500000000,
            used_bytes=500000000,
            usage=50.0,
            swap_total_bytes=0,
            swap_free_bytes=0,
            swap_usage=0.0,
        )
        assert info.swap_total_bytes == 0
        assert info.swap_usage == 0.0


class TestDiskInfo:
    @staticmethod
    def test_valid_disk_info():
        info = DiskInfo(
            mount_point="/",
            device="/dev/sda1",
            fstype="ext4",
            total_bytes=536870912000,
            used_bytes=214748364800,
            usage=40.0,
        )
        assert info.mount_point == "/"
        assert info.usage == 40.0

    @staticmethod
    def test_all_summary():
        info = DiskInfo(
            mount_point="all",
            device="",
            fstype="",
            total_bytes=1000000000000,
            used_bytes=300000000000,
            usage=30.0,
        )
        assert info.mount_point == "all"
        assert info.device == ""


class TestNetworkInfo:
    @staticmethod
    def test_valid_network_info():
        info = NetworkInfo(
            interface="eth0",
            rx_bytes_per_sec=5000,
            rx_packets_per_sec=20,
            tx_bytes_per_sec=3000,
            tx_packets_per_sec=15,
        )
        assert info.interface == "eth0"
        assert info.rx_bytes_per_sec == 5000

    @staticmethod
    def test_all_summary():
        info = NetworkInfo(
            interface="all",
            rx_bytes_per_sec=13000,
            rx_packets_per_sec=55,
            tx_bytes_per_sec=5000,
            tx_packets_per_sec=25,
        )
        assert info.interface == "all"

    @staticmethod
    def test_zero_rates():
        info = NetworkInfo(
            interface="eth0",
            rx_bytes_per_sec=0,
            rx_packets_per_sec=0,
            tx_bytes_per_sec=0,
            tx_packets_per_sec=0,
        )
        assert info.rx_bytes_per_sec == 0


class TestNpuInfo:
    @staticmethod
    def test_valid_npu_info():
        info = NpuInfo(
            device_id="0",
            usage=75.5,
            hbm_used_mb=17179869184,
            hbm_total_mb=34359738368,
            hbm_usage=50.0,
            temperature=65.0,
            power_watts=150.5,
            health=1,
        )
        assert info.device_id == "0"
        assert info.usage == 75.5
        assert info.temperature == 65.0
        assert info.health == 1

    @staticmethod
    def test_unhealthy_npu():
        info = NpuInfo(
            device_id="1",
            usage=0.0,
            hbm_used_mb=0,
            hbm_total_mb=34359738368,
            hbm_usage=0.0,
            temperature=0.0,
            power_watts=0.0,
            health=0,
        )
        assert info.health == 0

    @staticmethod
    def test_all_summary():
        info = NpuInfo(
            device_id="all",
            usage=68.9,
            hbm_used_mb=30064771072,
            hbm_total_mb=68719476736,
            hbm_usage=43.75,
            temperature=65.0,
            power_watts=270.5,
            health=1,
        )
        assert info.device_id == "all"

    @staticmethod
    def test_defaults():
        info = NpuInfo(
            device_id="0",
            usage=50.0,
            hbm_used_mb=0,
            hbm_total_mb=1,
            hbm_usage=0.0,
            temperature=40.0,
            power_watts=100.0,
        )
        assert info.health == 1


class TestDiskIoInfo:
    @staticmethod
    def test_valid_disk_io():
        info = DiskIoInfo(
            device="sda",
            read_bytes_per_sec=1000000,
            write_bytes_per_sec=500000,
            read_count_per_sec=100,
            write_count_per_sec=50,
        )
        assert info.device == "sda"
        assert info.read_bytes_per_sec == 1000000

    @staticmethod
    def test_all_summary():
        info = DiskIoInfo(
            device="all",
            read_bytes_per_sec=2000000,
            write_bytes_per_sec=1000000,
            read_count_per_sec=200,
            write_count_per_sec=100,
        )
        assert info.device == "all"


class TestHardwareSnapshot:
    @staticmethod
    def test_full_snapshot():
        snapshot = HardwareSnapshot(
            system=SystemInfo(
                hostname="host", product_name="Test-Device",
                uptime_seconds=100, boot_time="2026-01-01T00:00:00Z",
            ),
            cpu=CpuInfo(usage=50.0, cores=8, model_name="CPU"),
            memory=MemoryInfo(
                total_bytes=1000000, available_bytes=500000, used_bytes=500000,
                usage=50.0, swap_total_bytes=0, swap_free_bytes=0, swap_usage=0.0,
            ),
            disks=[],
            disk_io=[],
            network=[],
            npus=[],
            timestamp="2026-07-20T12:00:00Z",
        )
        assert snapshot.system.hostname == "host"
        assert snapshot.cpu.usage == 50.0
        assert snapshot.disks == []
        assert snapshot.disk_io == []
        assert snapshot.npus == []

    @staticmethod
    def test_snapshot_with_npus():
        snapshot = HardwareSnapshot(
            system=SystemInfo(
                hostname="host", product_name="Test-Device",
                uptime_seconds=100, boot_time="2026-01-01T00:00:00Z",
            ),
            cpu=CpuInfo(usage=50.0, cores=8, model_name="CPU"),
            memory=MemoryInfo(
                total_bytes=1000000, available_bytes=500000, used_bytes=500000,
                usage=50.0, swap_total_bytes=0, swap_free_bytes=0, swap_usage=0.0,
            ),
            disks=[
                DiskInfo(mount_point="/", device="/dev/sda1", fstype="ext4",
                         total_bytes=100, used_bytes=50, usage=50.0),
            ],
            disk_io=[
                DiskIoInfo(device="sda", read_bytes_per_sec=100,
                           write_bytes_per_sec=50, read_count_per_sec=10,
                           write_count_per_sec=5),
            ],
            network=[
                NetworkInfo(interface="eth0", rx_bytes_per_sec=100,
                            rx_packets_per_sec=1, tx_bytes_per_sec=50,
                            tx_packets_per_sec=1),
            ],
            npus=[
                NpuInfo(device_id="0", usage=75.0, hbm_used_mb=1000,
                        hbm_total_mb=2000, hbm_usage=50.0,
                        temperature=65.0, power_watts=150.0),
            ],
            timestamp="2026-07-20T12:00:00Z",
        )
        assert len(snapshot.disks) == 1
        assert len(snapshot.disk_io) == 1
        assert len(snapshot.network) == 1
        assert len(snapshot.npus) == 1
