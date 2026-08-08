"""hardware_vm_builder unit tests."""

from app.services.hardware_vm_builder import (
    NpuMetricSamples,
    build_cpu,
    build_npus,
    build_snapshot,
    node_up,
    product_name_from_samples,
)
from app.services.vm_client import VmSample


class TestHardwareVmBuilder:
    @staticmethod
    def test_node_up():
        assert node_up([VmSample(metric={"node": "master"}, value=1.0)])
        assert not node_up([VmSample(metric={"node": "master"}, value=0.0)])

    @staticmethod
    def test_product_name_from_samples():
        samples = [
            VmSample(
                metric={"node": "master", "product_name": "Atlas 800"},
                value=1.0,
            )
        ]
        assert product_name_from_samples(samples) == "Atlas 800"
        assert product_name_from_samples([]) == "-"

    @staticmethod
    def test_build_cpu():
        cpu = build_cpu(
            [VmSample(metric={}, value=42.5)],
            [VmSample(metric={}, value=64.0)],
        )
        assert cpu.usage == 42.5
        assert cpu.cores == 64

    @staticmethod
    def test_build_npus_empty():
        assert build_npus(
            NpuMetricSamples([], [], [], [], [], [])
        ) == []

    @staticmethod
    def test_build_snapshot_minimal():
        query_results = {
            "node_uname": [VmSample(metric={"nodename": "host-1"}, value=1.0)],
            "node_dmi": [VmSample(metric={"product_name": "Test Device"}, value=1.0)],
            "node_time": [VmSample(metric={}, value=1_722_841_200.0)],
            "node_boot_time": [VmSample(metric={}, value=1_722_754_800.0)],
            "cpu_usage": [VmSample(metric={}, value=10.0)],
            "cpu_cores": [VmSample(metric={}, value=8.0)],
            "memory_total": [VmSample(metric={}, value=1_000_000.0)],
            "memory_available": [VmSample(metric={}, value=500_000.0)],
            "swap_total": [VmSample(metric={}, value=0.0)],
            "swap_free": [VmSample(metric={}, value=0.0)],
            "filesystem_size": [],
            "filesystem_avail": [],
            "disk_read_rate": [],
            "disk_write_rate": [],
            "disk_read_iops": [],
            "disk_write_iops": [],
            "network_rx_rate": [],
            "network_tx_rate": [],
            "network_rx_packets_rate": [],
            "network_tx_packets_rate": [],
            "npu_utilization": [],
            "npu_hbm_used": [],
            "npu_hbm_total": [],
            "npu_temperature": [],
            "npu_power": [],
            "npu_health": [],
        }
        snapshot = build_snapshot(query_results)
        assert snapshot.system.hostname == "host-1"
        assert snapshot.cpu.usage == 10.0
        assert snapshot.memory.total_bytes == 1_000_000
        assert snapshot.npus == []
