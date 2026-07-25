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

export async function fetchApplianceMonitor(): Promise<ApplianceMonitorData> {
  return get<ApplianceMonitorData>('/api/v1/hardware/snapshot');
}
