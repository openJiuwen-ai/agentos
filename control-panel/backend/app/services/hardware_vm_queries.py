"""PromQL templates for hardware monitoring via VictoriaMetrics."""


def _escape_node(node: str) -> str:
    return node.replace("\\", "\\\\").replace('"', '\\"')


def _node_job(job: str, node: str) -> str:
    n = _escape_node(node)
    return f'{{job="{job}",node="{n}"}}'


def up_node(node: str) -> str:
    return f"up{_node_job('node-exporter', node)}"


def up_all_nodes() -> str:
    return 'up{job="node-exporter"}'


def product_name_node(node: str) -> str:
    return f"node_dmi_info{_node_job('node-exporter', node)}"


def product_name_all() -> str:
    return 'node_dmi_info{job="node-exporter"}'


def cpu_usage(node: str) -> str:
    n = _escape_node(node)
    return (
        f'100 - avg(rate(node_cpu_seconds_total'
        f'{{mode="idle",job="node-exporter",node="{n}"}}[1m])) * 100'
    )


def cpu_cores(node: str) -> str:
    n = _escape_node(node)
    return f'count(node_cpu_seconds_total{{mode="idle",job="node-exporter",node="{n}"}})'


def memory_total(node: str) -> str:
    return f"node_memory_MemTotal_bytes{_node_job('node-exporter', node)}"


def memory_available(node: str) -> str:
    return f"node_memory_MemAvailable_bytes{_node_job('node-exporter', node)}"


def swap_total(node: str) -> str:
    return f"node_memory_SwapTotal_bytes{_node_job('node-exporter', node)}"


def swap_free(node: str) -> str:
    return f"node_memory_SwapFree_bytes{_node_job('node-exporter', node)}"


def filesystem_size(node: str) -> str:
    return f"node_filesystem_size_bytes{_node_job('node-exporter', node)}"


def filesystem_avail(node: str) -> str:
    return f"node_filesystem_avail_bytes{_node_job('node-exporter', node)}"


def disk_read_rate(node: str) -> str:
    n = _escape_node(node)
    return (
        f"rate(node_disk_read_bytes_total"
        f'{{job="node-exporter",node="{n}"}}[1m])'
    )


def disk_write_rate(node: str) -> str:
    n = _escape_node(node)
    return (
        f"rate(node_disk_written_bytes_total"
        f'{{job="node-exporter",node="{n}"}}[1m])'
    )


def disk_read_iops(node: str) -> str:
    n = _escape_node(node)
    return (
        f"rate(node_disk_reads_completed_total"
        f'{{job="node-exporter",node="{n}"}}[1m])'
    )


def disk_write_iops(node: str) -> str:
    n = _escape_node(node)
    return (
        f"rate(node_disk_writes_completed_total"
        f'{{job="node-exporter",node="{n}"}}[1m])'
    )


def network_rx_rate(node: str) -> str:
    n = _escape_node(node)
    return (
        f'rate(node_network_receive_bytes_total'
        f'{{device!="lo",job="node-exporter",node="{n}"}}[1m])'
    )


def network_tx_rate(node: str) -> str:
    n = _escape_node(node)
    return (
        f'rate(node_network_transmit_bytes_total'
        f'{{device!="lo",job="node-exporter",node="{n}"}}[1m])'
    )


def network_rx_packets_rate(node: str) -> str:
    n = _escape_node(node)
    return (
        f'rate(node_network_receive_packets_total'
        f'{{device!="lo",job="node-exporter",node="{n}"}}[1m])'
    )


def network_tx_packets_rate(node: str) -> str:
    n = _escape_node(node)
    return (
        f'rate(node_network_transmit_packets_total'
        f'{{device!="lo",job="node-exporter",node="{n}"}}[1m])'
    )


def node_uname(node: str) -> str:
    return f"node_uname_info{_node_job('node-exporter', node)}"


def node_dmi(node: str) -> str:
    return f"node_dmi_info{_node_job('node-exporter', node)}"


def node_time(node: str) -> str:
    return f"node_time_seconds{_node_job('node-exporter', node)}"


def node_boot_time(node: str) -> str:
    return f"node_boot_time_seconds{_node_job('node-exporter', node)}"


def npu_utilization(node: str) -> str:
    return f"npu_chip_info_utilization{_node_job('npu-exporter', node)}"


def npu_hbm_used(node: str) -> str:
    return f"npu_chip_info_hbm_used_memory{_node_job('npu-exporter', node)}"


def npu_hbm_total(node: str) -> str:
    return f"npu_chip_info_hbm_total_memory{_node_job('npu-exporter', node)}"


def npu_temperature(node: str) -> str:
    return f"npu_chip_info_temperature{_node_job('npu-exporter', node)}"


def npu_power(node: str) -> str:
    return f"npu_chip_info_power{_node_job('npu-exporter', node)}"


def npu_health(node: str) -> str:
    return f"npu_chip_info_health_status{_node_job('npu-exporter', node)}"


def snapshot_query_names(node: str) -> dict[str, str]:
    return {
        "cpu_usage": cpu_usage(node),
        "cpu_cores": cpu_cores(node),
        "memory_total": memory_total(node),
        "memory_available": memory_available(node),
        "swap_total": swap_total(node),
        "swap_free": swap_free(node),
        "filesystem_size": filesystem_size(node),
        "filesystem_avail": filesystem_avail(node),
        "disk_read_rate": disk_read_rate(node),
        "disk_write_rate": disk_write_rate(node),
        "disk_read_iops": disk_read_iops(node),
        "disk_write_iops": disk_write_iops(node),
        "network_rx_rate": network_rx_rate(node),
        "network_tx_rate": network_tx_rate(node),
        "network_rx_packets_rate": network_rx_packets_rate(node),
        "network_tx_packets_rate": network_tx_packets_rate(node),
        "node_uname": node_uname(node),
        "node_dmi": node_dmi(node),
        "node_time": node_time(node),
        "node_boot_time": node_boot_time(node),
        "npu_utilization": npu_utilization(node),
        "npu_hbm_used": npu_hbm_used(node),
        "npu_hbm_total": npu_hbm_total(node),
        "npu_temperature": npu_temperature(node),
        "npu_power": npu_power(node),
        "npu_health": npu_health(node),
    }
