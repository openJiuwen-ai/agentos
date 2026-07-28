"""Hardware monitor service — reads from node_exporter on Linux, empty data on Windows."""

import asyncio
import logging
import platform
import re
import time
from datetime import datetime, timezone

import httpx

from app.schemas.hardware import (
    CpuInfo,
    DiskInfo,
    DiskIoInfo,
    HardwareSnapshot,
    MemoryInfo,
    NetworkInfo,
    SystemInfo,
)

logger = logging.getLogger(__name__)

_IS_LINUX = platform.system() == "Linux"

# node_exporter Prometheus 指标名
_METRIC_CPU = "node_cpu_seconds_total"
_METRIC_MEM_TOTAL = "node_memory_MemTotal_bytes"
_METRIC_MEM_AVAILABLE = "node_memory_MemAvailable_bytes"
_METRIC_SWAP_TOTAL = "node_memory_SwapTotal_bytes"
_METRIC_SWAP_FREE = "node_memory_SwapFree_bytes"
_METRIC_FS_SIZE = "node_filesystem_size_bytes"
_METRIC_FS_AVAIL = "node_filesystem_avail_bytes"
_METRIC_NET_RX = "node_network_receive_bytes_total"
_METRIC_NET_TX = "node_network_transmit_bytes_total"
_METRIC_NET_RX_PKT = "node_network_receive_packets_total"
_METRIC_NET_TX_PKT = "node_network_transmit_packets_total"
_METRIC_DISK_READ = "node_disk_read_bytes_total"
_METRIC_DISK_WRITE = "node_disk_written_bytes_total"
_METRIC_DISK_READ_IOPS = "node_disk_reads_completed_total"
_METRIC_DISK_WRITE_IOPS = "node_disk_writes_completed_total"
_METRIC_BOOT_TIME = "node_boot_time_seconds"
_METRIC_HOSTNAME = "node_uname_info"
_REAL_FS = {"ext4", "xfs", "btrfs", "zfs", "ntfs", "ext3", "ext2"}


def _parse_prometheus(text: str, prefix: str = "") -> dict[str, list[tuple[dict[str, str], float]]]:
    """解析 Prometheus text exposition 格式，返回 {metric_name: [(labels, value), ...]}"""
    result: dict[str, list[tuple[dict[str, str], float]]] = {}
    value_re = re.compile(
        r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|NaN|[+-]?Inf)'
    )
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        # 格式1: metric_name{label1="val1",...} value
        # 格式2: metric_name value（无 label）
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\{([^}]*)\})?\s+(.+)$', line)
        if not m:
            continue
        name = m.group(1)
        if prefix and not name.startswith(prefix):
            continue
        labels_str = m.group(2) or ""
        value_str = m.group(3).strip()
        vm = value_re.match(value_str)
        if not vm:
            continue
        value = float(vm.group(1))
        labels = {}
        for pair in re.findall(r'(\w+)="([^"]*)"', labels_str):
            labels[pair[0]] = pair[1]
        result.setdefault(name, []).append((labels, value))
    return result


