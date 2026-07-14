/** 后端统一响应结构，可按实际接口调整 */
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

// ==================== 推理模型相关类型 ====================

/** 模型状态 */
export type ModelStatus = 'success' | 'error' | 'warning';

/** 模型列表项 */
export interface InferenceModelItem {
  id: string;
  name: string;
  iconSrc?: string;
  status: ModelStatus;
  statusText: string;
  tags?: string[];
  e2eP95: string;
  e2eTrend?: string;
  todayCalls: string;
  todayTokens: string;
  meta?: string[];
}

/** 模型详情 */
export interface ModelDetail {
  id: string;
  name: string;
  type: string;
  contextLength: number;
  paramSize?: string;
  tags?: string[];
  description?: string;
  deployName: string;
  deployFramework: string;
  serverLocation: string;
  modelName: string;
  serviceIp?: string;
  servicePort?: number;
  serviceUrl?: string;
  computeStrategy?: string;
  maxConcurrency?: number;
  maxWaitConcurrency?: number;
  healthCheckUrl?: string;
  metricsUrl?: string;
  status: ModelStatus;
  statusText: string;
  instanceName?: string;
  runtime?: string;
  createdAt?: string;
  updatedAt?: string;
}

/** 模型列表响应 */
export interface ModelListResponse {
  list: InferenceModelItem[];
  total: number;
}

// ==================== API Key 相关类型 ====================

/** API Key 项 */
export interface ApiKeyItem {
  id: number;
  name: string;
  key: string;
  createdAt: string;
}

/** API Key 列表响应 */
export interface ApiKeyListResponse {
  list: ApiKeyItem[];
  total: number;
}
