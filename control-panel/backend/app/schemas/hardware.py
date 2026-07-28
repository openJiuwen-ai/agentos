"""Pydantic models for hardware monitoring."""

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    hostname: str
    product_name: str
    uptime_seconds: float
    boot_time: str


class CpuInfo(BaseModel):
    usage: float = Field(ge=0, le=100)
    cores: int
    model_name: str


class MemoryInfo(BaseModel):
    total_bytes: int
    available_bytes: int
    used_bytes: int
    usage: float = Field(ge=0, le=100)
    swap_total_bytes: int
    swap_free_bytes: int
    swap_usage: float = Field(ge=0, le=100)


class DiskInfo(BaseModel):
    mount_point: str
    device: str
    fstype: str
    total_bytes: int
    used_bytes: int
    usage: float = Field(ge=0, le=100)


class NetworkInfo(BaseModel):
    interface: str
    rx_bytes_per_sec: int
    rx_packets_per_sec: int
    tx_bytes_per_sec: int
    tx_packets_per_sec: int


class DiskIoInfo(BaseModel):
    device: str
    read_bytes_per_sec: int
    write_bytes_per_sec: int
    read_count_per_sec: int
    write_count_per_sec: int


class NpuInfo(BaseModel):
    device_id: str
    usage: float = Field(ge=0, le=100)
    hbm_used_mb: int
    hbm_total_mb: int
    hbm_usage: float = Field(ge=0, le=100)
    temperature: float
    power_watts: float
    health: int = 1          # 1=healthy, 0=unhealthy


class HardwareSnapshot(BaseModel):
    system: SystemInfo
    cpu: CpuInfo
    memory: MemoryInfo
    disks: list[DiskInfo]
    disk_io: list[DiskIoInfo]
    network: list[NetworkInfo]
    npus: list[NpuInfo]
    timestamp: str
