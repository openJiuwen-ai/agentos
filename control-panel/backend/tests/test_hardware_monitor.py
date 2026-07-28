"""HardwareMonitorService unit tests — mocked node_exporter metrics."""

import asyncio
import math
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.services.hardware_monitor import HardwareMonitorService, _parse_prometheus
from app.schemas.hardware import CpuInfo, DiskInfo, DiskIoInfo, MemoryInfo, NetworkInfo, SystemInfo


# ── Prometheus 解析测试 ─────────────────────────────────────────────────────

class TestParsePrometheus:
    @staticmethod
    def test_parse_simple_metric():
        text = "node_boot_time_seconds 1700000000"
        result = _parse_prometheus(text)
        assert "node_boot_time_seconds" in result
        assert len(result["node_boot_time_seconds"]) == 1
        labels, value = result["node_boot_time_seconds"][0]
        assert labels == {}
        assert value == 1700000000.0

    @staticmethod
    def test_parse_metric_with_labels():
        text = 'node_cpu_seconds_total{cpu="0",mode="idle"} 12345.67'
        result = _parse_prometheus(text)
        assert "node_cpu_seconds_total" in result
        labels, value = result["node_cpu_seconds_total"][0]
        assert labels["cpu"] == "0"
        assert labels["mode"] == "idle"
        assert value == 12345.67

    @staticmethod
    def test_parse_multiple_labels():
        text = 'node_filesystem_size_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"} 100000000'
        result = _parse_prometheus(text)
        labels, value = result["node_filesystem_size_bytes"][0]
        assert labels["device"] == "/dev/sda1"
        assert labels["fstype"] == "ext4"
        assert labels["mountpoint"] == "/"
        assert value == 100000000.0

    @staticmethod
    def test_parse_skips_comments():
        text = "# This is a comment\nnode_boot_time_seconds 1700000000"
        result = _parse_prometheus(text)
        assert "node_boot_time_seconds" in result

    @staticmethod
    def test_parse_skips_empty_lines():
        text = "\n\nnode_boot_time_seconds 1700000000\n\n"
        result = _parse_prometheus(text)
        assert "node_boot_time_seconds" in result

    @staticmethod
    def test_parse_multiple_values_same_metric():
        text = (
            'node_cpu_seconds_total{cpu="0",mode="idle"} 1000\n'
            'node_cpu_seconds_total{cpu="0",mode="user"} 500\n'
            'node_cpu_seconds_total{cpu="1",mode="idle"} 2000\n'
        )
        result = _parse_prometheus(text)
        assert len(result["node_cpu_seconds_total"]) == 3

    @staticmethod
    def test_parse_scientific_notation():
        text = "some_metric 1.5e10"
        result = _parse_prometheus(text)
        assert result["some_metric"][0][1] == 1.5e10

    @staticmethod
    def test_parse_decimal_without_integer():
        text = "some_metric .5"
        result = _parse_prometheus(text)
        assert result["some_metric"][0][1] == 0.5

    @staticmethod
    def test_parse_nan():
        text = "some_metric NaN"
        result = _parse_prometheus(text)
        assert math.isnan(result["some_metric"][0][1])

    @staticmethod
    def test_parse_inf():
        text = "metric_pos +Inf\nmetric_neg -Inf"
        result = _parse_prometheus(text)
        assert result["metric_pos"][0][1] == float("inf")
        assert result["metric_neg"][0][1] == float("-inf")


# ── CPU 测试 ─────────────────────────────────────────────────────────────────

