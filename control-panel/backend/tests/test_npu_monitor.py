"""NpuMonitor unit tests — mocked HTTP responses for Prometheus format parsing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.npu_monitor import NpuMonitor
from app.schemas.hardware import NpuInfo


SINGLE_NPU_PROMETHEUS = """# HELP npu_chip_info_utilization NPU core utilization percentage
# TYPE npu_chip_info_utilization gauge
npu_chip_info_utilization{id="0",container_name="",namespace="",pod_name="",model_name="910A"} 75.5

# HELP npu_chip_info_hbm_used_memory HBM memory used in MB
# TYPE npu_chip_info_hbm_used_memory gauge
npu_chip_info_hbm_used_memory{id="0"} 17179869184

# HELP npu_chip_info_hbm_total_memory HBM memory total in MB
# TYPE npu_chip_info_hbm_total_memory gauge
npu_chip_info_hbm_total_memory{id="0"} 34359738368

# HELP npu_chip_info_temperature Celsius
# TYPE npu_chip_info_temperature gauge
npu_chip_info_temperature{id="0"} 65

# HELP npu_chip_info_power Power consumption in watts
# TYPE npu_chip_info_power gauge
npu_chip_info_power{id="0"} 150.5

# HELP npu_chip_info_health_status NPU health status
# TYPE npu_chip_info_health_status gauge
npu_chip_info_health_status{id="0"} 1
"""

MULTI_NPU_PROMETHEUS = """# HELP npu_chip_info_utilization NPU core utilization percentage
# TYPE npu_chip_info_utilization gauge
npu_chip_info_utilization{id="0",container_name="",namespace="",pod_name="",model_name="910A"} 75.5
npu_chip_info_utilization{id="1",container_name="",namespace="",pod_name="",model_name="910A"} 62.3

# HELP npu_chip_info_hbm_used_memory HBM memory used in MB
# TYPE npu_chip_info_hbm_used_memory gauge
npu_chip_info_hbm_used_memory{id="0"} 17179869184
npu_chip_info_hbm_used_memory{id="1"} 12884901888

# HELP npu_chip_info_hbm_total_memory HBM memory total in MB
# TYPE npu_chip_info_hbm_total_memory gauge
npu_chip_info_hbm_total_memory{id="0"} 34359738368
npu_chip_info_hbm_total_memory{id="1"} 34359738368

# HELP npu_chip_info_temperature Celsius
# TYPE npu_chip_info_temperature gauge
npu_chip_info_temperature{id="0"} 65
npu_chip_info_temperature{id="1"} 58

# HELP npu_chip_info_power Power consumption in watts
# TYPE npu_chip_info_power gauge
npu_chip_info_power{id="0"} 150.5
npu_chip_info_power{id="1"} 120.0

# HELP npu_chip_info_health_status NPU health status
# TYPE npu_chip_info_health_status gauge
npu_chip_info_health_status{id="0"} 1
npu_chip_info_health_status{id="1"} 1
"""

UNHEALTHY_NPU_PROMETHEUS = """# HELP npu_chip_info_utilization NPU core utilization percentage
# TYPE npu_chip_info_utilization gauge
npu_chip_info_utilization{id="0",container_name="",namespace="",pod_name="",model_name="910A"} 0.0
npu_chip_info_utilization{id="1",container_name="",namespace="",pod_name="",model_name="910A"} 45.2

