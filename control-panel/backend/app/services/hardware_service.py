"""Hardware monitoring orchestration — multi-node via VictoriaMetrics."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.models.monitor_node import ConfiguredHardwareNode
from app.schemas.hardware import (
    HardwareNodeSummary,
    HardwareNodesData,
    NodeSnapshotData,
)
from app.services import hardware_vm_builder as builder
from app.services import hardware_vm_queries as queries
from app.services.vm_client import VmClient

logger = logging.getLogger(__name__)

VM_UNAVAILABLE_ERROR = "VictoriaMetrics unavailable"


class HardwareService:
    def __init__(self) -> None:
        self._vm = VmClient(settings.VICTORIAMETRICS_URL)

    async def close(self) -> None:
        await self._vm.close()

    @staticmethod
    def _configured_nodes() -> list[ConfiguredHardwareNode]:
        return settings.configured_hardware_nodes

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _vm_available(self) -> bool:
        if not self._vm.configured:
            return False
        return await self._vm.is_available()

    async def _query_map(self, promql_map: dict[str, str]) -> dict[str, list]:
        keys = list(promql_map.keys())
        results = await asyncio.gather(
            *(self._vm.query(promql_map[key]) for key in keys)
        )
        return dict(zip(keys, results))

    async def list_nodes(self) -> HardwareNodesData:
        configured = self._configured_nodes()
        vm_ok = await self._vm_available()

        if not vm_ok:
            return HardwareNodesData(
                nodes=[
                    HardwareNodeSummary(
                        id=node.id,
                        role=node.role,
                        host=node.host,
                        product_name="-",
                        status="offline",
                        error=VM_UNAVAILABLE_ERROR,
                    )
                    for node in configured
                ],
                timestamp=self._timestamp(),
            )

        up_samples, dmi_samples = await asyncio.gather(
            self._vm.query(queries.up_all_nodes()),
            self._vm.query(queries.product_name_all()),
        )
        up_by_node = {
            sample.metric.get("node", ""): sample.value >= 1 for sample in up_samples
        }
        dmi_by_node = builder.group_by_node(dmi_samples)

        nodes: list[HardwareNodeSummary] = []
        for node in configured:
            online = up_by_node.get(node.vm_label, False)
            product_name = (
                builder.product_name_from_samples(dmi_by_node.get(node.vm_label, []))
                if online
                else "-"
            )
            nodes.append(
                HardwareNodeSummary(
                    id=node.id,
                    role=node.role,
                    host=node.host,
                    product_name=product_name,
                    status="online" if online else "offline",
                    error=None,
                )
            )

        return HardwareNodesData(nodes=nodes, timestamp=self._timestamp())

    async def get_node_snapshot(self, node_id: str) -> NodeSnapshotData:
        vm_label = settings.resolve_vm_label(node_id)
        if vm_label is None:
            return NodeSnapshotData(
                node=node_id,
                status="offline",
                error="unknown node",
                snapshot=None,
            )

        vm_ok = await self._vm_available()
        if not vm_ok:
            return NodeSnapshotData(
                node=node_id,
                status="offline",
                error=VM_UNAVAILABLE_ERROR,
                snapshot=None,
            )

        up_samples = await self._vm.query(queries.up_node(vm_label))
        if not builder.node_up(up_samples):
            return NodeSnapshotData(
                node=node_id,
                status="offline",
                error="exporter unreachable",
                snapshot=None,
            )

        query_results = await self._query_map(queries.snapshot_query_names(vm_label))
        snapshot = builder.build_snapshot(query_results)
        return NodeSnapshotData(
            node=node_id,
            status="online",
            error=None,
            snapshot=snapshot,
        )