class TestCpuInfo:
    @staticmethod
    def test_parse_cpu_calculates_usage():
        svc = HardwareMonitorService()
        metrics1 = {
            "node_cpu_seconds_total": [
                ({"cpu": "0", "mode": "idle"}, 1000),
                ({"cpu": "0", "mode": "user"}, 500),
            ]
        }
        metrics2 = {
            "node_cpu_seconds_total": [
                ({"cpu": "0", "mode": "idle"}, 1050),  # +50 idle
                ({"cpu": "0", "mode": "user"}, 600),   # +100 user
            ]
        }
        cpu = svc.parse_cpu(metrics1, metrics2)
        # total_delta = 150, idle_delta = 50, usage = (150-50)/150 * 100 = 66.7%
        assert cpu.usage == 66.7

    @staticmethod
    def test_parse_cpu_multi_core_aggregation():
        svc = HardwareMonitorService()
        metrics1 = {
            "node_cpu_seconds_total": [
                ({"cpu": "0", "mode": "idle"}, 1000),
                ({"cpu": "1", "mode": "idle"}, 2000),
                ({"cpu": "0", "mode": "user"}, 500),
                ({"cpu": "1", "mode": "user"}, 300),
            ]
        }
        metrics2 = {
            "node_cpu_seconds_total": [
                ({"cpu": "0", "mode": "idle"}, 1050),  # +50
                ({"cpu": "1", "mode": "idle"}, 2100),  # +100
                ({"cpu": "0", "mode": "user"}, 600),   # +100
                ({"cpu": "1", "mode": "user"}, 350),   # +50
            ]
        }
        cpu = svc.parse_cpu(metrics1, metrics2)
        # total_delta = (50+100+100+50) = 300, idle_delta = (50+100) = 150
        # usage = (300-150)/300 * 100 = 50.0%
        assert cpu.usage == 50.0

    @staticmethod
    def test_parse_cpu_zero_delta():
        svc = HardwareMonitorService()
        metrics = {
            "node_cpu_seconds_total": [
                ({"cpu": "0", "mode": "idle"}, 1000),
                ({"cpu": "0", "mode": "user"}, 500),
            ]
        }
        cpu = svc.parse_cpu(metrics, metrics)
        # No change between snapshots
        assert cpu.usage == 0.0

    @staticmethod
    def test_parse_cpu_empty_metrics():
        svc = HardwareMonitorService()
        cpu = svc.parse_cpu({}, {})
        assert cpu.cores == 0
        assert cpu.usage == 0.0


# ── Memory 测试 ──────────────────────────────────────────────────────────────

class TestMemoryInfo:
    @staticmethod
    def test_parse_memory():
        svc = HardwareMonitorService()
        metrics = {
            "node_memory_MemTotal_bytes": [({}, 16000000000)],
            "node_memory_MemAvailable_bytes": [({}, 8000000000)],
            "node_memory_SwapTotal_bytes": [({}, 4000000000)],
            "node_memory_SwapFree_bytes": [({}, 2000000000)],
        }
        mem = svc.parse_memory(metrics)
        assert mem.total_bytes == 16000000000
        assert mem.available_bytes == 8000000000
        assert mem.used_bytes == 8000000000
        assert mem.usage == 50.0
        assert mem.swap_total_bytes == 4000000000
        assert mem.swap_free_bytes == 2000000000
        assert mem.swap_usage == 50.0

    @staticmethod
    def test_parse_memory_no_swap():
        svc = HardwareMonitorService()
        metrics = {
            "node_memory_MemTotal_bytes": [({}, 8000000000)],
            "node_memory_MemAvailable_bytes": [({}, 4000000000)],
            "node_memory_SwapTotal_bytes": [({}, 0)],
            "node_memory_SwapFree_bytes": [({}, 0)],
        }
        mem = svc.parse_memory(metrics)
        assert mem.swap_total_bytes == 0
        assert mem.swap_usage == 0.0

    @staticmethod
    def test_parse_memory_empty_metrics():
        svc = HardwareMonitorService()
        metrics = {}
        mem = svc.parse_memory(metrics)
        assert mem.total_bytes == 0
        assert mem.usage == 0


# ── Disk 测试 ────────────────────────────────────────────────────────────────

class TestDiskInfo:
    @staticmethod
    def test_parse_disk():
        svc = HardwareMonitorService()
        metrics = {
            "node_filesystem_size_bytes": [
                ({"device": "/dev/sda1", "fstype": "ext4", "mountpoint": "/"}, 100000000000),
                ({"device": "/dev/sdb1", "fstype": "xfs", "mountpoint": "/data"}, 200000000000),
            ],
            "node_filesystem_avail_bytes": [
                ({"device": "/dev/sda1", "fstype": "ext4", "mountpoint": "/"}, 60000000000),
                ({"device": "/dev/sdb1", "fstype": "xfs", "mountpoint": "/data"}, 140000000000),
            ],
        }
        disks = svc.parse_disk(metrics)
        assert len(disks) == 3  # 2 disks + 1 "all" summary
        assert disks[0].mount_point == "/"
        assert disks[0].usage == 40.0
        assert disks[1].mount_point == "/data"
        assert disks[1].usage == 30.0
        assert disks[2].mount_point == "all"
        assert disks[2].total_bytes == 300000000000
        assert disks[2].used_bytes == 100000000000

    @staticmethod
    def test_parse_disk_filters_non_real_fs():
        svc = HardwareMonitorService()
        metrics = {
            "node_filesystem_size_bytes": [
                ({"device": "/dev/sda1", "fstype": "ext4", "mountpoint": "/"}, 100000000000),
                ({"device": "tmpfs", "fstype": "tmpfs", "mountpoint": "/tmp"}, 1000000),
            ],
            "node_filesystem_avail_bytes": [],
        }
        disks = svc.parse_disk(metrics)
        # Should only have ext4 disk + "all" summary
        assert len(disks) == 2
        assert disks[0].fstype == "ext4"

    @staticmethod
    def test_parse_disk_filters_duplicates():
        svc = HardwareMonitorService()
        metrics = {
            "node_filesystem_size_bytes": [
                ({"device": "/dev/sda1", "fstype": "ext4", "mountpoint": "/"}, 100000000000),
                ({"device": "/dev/sda1", "fstype": "ext4", "mountpoint": "/"}, 100000000000),
            ],
            "node_filesystem_avail_bytes": [],
        }
        disks = svc.parse_disk(metrics)
        assert len(disks) == 2  # 1 unique + "all"

    @staticmethod
    def test_parse_disk_empty():
        svc = HardwareMonitorService()
        metrics = {}
        disks = svc.parse_disk(metrics)
        assert len(disks) == 1  # just "all"
        assert disks[0].mount_point == "all"
        assert disks[0].total_bytes == 0


