import { post, get } from './index';

const BASE = '/api/v1/thirdparty_agent';

/** 已上传框架的基本信息 */
export interface FrameworkItem {
  agent_name: string;
  version: string;
  display_name: string;
  entrypoint: string;
  build_status?: string;
  build_task_id?: string;
}

/** listFrameworks 查询参数 */
export interface ListFrameworksParams {
  framework?: string;
  size?: number;
  page?: number;
}

/** listFrameworks 分页响应 */
export interface ListFrameworksResponse {
  items: FrameworkItem[];
  total: number;
}

/** 构建任务状态 */
export interface BuildTaskStatus {
  task_id: string;
  status: 'pending' | 'building' | 'done' | 'failed';
  progress: number;
  image?: string;
  image_digest?: string;
  started_at?: string;
  finished_at?: string;
  registered: boolean;
  error_message?: string;
}

/** POST /installers — 上传 tgz 包 */
export function uploadPackage(file: File) {
  const fd = new FormData();
  fd.append('package', file);
  return post<FrameworkItem>(`${BASE}/installers`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60 * 60 * 1000,  // 1 hour
  });
}

/** GET /installers — 获取已上传框架列表（支持 framework 搜索 + 分页） */
export function listFrameworks(params: ListFrameworksParams = {}) {
  return get<ListFrameworksResponse>(`${BASE}/installers`, {
    framework: params.framework || '',
    size: params.size ?? 20,
    page: params.page ?? 1,
  });
}

/** POST /build_tasks — 触发构建 */
export function triggerBuild(body: { agent_name: string; version: string; display_name: string; entrypoint: string }) {
  return post<{ task_id: string; status: string; created_at?: string }>(`${BASE}/build_tasks`, body);
}

/** GET /build_tasks/{task_id} — 查询构建状态 */
export function getBuildStatus(taskId: string) {
  return get<BuildTaskStatus>(`${BASE}/build_tasks/${taskId}`);
}
