"""Build HardwareSnapshot from VictoriaMetrics vector query results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

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
from app.services.hardware_monitor import HardwareMonitorService
from app.services.vm_client import VmSample


@dataclass(frozen=True)
class NpuMetricSamples:
    utilization: list[VmSample]
    hbm_used: list[VmSample]
    hbm_total: list[VmSample]
    temperature: list[VmSample]
    power: list[VmSample]
    health: list[VmSample]


def _scalar(samples: list[VmSample]) -> float | None:
    if not samples:
        return None
    return samples[0].value


def _label(samples: list[VmSample], label: str) -> str | None:
    for sample in samples:
        value = sample.metric.get(label)
        if value:
            return value
    return None


def group_by_node(samples: list[VmSample]) -> dict[str, list[VmSample]]:
    grouped: dict[str, list[VmSample]] = {}
    for sample in samples:
        node = sample.metric.get("node", "")
        grouped.setdefault(node, []).append(sample)
    return grouped


def node_up(samples: list[VmSample]) -> bool:
    value = _scalar(samples)
    return value is not None and value >= 1


def product_name_from_samples(samples: list[VmSample]) -> str:
    for sample in samples:
        name = sample.metric.get("product_name")
        if name:
            return name
    return "-"


def build_cpu(cpu_usage_samples: list[VmSample], cpu_cores_samples: list[VmSample]) -> CpuInfo:
    usage = _scalar(cpu_usage_samples)
    cores = _scalar(cpu_cores_samples)
    return CpuInfo(
        usage=round(usage, 1) if usage is not None else 0.0,
        cores=int(cores) if cores is not None else 0,
        model_name="-",
    )


def build_memory(
    total_samples: list[VmSample],
    available_samples: list[VmSample],
    swap_total_samples: list[VmSample],
    swap_free_samples: list[VmSample],
) -> MemoryInfo:
    total = int(_scalar(total_samples) or 0)
    available = int(_scalar(available_samples) or 0)
    used = total - available
    swap_total = int(_scalar(swap_total_samples) or 0)
    swap_free = int(_scalar(swap_free_samples) or 0)
    return MemoryInfo(
        total_bytes=total,
        available_bytes=available,
        used_bytes=used,
        usage=round(used / total * 100, 1) if total else 0.0,
        swap_total_bytes=swap_total,
        swap_free_bytes=swap_free,
        swap_usage=round((swap_total - swap_free) / swap_total * 100, 1)
        if swap_total
        else 0.0,
    )


def build_disks(
    size_samples: list[VmSample], avail_samples: list[VmSample]
) -> list[DiskInfo]:
    avail_map: dict[tuple[str, str], int] = {}
    for sample in avail_samples:
        device = sample.metric.get("device", "")
        mount = sample.metric.get("mountpoint", "")
        avail_map[(device, mount)] = int(sample.value)

    seen_devices: set[str] = set()
    disks: list[DiskInfo] = []
    for sample in size_samples:
        device = sample.metric.get("device", "")
        fstype = sample.metric.get("fstype", "")
        mount_point = sample.metric.get("mountpoint", "")
        total = int(sample.value)

        if not HardwareMonitorService.is_real_disk(
            fstype, device, mount_point, float(total), seen_devices
        ):
            continue
        seen_devices.add(device)
        avail = avail_map.get((device, mount_point), 0)
        used = total - avail
        disks.append(
            DiskInfo(
                mount_point=mount_point,
                device=device,
                fstype=fstype,
                total_bytes=total,
                used_bytes=used,
                usage=round(used / total * 100, 1) if total else 0.0,
            )
        )

    total_b = sum(item.total_bytes for item in disks)
    used_b = sum(item.used_bytes for item in disks)
    disks.append(
        DiskInfo(
            mount_point="all",
            device="",
            fstype="",
            total_bytes=total_b,
            used_bytes=used_b,
            usage=round(used_b / total_b * 100, 1) if total_b else 0.0,
        )
    )
    return disks


def _merge_device_rates(
    read_samples: list[VmSample],
    write_samples: list[VmSample],
    read_iops_samples: list[VmSample],
    write_iops_samples: list[VmSample],
) -> list[DiskIoInfo]:
    devices: dict[str, dict[str, float]] = {}

    def _put(samples: list[VmSample], key: str) -> None:
        for sample in samples:
            device = sample.metric.get("device", "")
            if not device:
                continue
            devices.setdefault(device, {})
            devices[device][key] = sample.value

    _put(read_samples, "read")
    _put(write_samples, "write")
    _put(read_iops_samples, "read_iops")
    _put(write_iops_samples, "write_iops")

    result: list[DiskIoInfo] = []
    total_read = total_write = total_read_iops = total_write_iops = 0
    for device, values in sorted(devices.items()):
        read_bps = max(0, int(values.get("read", 0)))
        write_bps = max(0, int(values.get("write", 0)))
        read_iops = max(0, int(values.get("read_iops", 0)))
        write_iops = max(0, int(values.get("write_iops", 0)))
        result.append(
            DiskIoInfo(
                device=device,
                read_bytes_per_sec=read_bps,
                write_bytes_per_sec=write_bps,
                read_count_per_sec=read_iops,
                write_count_per_sec=write_iops,
            )
        )
        total_read += read_bps
        total_write += write_bps
        total_read_iops += read_iops
        total_write_iops += write_iops

    result.append(
        DiskIoInfo(
            device="all",
            read_bytes_per_sec=total_read,
            write_bytes_per_sec=total_write,
            read_count_per_sec=total_read_iops,
            write_count_per_sec=total_write_iops,
        )
    )
    return result


def _merge_network_rates(
    rx_samples: list[VmSample],
    tx_samples: list[VmSample],
    rx_pkt_samples: list[VmSample],
    tx_pkt_samples: list[VmSample],
) -> list[NetworkInfo]:
    interfaces: dict[str, dict[str, float]] = {}

    def _put(samples: list[VmSample], key: str) -> None:
        for sample in samples:
            iface = sample.metric.get("device", "")
            if iface in ("lo", ""):
                continue
            interfaces.setdefault(iface, {})
            interfaces[iface][key] = sample.value

    _put(rx_samples, "rx")
    _put(tx_samples, "tx")
    _put(rx_pkt_samples, "rx_pkt")
    _put(tx_pkt_samples, "tx_pkt")

    result: list[NetworkInfo] = []
    total_rx = total_tx = total_rx_pkt = total_tx_pkt = 0
    for iface, values in sorted(interfaces.items()):
        rx_bps = max(0, int(values.get("rx", 0)))
        tx_bps = max(0, int(values.get("tx", 0)))
        rx_pps = max(0, int(values.get("rx_pkt", 0)))
        tx_pps = max(0, int(values.get("tx_pkt", 0)))
        result.append(
            NetworkInfo(
                interface=iface,
                rx_bytes_per_sec=rx_bps,
                rx_packets_per_sec=rx_pps,
                tx_bytes_per_sec=tx_bps,
                tx_packets_per_sec=tx_pps,
            )
        )
        total_rx += rx_bps
        total_tx += tx_bps
        total_rx_pkt += rx_pps
        total_tx_pkt += tx_pps

    result.append(
        NetworkInfo(
            interface="all",
            rx_bytes_per_sec=total_rx,
            rx_packets_per_sec=total_rx_pkt,
            tx_bytes_per_sec=total_tx,
            tx_packets_per_sec=total_tx_pkt,
        )
    )
    return result


def build_npus(samples: NpuMetricSamples) -> list[NpuInfo]:
    device_ids: set[str] = set()
    for metric_samples in (
        samples.utilization,
        samples.hbm_used,
        samples.hbm_total,
        samples.temperature,
        samples.power,
        samples.health,
    ):
        for sample in metric_samples:
            device_id = sample.metric.get("id")
            if device_id is not None:
                device_ids.add(device_id)

    if not device_ids:
        return []

    def _map(metric_samples: list[VmSample]) -> dict[str, float]:
        result: dict[str, float] = {}
        for sample in metric_samples:
            device_id = sample.metric.get("id")
            if device_id is not None:
                result[device_id] = sample.value
        return result

    util_map = _map(samples.utilization)
    hbm_used_map = _map(samples.hbm_used)
    hbm_total_map = _map(samples.hbm_total)
    temp_map = _map(samples.temperature)
    power_map = _map(samples.power)
    health_map = _map(samples.health)

    devices: list[NpuInfo] = []
    for device_id in sorted(device_ids, key=lambda item: int(item) if item.isdigit() else item):
        hbm_used = int(hbm_used_map.get(device_id, 0))
        hbm_total = int(hbm_total_map.get(device_id, 0))
        devices.append(
            NpuInfo(
                device_id=device_id,
                usage=util_map.get(device_id, 0.0),
                hbm_used_mb=hbm_used,
                hbm_total_mb=hbm_total,
                hbm_usage=round(hbm_used / hbm_total * 100, 1) if hbm_total else 0.0,
                temperature=temp_map.get(device_id, 0.0),
                power_watts=power_map.get(device_id, 0.0),
                health=int(health_map.get(device_id, 1)),
            )
        )

    total_used = sum(item.hbm_used_mb for item in devices)
    total_hbm = sum(item.hbm_total_mb for item in devices)
    avg_usage = sum(item.usage for item in devices) / len(devices)
    max_temp = max((item.temperature for item in devices), default=0.0)
    total_power = sum(item.power_watts for item in devices)
    min_health = min((item.health for item in devices), default=1)

    devices.append(
        NpuInfo(
            device_id="all",
            usage=round(avg_usage, 1),
            hbm_used_mb=total_used,
            hbm_total_mb=total_hbm,
            hbm_usage=round(total_used / total_hbm * 100, 1) if total_hbm else 0.0,
            temperature=max_temp,
            power_watts=round(total_power, 1),
            health=min_health,
        )
    )
    return devices


def build_system(
    uname_samples: list[VmSample],
    dmi_samples: list[VmSample],
    time_samples: list[VmSample],
    boot_samples: list[VmSample],
) -> SystemInfo:
    hostname = _label(uname_samples, "nodename") or "-"
    product_name = _label(dmi_samples, "product_name") or "-"
    node_time = _scalar(time_samples) or 0.0
    boot_time = _scalar(boot_samples) or 0.0

    if boot_time <= 0:
        uptime = -1.0
        boot_time_str = "-"
    else:
        now = node_time if node_time > 0 else datetime.now(timezone.utc).timestamp()
        uptime = now - boot_time
        boot_time_str = datetime.fromtimestamp(boot_time, tz=timezone.utc).isoformat()

    return SystemInfo(
        hostname=hostname,
        product_name=product_name,
        uptime_seconds=uptime,
        boot_time=boot_time_str,
    )


def build_timestamp(time_samples: list[VmSample]) -> str:
    node_time = _scalar(time_samples)
    if node_time and node_time > 0:
        return datetime.fromtimestamp(node_time, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def build_snapshot(query_results: dict[str, list[VmSample]]) -> HardwareSnapshot:
    return HardwareSnapshot(
        system=build_system(
            query_results.get("node_uname", []),
            query_results.get("node_dmi", []),
            query_results.get("node_time", []),
            query_results.get("node_boot_time", []),
        ),
        cpu=build_cpu(
            query_results.get("cpu_usage", []),
            query_results.get("cpu_cores", []),
        ),
        memory=build_memory(
            query_results.get("memory_total", []),
            query_results.get("memory_available", []),
            query_results.get("swap_total", []),
            query_results.get("swap_free", []),
        ),
        disks=build_disks(
            query_results.get("filesystem_size", []),
            query_results.get("filesystem_avail", []),
        ),
        disk_io=_merge_device_rates(
            query_results.get("disk_read_rate", []),
            query_results.get("disk_write_rate", []),
            query_results.get("disk_read_iops", []),
            query_results.get("disk_write_iops", []),
        ),
        network=_merge_network_rates(
            query_results.get("network_rx_rate", []),
            query_results.get("network_tx_rate", []),
            query_results.get("network_rx_packets_rate", []),
            query_results.get("network_tx_packets_rate", []),
        ),
        npus=build_npus(
            NpuMetricSamples(
                utilization=query_results.get("npu_utilization", []),
                hbm_used=query_results.get("npu_hbm_used", []),
                hbm_total=query_results.get("npu_hbm_total", []),
                temperature=query_results.get("npu_temperature", []),
                power=query_results.get("npu_power", []),
                health=query_results.get("npu_health", []),
            )
        ),
        timestamp=build_timestamp(query_results.get("node_time", [])),
    )
