import { get, post, put, del } from './index';

// ==================== 类型定义 ====================

/** 配置模板 */
export interface NodeServiceTemplate {
  name: string;
  description: string;
  source: 'system' | 'user';
  config?: NodeServiceConfig;
}

/** 模板列表响应 */
export interface TemplateListResponse {
  templates: NodeServiceTemplate[];
}

/** 节点服务配置 — 按功能域分组 */
export interface NodeServiceConfig {
  model: {
    weight_path: string;
    model_path: string;
    model_name: string;
  };
  deploy: {
    image: string;
    npu_num: number;
  };
  parallel: {
    tensor_parallel_size: number;
    data_parallel_size: number;
    enable_expert_parallel: boolean;
    gpu_memory_utilization: number;
    quantization: string;
  };
  inference: {
    max_model_len: number;
    max_num_batched_tokens: number;
    max_num_seqs: number;
    enforce_eager: boolean;
  };
  format: {
    tokenizer_mode: string;
    tool_call_parser: string;
    reasoning_parser: string;
    trust_remote_code: boolean;
  };
  ports: {
    controller_port: number;
    coordinator_infer_port: number;
    coordinator_mgmt_port: number;
    coordinator_obs_port: number;
    node_manager_port: number;
    base_port: number;
  };
}

/** 启动进度 */
export interface StartProgress {
  status: string;
  message: string;
  error: string | null;
}

/** 节点服务状态 */
export interface NodeServiceStatus {
  container: string;
  engine: string;
  config?: NodeServiceConfig;
  recent_logs?: string[];
  start_progress?: StartProgress;
}

/** 健康检查响应 */
export interface NodeServiceHealth {
  healthy: boolean;
  container: string;
}

/** 日志响应 */
export interface NodeServiceLogsResponse {
  logs: string[];
}

// ==================== API 函数 ====================

const BASE = '/api/v1/node-service';

/** 获取节点配置 */
export async function fetchNodeConfig(node: string) {
  return get<NodeServiceConfig>(`${BASE}/config`, { node });
}

/** 更新节点配置（merge 语义） */
export async function updateNodeConfig(node: string, data: Partial<NodeServiceConfig>) {
  return put(`${BASE}/config`, data, { params: { node } });
}

/** 启动推理服务 */
export async function startNodeService(node: string, configOverride?: Partial<NodeServiceConfig>) {
  return post(`${BASE}/start`, configOverride || {}, { params: { node } });
}

/** 停止推理服务 */
export async function stopNodeService(node: string) {
  return post(`${BASE}/stop`, undefined, { params: { node } });
}

/** 重启推理服务 */
export async function restartNodeService(node: string, configOverride?: Partial<NodeServiceConfig>) {
  return post(`${BASE}/restart`, configOverride || {}, { params: { node } });
}

/** 获取节点状态 */
export async function fetchNodeStatus(node: string) {
  return get<NodeServiceStatus>(`${BASE}/status`, { node });
}

/** 获取节点健康状态 */
export async function fetchNodeHealth(node: string) {
  return get<NodeServiceHealth>(`${BASE}/health`, { node });
}

/** 获取节点日志 */
export async function fetchNodeLogs(node: string, lines = 100) {
  return get<NodeServiceLogsResponse>(`${BASE}/logs`, { node, lines });
}

/** 获取模板列表 */
export async function fetchTemplates(node: string) {
  return get<TemplateListResponse>(`${BASE}/templates`, { node });
}

/** 获取指定模板内容 */
export async function fetchTemplateContent(node: string, name: string) {
  return get<NodeServiceTemplate>(`${BASE}/templates/${encodeURIComponent(name)}`, { node });
}

/** 保存当前配置为模板 */
export async function saveTemplate(node: string, data: { name: string; description: string }) {
  return post(`${BASE}/templates`, data, { params: { node } });
}

/** 删除用户自定义模板 */
export async function deleteTemplate(node: string, name: string) {
  return del(`${BASE}/templates/${encodeURIComponent(name)}`, { node });
}

/** 应用模板（覆盖当前 user_config + 简化配置） */
export async function applyTemplate(node: string, name: string) {
  return post(`${BASE}/config/apply-template`, { name }, { params: { node } });
}