# HELP npu_chip_info_health_status NPU health status
# TYPE npu_chip_info_health_status gauge
npu_chip_info_health_status{id="0"} 0
npu_chip_info_health_status{id="1"} 1
"""

EMPTY_PROMETHEUS = """# HELP some_other_metric A metric we don't parse
# TYPE some_other_metric gauge
some_other_metric 42
"""


class TestParseMetrics:
    @staticmethod
    def test_single_device():
        monitor = NpuMonitor("http://localhost:9012")
        devices = monitor.parse_metrics(SINGLE_NPU_PROMETHEUS)

        assert len(devices) == 2  # device 0 + all summary
        assert devices[0].device_id == "0"
        assert devices[0].usage == 75.5
        assert devices[0].hbm_used_mb == 17179869184
        assert devices[0].hbm_total_mb == 34359738368
        assert devices[0].hbm_usage == 50.0
        assert devices[0].temperature == 65.0
        assert devices[0].power_watts == 150.5

        # All summary
        assert devices[1].device_id == "all"
        assert devices[1].usage == 75.5
        assert devices[1].hbm_used_mb == 17179869184
        assert devices[1].hbm_total_mb == 34359738368
        assert devices[1].temperature == 65.0
        assert devices[1].power_watts == 150.5

    @staticmethod
    def test_multiple_devices():
        monitor = NpuMonitor("http://localhost:9012")
        devices = monitor.parse_metrics(MULTI_NPU_PROMETHEUS)

        assert len(devices) == 3  # device 0, device 1, all

        assert devices[0].device_id == "0"
        assert devices[0].usage == 75.5
        assert devices[1].device_id == "1"
        assert devices[1].usage == 62.3

        # All summary
        all_dev = devices[2]
        assert all_dev.device_id == "all"
        assert all_dev.usage == round((75.5 + 62.3) / 2, 1)
        assert all_dev.hbm_used_mb == 17179869184 + 12884901888
        assert all_dev.hbm_total_mb == 34359738368 + 34359738368
        assert all_dev.temperature == 65.0  # max
        assert all_dev.power_watts == round(150.5 + 120.0, 1)

    @staticmethod
    def test_empty_metrics():
        monitor = NpuMonitor("http://localhost:9012")
        devices = monitor.parse_metrics(EMPTY_PROMETHEUS)
        assert devices == []

    @staticmethod
    def test_empty_string():
        monitor = NpuMonitor("http://localhost:9012")
        devices = monitor.parse_metrics("")
        assert devices == []

    @staticmethod
    def test_partial_metrics():
        """Only utilization reported, no HBM/temp/power - should still parse."""
        text = 'npu_chip_info_utilization{id="0",container_name="",namespace="",pod_name="",model_name="910A"} 50.0\n'
        monitor = NpuMonitor("http://localhost:9012")
        devices = monitor.parse_metrics(text)

        assert len(devices) == 2  # device 0 + all
        assert devices[0].usage == 50.0
        assert devices[0].hbm_used_mb == 0
        assert devices[0].hbm_total_mb == 0
        assert devices[0].hbm_usage == 0.0
        assert devices[0].temperature == 0
        assert devices[0].power_watts == 0
        assert devices[0].health == 1  # default healthy

    @staticmethod
    def test_unhealthy_device():
        """Parse unhealthy NPU with error code."""
        monitor = NpuMonitor("http://localhost:9012")
        devices = monitor.parse_metrics(UNHEALTHY_NPU_PROMETHEUS)

        assert len(devices) == 3  # device 0, device 1, all

        # Device 0 is unhealthy
        assert devices[0].device_id == "0"
        assert devices[0].health == 0

        # Device 1 is healthy
        assert devices[1].device_id == "1"
        assert devices[1].health == 1

        # All summary takes minimum health (unhealthy if any is unhealthy)
        all_dev = devices[2]
        assert all_dev.device_id == "all"
        assert all_dev.health == 0  # min of [0, 1]


class TestGetNpuInfo:
    @pytest.mark.asyncio
    async def test_unreachable_returns_empty(self):
        monitor = NpuMonitor("http://localhost:9012")
        result = await monitor.get_npu_info()
        assert result == []

    @pytest.mark.asyncio
    async def test_non_200_returns_empty(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("500")

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.npu_monitor.httpx.AsyncClient", return_value=mock_client):
            monitor = NpuMonitor("http://localhost:9012")
            result = await monitor.get_npu_info()
            assert result == []

    @pytest.mark.asyncio
    async def test_valid_response(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = SINGLE_NPU_PROMETHEUS

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.npu_monitor.httpx.AsyncClient", return_value=mock_client):
            monitor = NpuMonitor("http://localhost:9012")
            result = await monitor.get_npu_info()
            assert len(result) == 2
            assert result[0].device_id == "0"
            assert result[1].device_id == "all"

    @pytest.mark.asyncio
    async def test_parse_error_returns_empty(self):
        """HTTP 200 but parse_metrics raises → returns empty list."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = "invalid garbage text"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.npu_monitor.httpx.AsyncClient", return_value=mock_client):
            with patch.object(NpuMonitor, "parse_metrics", side_effect=ValueError("parse fail")):
                monitor = NpuMonitor("http://localhost:9012")
                result = await monitor.get_npu_info()
                assert result == []


class TestUrlHandling:
    @staticmethod
    def test_strips_trailing_slash():
        monitor = NpuMonitor("http://localhost:9012/")
        assert monitor.npu_url == "http://localhost:9012"

    @staticmethod
    def test_preserves_url():
        monitor = NpuMonitor("http://myhost:8080")
        assert monitor.npu_url == "http://myhost:8080"