# ── Disk IO 测试 ─────────────────────────────────────────────────────────────

class TestDiskIoInfo:
    @staticmethod
    def test_parse_disk_io_first_call_returns_zeros():
        svc = HardwareMonitorService()
        metrics = {
            "node_disk_read_bytes_total": [({"device": "sda"}, 1000000)],
            "node_disk_written_bytes_total": [({"device": "sda"}, 500000)],
            "node_disk_reads_completed_total": [({"device": "sda"}, 100)],
            "node_disk_writes_completed_total": [({"device": "sda"}, 50)],
        }
        disk_io = svc.parse_disk_io(metrics)
        assert len(disk_io) == 1  # just "all" summary
        assert disk_io[0].device == "all"
        assert disk_io[0].read_bytes_per_sec == 0
        assert disk_io[0].write_bytes_per_sec == 0

    @staticmethod
    def test_parse_disk_io_calculates_rates():
        svc = HardwareMonitorService()
        # First call - sets baseline
        metrics1 = {
            "node_disk_read_bytes_total": [({"device": "sda"}, 1000000)],
            "node_disk_written_bytes_total": [({"device": "sda"}, 500000)],
            "node_disk_reads_completed_total": [({"device": "sda"}, 100)],
            "node_disk_writes_completed_total": [({"device": "sda"}, 50)],
        }
        svc.parse_disk_io(metrics1)

        # Second call - should calculate rates
        metrics2 = {
            "node_disk_read_bytes_total": [({"device": "sda"}, 2000000)],  # +1MB
            "node_disk_written_bytes_total": [({"device": "sda"}, 1000000)],  # +500KB
            "node_disk_reads_completed_total": [({"device": "sda"}, 200)],  # +100
            "node_disk_writes_completed_total": [({"device": "sda"}, 100)],  # +50
        }
        disk_io = svc.parse_disk_io(metrics2)
        assert len(disk_io) == 2  # sda + all
        assert disk_io[0].device == "sda"
        # Rates depend on time delta, but should be non-zero
        assert disk_io[0].read_bytes_per_sec > 0


# ── Network 测试 ─────────────────────────────────────────────────────────────

