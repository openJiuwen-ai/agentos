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
  });
}

/** GET /installers — 获取已上传框架列表 */
export function listFrameworks() {
  return get<FrameworkItem[]>(`${BASE}/installers`);
}

/** POST /build_tasks — 触发构建 */
export function triggerBuild(body: { agent_name: string; version: string; display_name: string; entrypoint: string }) {
  return post<{ task_id: string; status: string; created_at?: string }>(`${BASE}/build_tasks`, body);
}

/** GET /build_tasks/{task_id} — 查询构建状态 */
export function getBuildStatus(taskId: string) {
  return get<BuildTaskStatus>(`${BASE}/build_tasks/${taskId}`);
}