class HardwareMonitorService:
    """Reads host metrics from node_exporter, empty data on Windows."""

    def __init__(self, cpu_sample_interval: float = 1.0):
        self.cpu_sample_interval = cpu_sample_interval
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=5)
        self.prev_net: dict[str, tuple[float, float, float, float]] | None = None
        self.prev_net_time: float = 0.0
        self.prev_disk_io: dict[str, tuple[float, float, float, float]] | None = None
        self.prev_disk_io_time: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_metrics(self) -> dict[str, list[tuple[dict[str, str], float]]] | None:
        """从 node_exporter 拉取 Prometheus 指标"""
        from app.config import settings
        url = f"{settings.node_exporter_url}/metrics"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return _parse_prometheus(resp.text)
        except (httpx.HTTPError, ConnectionError) as e:
            logger.warning("Failed to fetch node_exporter metrics: %s", e)
            return None

    async def fetch_cpu_metrics(self) -> dict[str, list[tuple[dict[str, str], float]]] | None:
        """从 node_exporter 拉取仅 CPU 相关指标"""
        from app.config import settings
        url = f"{settings.node_exporter_url}/metrics"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return _parse_prometheus(resp.text, prefix=_METRIC_CPU)
        except (httpx.HTTPError, ConnectionError) as e:
            logger.warning("Failed to fetch node_exporter CPU metrics: %s", e)
            return None

    async def get_snapshot(self) -> HardwareSnapshot:
        async with self._lock:
            return await self._get_snapshot_inner()

    async def _get_snapshot_inner(self) -> HardwareSnapshot:
        if _IS_LINUX:
            metrics1 = await self.fetch_metrics()
            if metrics1 is None:
                return self.empty_snapshot()

            await asyncio.sleep(self.cpu_sample_interval)

            metrics2 = await self.fetch_cpu_metrics()
            if metrics2 is None:
                return self.empty_snapshot()

            cpu = self.parse_cpu(metrics1, metrics2)
            memory = self.parse_memory(metrics1)
            disks = self.parse_disk(metrics1)
            disk_io = self.parse_disk_io(metrics1)
            network = self.parse_network(metrics1)
            boot_time = self.extract_boot_time(metrics1)
        else:
            cpu = CpuInfo(usage=0, cores=0, model_name="-")
            memory = MemoryInfo(total_bytes=0, available_bytes=0, used_bytes=0, usage=0,
                                swap_total_bytes=0, swap_free_bytes=0, swap_usage=0)
            disks = [DiskInfo(mount_point="all", device="", fstype="", total_bytes=0, used_bytes=0, usage=0)]
            disk_io = [DiskIoInfo(device="all", read_bytes_per_sec=0, write_bytes_per_sec=0,
                                  read_count_per_sec=0, write_count_per_sec=0)]
            network = [NetworkInfo(interface="all", rx_bytes_per_sec=0, rx_packets_per_sec=0,
                                   tx_bytes_per_sec=0, tx_packets_per_sec=0)]
            boot_time = 0.0

        return HardwareSnapshot(
            system=self.get_system_info(boot_time=boot_time),
            cpu=cpu,
            memory=memory,
            disks=disks,
            disk_io=disk_io,
            network=network,
            npus=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def empty_snapshot(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            system=self.get_system_info(boot_time=0.0),
            cpu=CpuInfo(usage=0, cores=0, model_name="-"),
            memory=MemoryInfo(total_bytes=0, available_bytes=0, used_bytes=0, usage=0,
                              swap_total_bytes=0, swap_free_bytes=0, swap_usage=0),
            disks=[DiskInfo(mount_point="all", device="", fstype="", total_bytes=0, used_bytes=0, usage=0)],
            disk_io=[DiskIoInfo(device="all", read_bytes_per_sec=0, write_bytes_per_sec=0,
                                read_count_per_sec=0, write_count_per_sec=0)],
            network=[NetworkInfo(interface="all", rx_bytes_per_sec=0, rx_packets_per_sec=0,
                                 tx_bytes_per_sec=0, tx_packets_per_sec=0)],
            npus=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ── System info ──────────────────────────────────────────────────

    def get_system_info(self, boot_time: float = 0.0) -> SystemInfo:
        from app.config import settings
        hostname = settings.AGENTOS_HOSTNAME or "-"
        product_name = settings.AGENTOS_PRODUCT_NAME or "-"
        boot_ts = boot_time if boot_time > 0 else self.get_boot_time()
        if boot_ts <= 0:
            uptime = -1
            boot_time_str = "-"
        else:
            uptime = time.time() - boot_ts
            boot_time_str = datetime.fromtimestamp(boot_ts, tz=timezone.utc).isoformat()
        return SystemInfo(
            hostname=hostname,
            product_name=product_name,
            uptime_seconds=uptime,
            boot_time=boot_time_str,
        )

    @staticmethod
    def get_boot_time() -> float:
        try:
            from app.config import settings
            resp = httpx.get(f"{settings.node_exporter_url}/metrics", timeout=5)
            for line in resp.text.splitlines():
                if line.startswith(_METRIC_BOOT_TIME) and not line.startswith("#"):
                    return float(line.split()[-1])
        except (httpx.HTTPError, ConnectionError) as e:
            logger.debug("Failed to get boot time: %s", e)
        return 0.0

    @staticmethod
    def extract_boot_time(metrics: dict) -> float:
        for labels, value in metrics.get(_METRIC_BOOT_TIME, []):
            return value
        return 0.0

    # ── Parse node_exporter metrics ──────────────────────────────────

    @staticmethod
    def parse_cpu(metrics1: dict, metrics2: dict) -> CpuInfo:
        # Use metrics2 for core count (latest state)
        cores = len(set(
            labels.get("cpu", "")
            for labels, _ in metrics2.get(_METRIC_CPU, [])
        ))

        # Aggregate by mode across all CPUs for both snapshots
        def _aggregate(metrics: dict) -> dict[str, float]:
            result: dict[str, float] = {}
            for labels, value in metrics.get(_METRIC_CPU, []):
                mode = labels.get("mode", "")
                result[mode] = result.get(mode, 0) + value
            return result

        prev = _aggregate(metrics1)
        current = _aggregate(metrics2)

        usage = 0.0
        total_delta = sum(current.values()) - sum(prev.values())
        idle_delta = current.get("idle", 0) - prev.get("idle", 0)
        if total_delta > 0:
            usage = round((total_delta - idle_delta) / total_delta * 100, 1)

        return CpuInfo(usage=usage, cores=cores, model_name="-")

    @staticmethod
    def parse_memory(metrics: dict) -> MemoryInfo:
        def _get(name: str) -> int:
            for labels, value in metrics.get(name, []):
                return int(value)
            return 0

        total = _get(_METRIC_MEM_TOTAL)
        available = _get(_METRIC_MEM_AVAILABLE)
        used = total - available
        swap_total = _get(_METRIC_SWAP_TOTAL)
        swap_free = _get(_METRIC_SWAP_FREE)

        return MemoryInfo(
            total_bytes=total, available_bytes=available, used_bytes=used,
            usage=round(used / total * 100, 1) if total else 0,
            swap_total_bytes=swap_total, swap_free_bytes=swap_free,
            swap_usage=round((swap_total - swap_free) / swap_total * 100, 1) if swap_total else 0,
        )

    @staticmethod
    def is_real_disk(fstype: str, device: str, mount_point: str, total: float,
                      seen_devices: set[str]) -> bool:
        return fstype in _REAL_FS and device not in seen_devices and mount_point and total > 0

    def parse_disk(self, metrics: dict) -> list[DiskInfo]:
        seen_devices: set[str] = set()
        disks: list[DiskInfo] = []

        # fstype 和 mountpoint 直接从 node_filesystem_size_bytes 的 label 获取
        for labels, value in metrics.get(_METRIC_FS_SIZE, []):
            device = labels.get("device", "")
            fstype = labels.get("fstype", "")
            mount_point = labels.get("mountpoint", "")
            total = int(value)

            if not self.is_real_disk(fstype, device, mount_point, total, seen_devices):
                continue
            seen_devices.add(device)

            # 获取可用空间
            avail = 0
            for a_labels, a_value in metrics.get(_METRIC_FS_AVAIL, []):
                if a_labels.get("device") == device and a_labels.get("mountpoint") == mount_point:
                    avail = int(a_value)
                    break
            used = total - avail

            disks.append(DiskInfo(
                mount_point=mount_point, device=device, fstype=fstype,
                total_bytes=total, used_bytes=used,
                usage=round(used / total * 100, 1),
            ))

        total_b = sum(d.total_bytes for d in disks)
        used_b = sum(d.used_bytes for d in disks)
        disks.append(DiskInfo(mount_point="all", device="", fstype="",
                              total_bytes=total_b, used_bytes=used_b,
                              usage=round(used_b / total_b * 100, 1) if total_b else 0))
        return disks

    def parse_disk_io(self, metrics: dict) -> list[DiskIoInfo]:
        current: dict[str, tuple[float, float, float, float]] = {}

        for labels, value in metrics.get(_METRIC_DISK_READ, []):
            dev = labels.get("device", "")
            if not dev:
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (value, entry[1], entry[2], entry[3])

        for labels, value in metrics.get(_METRIC_DISK_WRITE, []):
            dev = labels.get("device", "")
            if not dev:
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (entry[0], entry[1], value, entry[3])

        for labels, value in metrics.get(_METRIC_DISK_READ_IOPS, []):
            dev = labels.get("device", "")
            if not dev:
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (entry[0], value, entry[2], entry[3])

        for labels, value in metrics.get(_METRIC_DISK_WRITE_IOPS, []):
            dev = labels.get("device", "")
            if not dev:
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (entry[0], entry[1], entry[2], value)

        now = time.time()
        result: list[DiskIoInfo] = []

        if self.prev_disk_io is not None and self.prev_disk_io_time > 0:
            dt = now - self.prev_disk_io_time
            if dt > 0:
                tr = tw = trc = twc = 0
                for dev, (rb, rc, wb, wc) in current.items():
                    prev = self.prev_disk_io.get(dev)
                    if prev:
                        rb_s = max(0, int((rb - prev[0]) / dt))
                        rc_s = max(0, int((rc - prev[1]) / dt))
                        wb_s = max(0, int((wb - prev[2]) / dt))
                        wc_s = max(0, int((wc - prev[3]) / dt))
                    else:
                        rb_s = rc_s = wb_s = wc_s = 0
                    result.append(DiskIoInfo(device=dev, read_bytes_per_sec=rb_s, write_bytes_per_sec=wb_s,
                                              read_count_per_sec=rc_s, write_count_per_sec=wc_s))
                    tr += rb_s
                    tw += wb_s
                    trc += rc_s
                    twc += wc_s
                result.append(DiskIoInfo(device="all", read_bytes_per_sec=tr, write_bytes_per_sec=tw,
                                          read_count_per_sec=trc, write_count_per_sec=twc))
        else:
            result.append(DiskIoInfo(device="all", read_bytes_per_sec=0, write_bytes_per_sec=0,
                                      read_count_per_sec=0, write_count_per_sec=0))

        self.prev_disk_io = current
        self.prev_disk_io_time = now
        return result

    def parse_network(self, metrics: dict) -> list[NetworkInfo]:
        current: dict[str, tuple[float, float, float, float]] = {}

        for labels, value in metrics.get(_METRIC_NET_RX, []):
            dev = labels.get("device", "")
            if dev in ("lo", ""):
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (value, entry[1], entry[2], entry[3])

        for labels, value in metrics.get(_METRIC_NET_TX, []):
            dev = labels.get("device", "")
            if dev in ("lo", ""):
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (entry[0], entry[1], value, entry[3])

        for labels, value in metrics.get(_METRIC_NET_RX_PKT, []):
            dev = labels.get("device", "")
            if dev in ("lo", ""):
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (entry[0], value, entry[2], entry[3])

        for labels, value in metrics.get(_METRIC_NET_TX_PKT, []):
            dev = labels.get("device", "")
            if dev in ("lo", ""):
                continue
            entry = current.setdefault(dev, (0, 0, 0, 0))
            current[dev] = (entry[0], entry[1], entry[2], value)

        now = time.time()
        result: list[NetworkInfo] = []

        if self.prev_net is not None and self.prev_net_time > 0:
            dt = now - self.prev_net_time
            if dt > 0:
                total_rx = total_tx = total_rx_pkt = total_tx_pkt = 0
                for iface, (rx, rx_p, tx_v, tx_p) in current.items():
                    prev = self.prev_net.get(iface)
                    if prev:
                        rx_s = max(0, int((rx - prev[0]) / dt))
                        rx_p_s = max(0, int((rx_p - prev[1]) / dt))
                        tx_s = max(0, int((tx_v - prev[2]) / dt))
                        tx_p_s = max(0, int((tx_p - prev[3]) / dt))
                    else:
                        rx_s = rx_p_s = tx_s = tx_p_s = 0
                    result.append(NetworkInfo(interface=iface, rx_bytes_per_sec=rx_s, rx_packets_per_sec=rx_p_s,
                                              tx_bytes_per_sec=tx_s, tx_packets_per_sec=tx_p_s))
                    total_rx += rx_s
                    total_tx += tx_s
                    total_rx_pkt += rx_p_s
                    total_tx_pkt += tx_p_s
                result.append(NetworkInfo(interface="all", rx_bytes_per_sec=total_rx, rx_packets_per_sec=total_rx_pkt,
                                          tx_bytes_per_sec=total_tx, tx_packets_per_sec=total_tx_pkt))
        else:
            for iface in current:
                result.append(NetworkInfo(interface=iface, rx_bytes_per_sec=0, rx_packets_per_sec=0,
                                          tx_bytes_per_sec=0, tx_packets_per_sec=0))
            if current:
                result.append(NetworkInfo(interface="all", rx_bytes_per_sec=0, rx_packets_per_sec=0,
                                          tx_bytes_per_sec=0, tx_packets_per_sec=0))

        self.prev_net = current
        self.prev_net_time = now
        return result