class TestNetworkInfo:
    @staticmethod
    def test_parse_network_first_call_returns_zeros():
        svc = HardwareMonitorService()
        metrics = {
            "node_network_receive_bytes_total": [({"device": "eth0"}, 10000)],
            "node_network_transmit_bytes_total": [({"device": "eth0"}, 5000)],
            "node_network_receive_packets_total": [({"device": "eth0"}, 100)],
            "node_network_transmit_packets_total": [({"device": "eth0"}, 50)],
        }
        net = svc.parse_network(metrics)
        assert len(net) == 2  # eth0 + all
        assert net[0].interface == "eth0"
        assert net[0].rx_bytes_per_sec == 0
        assert net[0].tx_bytes_per_sec == 0

    @staticmethod
    def test_parse_network_calculates_rates():
        svc = HardwareMonitorService()
        # First call
        metrics1 = {
            "node_network_receive_bytes_total": [({"device": "eth0"}, 10000)],
            "node_network_transmit_bytes_total": [({"device": "eth0"}, 5000)],
            "node_network_receive_packets_total": [({"device": "eth0"}, 100)],
            "node_network_transmit_packets_total": [({"device": "eth0"}, 50)],
        }
        svc.parse_network(metrics1)

        # Second call
        metrics2 = {
            "node_network_receive_bytes_total": [({"device": "eth0"}, 15000)],  # +5000
            "node_network_transmit_bytes_total": [({"device": "eth0"}, 8000)],   # +3000
            "node_network_receive_packets_total": [({"device": "eth0"}, 150)],   # +50
            "node_network_transmit_packets_total": [({"device": "eth0"}, 80)],   # +30
        }
        net = svc.parse_network(metrics2)
        assert len(net) == 2
        assert net[0].interface == "eth0"
        # Rates depend on time delta
        assert net[0].rx_bytes_per_sec > 0

    @staticmethod
    def test_parse_network_filters_loopback():
        svc = HardwareMonitorService()
        metrics = {
            "node_network_receive_bytes_total": [
                ({"device": "lo"}, 1000000),
                ({"device": "eth0"}, 10000),
            ],
            "node_network_transmit_bytes_total": [
                ({"device": "lo"}, 1000000),
                ({"device": "eth0"}, 5000),
            ],
            "node_network_receive_packets_total": [],
            "node_network_transmit_packets_total": [],
        }
        net = svc.parse_network(metrics)
        interfaces = [n.interface for n in net]
        assert "lo" not in interfaces
        assert "eth0" in interfaces

    @staticmethod
    def test_parse_network_multiple_nics():
        svc = HardwareMonitorService()
        metrics = {
            "node_network_receive_bytes_total": [
                ({"device": "eth0"}, 10000),
                ({"device": "eth1"}, 20000),
            ],
            "node_network_transmit_bytes_total": [
                ({"device": "eth0"}, 5000),
                ({"device": "eth1"}, 8000),
            ],
            "node_network_receive_packets_total": [],
            "node_network_transmit_packets_total": [],
        }
        net = svc.parse_network(metrics)
        assert len(net) == 3  # eth0 + eth1 + all
        assert net[2].interface == "all"


# ── System Info 测试 ─────────────────────────────────────────────────────────

class TestSystemInfo:
    @staticmethod
    @patch("app.config.settings")
    @patch("app.services.hardware_monitor.time")
    def test_get_system_info(mock_time, mock_settings):
        mock_time.time.return_value = 1700001000.0
        mock_settings.AGENTOS_HOSTNAME = "test-host"
        mock_settings.AGENTOS_PRODUCT_NAME = "Test Server"
        mock_settings.node_exporter_url = "http://localhost:9090"

        svc = HardwareMonitorService()
        info = svc.get_system_info(boot_time=1700000000.0)

        assert info.hostname == "test-host"
        assert info.product_name == "Test Server"
        assert info.uptime_seconds == 1000.0
        assert "T" in info.boot_time

    @staticmethod
    @patch("app.config.settings")
    def test_get_system_info_defaults(mock_settings):
        mock_settings.AGENTOS_HOSTNAME = ""
        mock_settings.AGENTOS_PRODUCT_NAME = ""
        mock_settings.node_exporter_url = "http://localhost:9090"

        svc = HardwareMonitorService()
        with patch.object(svc, 'get_boot_time', return_value=0.0):
            info = svc.get_system_info()

        assert info.hostname == "-"
        assert info.product_name == "-"


# ── Boot Time 测试 ───────────────────────────────────────────────────────────

class TestBootTime:
    @staticmethod
    @patch("app.config.settings")
    def test_get_boot_time_from_node_exporter(mock_settings):
        mock_settings.node_exporter_url = "http://localhost:9090"
        mock_response = MagicMock()
        mock_response.text = "node_boot_time_seconds 1700000000\n"

        svc = HardwareMonitorService()
        with patch("httpx.get", return_value=mock_response):
            boot_time = svc.get_boot_time()

        assert boot_time == 1700000000.0

    @staticmethod
    @patch("app.config.settings")
    def test_get_boot_time_returns_zero_on_error(mock_settings):
        mock_settings.node_exporter_url = "http://localhost:9090"

        svc = HardwareMonitorService()
        with patch("httpx.get", side_effect=ConnectionError("Connection refused")):
            boot_time = svc.get_boot_time()

        assert boot_time == 0.0

    @staticmethod
    def test_extract_boot_time_from_metrics():
        metrics = {
            "node_boot_time_seconds": [({}, 1700000000.0)],
        }
        assert math.isclose(HardwareMonitorService.extract_boot_time(metrics), 1700000000.0)

    @staticmethod
    def test_extract_boot_time_empty_metrics():
        assert math.isclose(HardwareMonitorService.extract_boot_time({}), 0.0)


