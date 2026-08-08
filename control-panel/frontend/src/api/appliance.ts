import { get } from './index';

export interface ApplianceMonitorSystem {
  hostname: string;
  product_name?: string;
  uptime_seconds: number;
  boot_time: string;
}

export interface ApplianceMonitorCpu {
  usage: number;
  cores: number;
  model_name: string;
}

export interface ApplianceMonitorMemory {
  total_bytes: number;
  available_bytes: number;
  used_bytes: number;
  usage: number;
  swap_total_bytes: number;
  swap_free_bytes: number;
  swap_usage: number;
}

export interface ApplianceMonitorDisk {
  mount_point: string;
  device: string;
  fstype: string;
  total_bytes: number;
  used_bytes: number;
  usage: number;
}

export interface ApplianceMonitorDiskIo {
  device: string;
  read_bytes_per_sec: number;
  write_bytes_per_sec: number;
  read_count_per_sec: number;
  write_count_per_sec: number;
}

export interface ApplianceMonitorNetwork {
  interface: string;
  rx_bytes_per_sec: number;
  rx_packets_per_sec: number;
  tx_bytes_per_sec: number;
  tx_packets_per_sec: number;
}

export interface ApplianceMonitorNpu {
  device_id: string;
  usage: number;
  hbm_used_mb: number;
  hbm_total_mb: number;
  hbm_usage: number;
  temperature: number;
  power_watts: number;
  health: number;
}

export interface ApplianceMonitorData {
  system: ApplianceMonitorSystem;
  cpu: ApplianceMonitorCpu;
  memory: ApplianceMonitorMemory;
  disks: ApplianceMonitorDisk[];
  disk_io: ApplianceMonitorDiskIo[];
  network: ApplianceMonitorNetwork[];
  npus: ApplianceMonitorNpu[];
  timestamp: string;
}

export interface HardwareNodeSummary {
  id: string;
  role: string;
  host: string;
  product_name: string;
  status: 'online' | 'offline';
  error: string | null;
}

export interface HardwareNodesData {
  nodes: HardwareNodeSummary[];
  timestamp: string;
}

export interface NodeSnapshotData {
  node: string;
  status: 'online' | 'offline';
  error: string | null;
  snapshot: ApplianceMonitorData | null;
}

export async function fetchHardwareNodes(): Promise<HardwareNodesData> {
  return get<HardwareNodesData>('/api/v1/hardware/nodes');
}

export async function fetchApplianceMonitor(id: string): Promise<NodeSnapshotData> {
  return get<NodeSnapshotData>('/api/v1/hardware/snapshot', { node: id });
}
