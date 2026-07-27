import type { AxiosRequestConfig } from 'axios';
import { get } from './index';

export interface InstanceEntry {
  service_id: string;
  framework: string;
  framework_version: string;
  address: string;
  node: string;
  user: string;
  created_at: string | null;
  last_active_at: string | null;
  status: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  overview_total: number;
  overview_running: number;
  overview_abnormal: number;
  overview_stopped: number;
}

export interface InstanceQuery {
  page?: number;
  size?: number;
  sort?: string;
  keyword?: string;
  status?: string;
  framework?: string;
  refresh?: boolean;
}

/** GET /api/v1/agent/instances — admin: 分页查看全部 agent 实例 */
export function fetchInstances(
  params?: InstanceQuery,
  config?: AxiosRequestConfig,
): Promise<Paginated<InstanceEntry>> {
  return get<Paginated<InstanceEntry>>('/api/v1/agent/instances', params, config);
}