# ── Snapshot 测试 ────────────────────────────────────────────────────────────

class TestGetSnapshot:
    @staticmethod
    @pytest.mark.asyncio
    @patch("app.services.hardware_monitor._IS_LINUX", True)
    @patch("app.config.settings")
    async def test_get_snapshot_linux(mock_settings):
        mock_settings.node_exporter_url = "http://localhost:9090"
        mock_settings.AGENTOS_HOSTNAME = "test-host"
        mock_settings.AGENTOS_PRODUCT_NAME = "Test Server"

        mock_response = MagicMock()
        mock_response.text = (
            'node_cpu_seconds_total{cpu="0",mode="idle"} 1000\n'
            'node_cpu_seconds_total{cpu="0",mode="user"} 500\n'
            'node_memory_MemTotal_bytes 16000000000\n'
            'node_memory_MemAvailable_bytes 8000000000\n'
            'node_filesystem_size_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"} 100000000000\n'
            'node_filesystem_avail_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"} 60000000000\n'
            'node_network_receive_bytes_total{device="eth0"} 10000\n'
            'node_network_transmit_bytes_total{device="eth0"} 5000\n'
            'node_boot_time_seconds 1700000000\n'
        )

        mock_response2 = MagicMock()
        mock_response2.text = (
            'node_cpu_seconds_total{cpu="0",mode="idle"} 1050\n'
            'node_cpu_seconds_total{cpu="0",mode="user"} 600\n'
            'node_memory_MemTotal_bytes 16000000000\n'
            'node_memory_MemAvailable_bytes 8000000000\n'
            'node_filesystem_size_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"} 100000000000\n'
            'node_filesystem_avail_bytes{device="/dev/sda1",fstype="ext4",mountpoint="/"} 60000000000\n'
            'node_network_receive_bytes_total{device="eth0"} 10000\n'
            'node_network_transmit_bytes_total{device="eth0"} 5000\n'
        )

        parsed1 = _parse_prometheus(mock_response.text)
        parsed2 = _parse_prometheus(mock_response2.text, prefix="node_cpu_seconds_total")

        svc = HardwareMonitorService()
        mock_fetch = AsyncMock(return_value=parsed1)
        mock_fetch_cpu = AsyncMock(return_value=parsed2)
        with patch.object(svc, 'fetch_metrics', mock_fetch):
            with patch.object(svc, 'fetch_cpu_metrics', mock_fetch_cpu):
                snapshot = await svc.get_snapshot()

        assert snapshot.system.hostname == "test-host"
        assert snapshot.cpu.cores == 1
        assert snapshot.cpu.usage == 66.7
        assert snapshot.memory.total_bytes == 16000000000
        assert len(snapshot.disks) == 2  # sda1 + all
        assert snapshot.npus == []
        assert "T" in snapshot.timestamp

    @staticmethod
    @pytest.mark.asyncio
    @patch("app.config.settings")
    async def test_get_snapshot_empty_on_fetch_error(mock_settings):
        mock_settings.node_exporter_url = "http://localhost:9090"
        mock_settings.AGENTOS_HOSTNAME = "test-host"
        mock_settings.AGENTOS_PRODUCT_NAME = "Test Server"

        svc = HardwareMonitorService()
        with patch.object(svc, 'fetch_metrics', return_value=None):
            snapshot = await svc.get_snapshot()

        assert snapshot.cpu.cores == 0
        assert snapshot.memory.total_bytes == 0
        assert len(snapshot.disks) == 1  # just "all"
        assert snapshot.disks[0].mount_point == "all"


# ── Windows 测试 ─────────────────────────────────────────────────────────────

class TestWindows:
    @staticmethod
    @pytest.mark.asyncio
    @patch("app.services.hardware_monitor._IS_LINUX", False)
    @patch("app.config.settings")
    async def test_get_snapshot_windows_returns_zeros(mock_settings):
        mock_settings.AGENTOS_HOSTNAME = "windows-host"
        mock_settings.AGENTOS_PRODUCT_NAME = "Windows PC"
        mock_settings.node_exporter_url = "http://localhost:9090"

        svc = HardwareMonitorService()
        snapshot = await svc.get_snapshot()

        assert snapshot.cpu.cores == 0
        assert snapshot.memory.total_bytes == 0
        assert len(snapshot.disks) == 1
        assert snapshot.disks[0].mount_point == "all"
        assert len(snapshot.network) == 1
        assert snapshot.network[0].interface == "all"
