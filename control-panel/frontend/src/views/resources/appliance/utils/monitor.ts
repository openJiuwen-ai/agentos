import type { ApplianceMonitorData } from '@/api/appliance';

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
const SECONDS_PER_HOUR = 3_600;
const SECONDS_PER_DAY = SECONDS_PER_HOUR * 24;
const BYTES_PER_KIB = 1024;
const TIMESTAMP_FIELD_WIDTH = 2;
const GB_UNIT_INDEX = BYTE_UNITS.indexOf('GB');
const BYTE_WHOLE_DIGITS = 0;
const BYTE_FRACTION_DIGITS = 1;

export function formatMonitorTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  const pad = (value: number) => String(value).padStart(TIMESTAMP_FIELD_WIDTH, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function formatUptimeSeconds(seconds: number): string {
  if (seconds === -1) {
    return '--';
  }
  const days = Math.floor(seconds / SECONDS_PER_DAY);
  const hours = Math.floor((seconds % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
  return `${days} 天 ${hours} 小时`;
}

function byteUnitIndex(bytes: number): number {
  if (bytes <= 0) {
    return 0;
  }
  return Math.min(Math.floor(Math.log(bytes) / Math.log(BYTES_PER_KIB)), BYTE_UNITS.length - 1);
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  const unitIndex = byteUnitIndex(bytes);
  const value = bytes / BYTES_PER_KIB ** unitIndex;
  const digits = unitIndex >= GB_UNIT_INDEX ? BYTE_FRACTION_DIGITS : BYTE_WHOLE_DIGITS;
  return `${value.toFixed(digits)} ${BYTE_UNITS[unitIndex]}`;
}

export type BytePairLabel = {
  used: string;
  total: string;
  unit: string;
};

function formatAlignedByteValue(bytes: number, divisor: number): string {
  const value = bytes <= 0 ? 0 : bytes / divisor;
  if (value > 0 && value < 1) {
    return value.toFixed(2);
  }
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}` : rounded.toFixed(1);
}

export function formatBytePair(usedBytes: number, totalBytes: number): BytePairLabel {
  const unitIndex = byteUnitIndex(Math.max(usedBytes, totalBytes, 0));
  const divisor = BYTES_PER_KIB ** unitIndex;
  return {
    used: formatAlignedByteValue(usedBytes, divisor),
    total: formatAlignedByteValue(totalBytes, divisor),
    unit: BYTE_UNITS[unitIndex] ?? 'B',
  };
}

export function formatBytesPerSecParts(bytesPerSec: number): { value: string; unit: string } {
  if (bytesPerSec <= 0) {
    return { value: '0', unit: 'B/s' };
  }
  const formatted = formatBytes(bytesPerSec);
  const spaceIndex = formatted.indexOf(' ');
  if (spaceIndex === -1) {
    return { value: formatted, unit: 'B/s' };
  }
  return {
    value: formatted.slice(0, spaceIndex),
    unit: `${formatted.slice(spaceIndex + 1)}/s`,
  };
}

export function roundUsagePercent(value: number): number {
  return Math.round(value * 10) / 10;
}

export function formatUsagePercent(value: number): string {
  const rounded = roundUsagePercent(value);
  return Number.isInteger(rounded) ? `${rounded}` : rounded.toFixed(1);
}

export function pickDiskAll(data: ApplianceMonitorData) {
  return data.disks.find((item) => item.mount_point === 'all');
}

export function pickNetworkAll(data: ApplianceMonitorData) {
  return data.network.find((item) => item.interface === 'all');
}

export function pickNpuAll(data: ApplianceMonitorData) {
  return data.npus.find((item) => item.device_id === 'all');
}

function compareNpuDeviceId(left: string, right: string): number {
  const leftId = Number(left);
  const rightId = Number(right);
  if (!Number.isNaN(leftId) && !Number.isNaN(rightId)) {
    return leftId - rightId;
  }
  return left.localeCompare(right, undefined, { numeric: true });
}

export function listNpuDevices(data: ApplianceMonitorData) {
  return data.npus
    .filter((item) => item.device_id !== 'all')
    .sort((left, right) => compareNpuDeviceId(left.device_id, right.device_id));
}

export function listDiskMounts(data: ApplianceMonitorData) {
  return data.disks.filter((item) => item.mount_point !== 'all');
}

export function formatHbmGigabytes(mb: number): string {
  if (mb <= 0) {
    return '0.0 GB';
  }
  return `${(mb / 1024).toFixed(1)} GB`;
}

export function getNpuHealthMeta(health: number): { tagClass: string; text: string } {
  if (health === 1) {
    return { tagClass: 'health-tag--healthy', text: '健康' };
  }
  if (health === 0) {
    return { tagClass: 'health-tag--unhealthy', text: '异常' };
  }
  return { tagClass: 'health-tag--unknown', text: '未知' };
}

export interface ApplianceMonitorViewModel {
  deviceName: string;
  modelName: string;
  uptimeText: string;
  updatedAt: string;
  cpuUsage: number;
  npuUsage: number;
  memoryUsage: number;
  memoryUsedText: string;
  memoryTotalText: string;
  memoryCapacity: BytePairLabel;
  diskUsage: number;
  diskUsedText: string;
  diskTotalText: string;
  diskCapacity: BytePairLabel;
  networkRxBytesPerSec: number;
  networkTxBytesPerSec: number;
}

export function mapApplianceMonitorToView(data: ApplianceMonitorData): ApplianceMonitorViewModel {
  const diskAll = pickDiskAll(data);
  const networkAll = pickNetworkAll(data);
  const npuAll = pickNpuAll(data);
  return {
    deviceName: data.system.hostname,
    modelName: data.system.product_name ?? data.cpu.model_name,
    uptimeText: formatUptimeSeconds(data.system.uptime_seconds),
    updatedAt: formatMonitorTimestamp(data.timestamp),
    cpuUsage: roundUsagePercent(data.cpu.usage),
    npuUsage: roundUsagePercent(npuAll?.usage ?? 0),
    memoryUsage: roundUsagePercent(data.memory.usage),
    memoryUsedText: formatBytes(data.memory.used_bytes),
    memoryTotalText: formatBytes(data.memory.total_bytes),
    memoryCapacity: formatBytePair(data.memory.used_bytes, data.memory.total_bytes),
    diskUsage: roundUsagePercent(diskAll?.usage ?? 0),
    diskUsedText: formatBytes(diskAll?.used_bytes ?? 0),
    diskTotalText: formatBytes(diskAll?.total_bytes ?? 0),
    diskCapacity: formatBytePair(diskAll?.used_bytes ?? 0, diskAll?.total_bytes ?? 0),
    networkRxBytesPerSec: networkAll?.rx_bytes_per_sec ?? 0,
    networkTxBytesPerSec: networkAll?.tx_bytes_per_sec ?? 0,
  };
}
