"""NPU monitor — calls npu_exporter /metrics Prometheus endpoint.

Returns empty list when npu_exporter is unreachable or returns invalid data.
"""

import logging
import re

import httpx

from app.schemas.hardware import NpuInfo

logger = logging.getLogger(__name__)

_RE_UTILIZATION = re.compile(r'npu_chip_info_utilization\{[^}]*id="(\d+)"[^}]*\}\s+([\d.]+)')
_RE_HBM_USED = re.compile(r'npu_chip_info_hbm_used_memory\{[^}]*id="(\d+)"[^}]*\}\s+(\d+)')
_RE_HBM_TOTAL = re.compile(r'npu_chip_info_hbm_total_memory\{[^}]*id="(\d+)"[^}]*\}\s+(\d+)')
_RE_TEMPERATURE = re.compile(r'npu_chip_info_temperature\{[^}]*id="(\d+)"[^}]*\}\s+([\d.]+)')
_RE_POWER = re.compile(r'npu_chip_info_power\{[^}]*id="(\d+)"[^}]*\}\s+([\d.]+)')
_RE_HEALTH = re.compile(r'npu_chip_info_health_status\{[^}]*id="(\d+)"[^}]*\}\s+(\d+)')


class NpuMonitor:
    """Calls npu_exporter /metrics, parses Prometheus text format."""

    def __init__(self, npu_url: str):
        self._npu_url = npu_url.rstrip("/")

    @property
    def npu_url(self) -> str:
        return self._npu_url

    async def get_npu_info(self) -> list[NpuInfo]:
        """Fetch NPU data. Returns empty list when unreachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._npu_url}/metrics")
                resp.raise_for_status()
                return self.parse_metrics(resp.text)
        except Exception as e:
            logger.warning("npu_exporter unreachable: %s", e)
            return []

    @staticmethod
    def parse_metrics(text: str) -> list[NpuInfo]:
        """Parse Prometheus text format into NpuInfo list."""
        util_map: dict[str, float] = {}
        hbm_used: dict[str, int] = {}
        hbm_total: dict[str, int] = {}
        temp_map: dict[str, float] = {}
        power_map: dict[str, float] = {}
        health_map: dict[str, int] = {}

        for m in _RE_UTILIZATION.finditer(text):
            util_map[m.group(1)] = float(m.group(2))
        for m in _RE_HBM_USED.finditer(text):
            hbm_used[m.group(1)] = int(m.group(2))
        for m in _RE_HBM_TOTAL.finditer(text):
            hbm_total[m.group(1)] = int(m.group(2))
        for m in _RE_TEMPERATURE.finditer(text):
            temp_map[m.group(1)] = float(m.group(2))
        for m in _RE_POWER.finditer(text):
            power_map[m.group(1)] = float(m.group(2))
        for m in _RE_HEALTH.finditer(text):
            health_map[m.group(1)] = int(m.group(2))

        device_ids = sorted(
            set(util_map) | set(hbm_used) | set(hbm_total)
            | set(temp_map) | set(power_map) | set(health_map)
        )
        if not device_ids:
            return []

        devices: list[NpuInfo] = []
        for did in device_ids:
            hu = hbm_used.get(did, 0)
            ht = hbm_total.get(did, 0)
            devices.append(
                NpuInfo(
                    device_id=did,
                    usage=util_map.get(did, 0),
                    hbm_used_mb=hu,
                    hbm_total_mb=ht,
                    hbm_usage=round(hu / ht * 100, 1) if ht else 0,
                    temperature=temp_map.get(did, 0),
                    power_watts=power_map.get(did, 0),
                    health=health_map.get(did, 1),
                )
            )

        total_used = sum(d.hbm_used_mb for d in devices)
        total_hbm = sum(d.hbm_total_mb for d in devices)
        avg_usage = sum(d.usage for d in devices) / len(devices)
        max_temp = max((d.temperature for d in devices), default=0)
        total_power = sum(d.power_watts for d in devices)
        min_health = min((d.health for d in devices), default=1)

        devices.append(
            NpuInfo(
                device_id="all",
                usage=round(avg_usage, 1),
                hbm_used_mb=total_used,
                hbm_total_mb=total_hbm,
                hbm_usage=round(total_used / total_hbm * 100, 1) if total_hbm else 0,
                temperature=max_temp,
                power_watts=round(total_power, 1),
                health=min_health,
            )
        )
        return devices
