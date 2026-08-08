"""Hardware monitor node configuration."""

from __future__ import annotations

from pydantic import BaseModel


MASTER_NODE_ID = "master"
MASTER_ROLE = "Master"
WORKER_ROLE = "Worker"


class MonitorNodeConfig(BaseModel):
    host: str


class ConfiguredHardwareNode(BaseModel):
    id: str
    host: str
    role: str
    vm_label: str


class NodeTarget(BaseModel):
    id: str
    host: str
    vm_label: str
    node_exporter_url: str
    npu_exporter_url: str
