import { get, post, put, del } from './index';

// ==================== 类型定义 ====================

/** 模型状态 */
export type ModelStatus = 'success' | 'error' | 'warning';

/** LiteLLM 模型信息 */
export interface LiteLLMModelInfo {
  id?: string;
  db_model?: boolean;
  blocked?: boolean;
  description?: string;
  context_window?: number;
  key?: string;
  max_tokens?: number;
  max_input_tokens?: number;
  max_output_tokens?: number;
  litellm_provider?: string;
  mode?: string;
  [key: string]: unknown;
}

/** LiteLLM 模型参数 */
export interface LiteLLMParams {
  model: string;
  api_base?: string;
  api_key?: string;
  [key: string]: unknown;
}

/** 模型列表项（后端返回格式） */
export interface InferenceModelItem {
  id: string;
  model_name: string;
  litellm_params: LiteLLMParams;
  model_info: LiteLLMModelInfo;
  instance_url?: string;
  max_concurrent?: number;
  inference_engine?: string;
  grafana_job_name?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

/** 模型详情 */
export interface ModelDetail {
  id: string;
  model_name: string;
  litellm_params: LiteLLMParams;
  model_info: LiteLLMModelInfo;
  instance_url?: string;
  max_concurrent?: number;
  inference_engine?: string;
  grafana_job_name?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

/** 模型列表响应（后端返回格式） */
export interface ModelListResponse {
  total: number;
  page: number;
  page_size: number;
  items: InferenceModelItem[];
}

/** API Key 项（后端返回格式） */
export interface ApiKeyItem {
  key_name?: string;
  key_preview: string;
  key_alias: string;
  is_default?: boolean;
  bound_model?: string;
  created_at: string;
  expires_at?: string;
}

/** API Key 列表响应（后端返回格式） */
export interface ApiKeyListResponse {
  keys: ApiKeyItem[];
}

/** 创建 API Key 响应 */
export interface CreateApiKeyResponse {
  key: string;
  key_alias: string;
  uid: string;
  models: string[];
  expires?: string;
}

// ==================== API 函数 ====================

/** 获取 Gateway 配置 */
export async function fetchGatewayConfig() {
  return get<{ gateway_url: string }>('/api/v1/maas/config');
}

/** 获取模型列表 */
export async function fetchModelList(params?: { status?: string; keyword?: string }) {
  return get<ModelListResponse>('/api/v1/litellm/model', params);
}

/** 获取模型详情 */
export async function fetchModelDetail(id: string) {
  return get<ModelDetail>(`/api/v1/litellm/model/${id}`);
}

/** 更新模型信息 */
export async function updateModel(model_id: string, data: Partial<ModelDetail>) {
  return put<ModelDetail>(`/api/v1/litellm/model/${model_id}`, data);
}

/** 删除模型 */
export async function deleteModel(model_id: string) {
  return del(`/api/v1/litellm/model/${model_id}`);
}

/** 重启模型（文档规范中无此接口，保留供前端使用） */
export async function restartModel(model_id: string) {
  return post(`/api/v1/litellm/model/${model_id}/restart`);
}

/** 创建模型 */
export async function createModel(data: {
  model_name: string;
  litellm_params: LiteLLMParams;
  instance_url?: string;
  max_concurrent?: number;
  inference_engine?: string;
  model_info?: LiteLLMModelInfo;
}) {
  return post<InferenceModelItem>('/api/v1/litellm/model', data);
}

// ==================== API Key API 函数 ====================

/** 获取 API Key 列表 */
export async function fetchApiKeyList() {
  return get<ApiKeyListResponse>('/api/v1/litellm/key');
}

/** 创建 API Key */
export async function createApiKey(data: { key_name?: string; model?: string }) {
  return post<CreateApiKeyResponse>('/api/v1/litellm/key/generate', data);
}

/** 删除 API Key */
export async function deleteApiKey(key_alias: string) {
  return del(`/api/v1/litellm/key/${key_alias}`);
}

// ==================== 使用统计 API 函数 ====================

/** 使用统计概览响应 */
export interface UsageOverviewResponse {
  start_date: string;
  end_date: string;
  users: Array<{
    user_id: string;
    total_tokens: number;
    total_requests: number;
    total_cost: number;
  }>;
  daily: Array<{
    date: string;
    tokens: number;
    requests: number;
    cost: number;
    active_users: number;
  }>;
}

/** 获取使用统计概览 */
export async function fetchUsageOverview(params: {
  start_date: string;
  end_date: string;
}): Promise<UsageOverviewResponse> {
  return get<UsageOverviewResponse>('/api/v1/litellm/usage/overview', params);
}

/** 指定用户每日活动响应 */
export interface UserUsageDetailResponse {
  user_id: string;
  start_date: string;
  end_date: string;
  daily_activity: Array<{
    date: string;
    tokens: number;
    requests: number;
    cost: number;
  }>;
}

/** 获取指定用户每日活动（普通用户只能看自己） */
export async function fetchUserUsage(params: {
  user_id: string;
  start_date: string;
  end_date: string;
}): Promise<UserUsageDetailResponse> {
  return get<UserUsageDetailResponse>('/api/v1/litellm/usage/user', params);
}

/** 模型用量分布响应 */
export interface ModelUsageResponse {
  items: Array<{
    model: string;
    tokens: number;
    requests: number;
    cost: number;
    pct: number;
  }>;
}

/** 获取模型用量分布（管理员） */
export async function fetchUsageByModel(params: {
  start_date: string;
  end_date: string;
}): Promise<ModelUsageResponse> {
  return get<ModelUsageResponse>('/api/v1/litellm/usage/by-model', params);
}

/** 用户用量排行响应 */
export interface UserUsageRankResponse {
  items: Array<{
    user_id: string;
    username?: string | null;
    tokens: number;
    requests: number;
    cost: number;
  }>;
}

/** 获取用户用量排行（管理员） */
export async function fetchUsageByUser(params: {
  start_date: string;
  end_date: string;
  top?: number;
}): Promise<UserUsageRankResponse> {
  return get<UserUsageRankResponse>('/api/v1/litellm/usage/by-user', params);
}

/** 趋势数据响应 */
export interface TrendResponse {
  start_date: string;
  end_date: string;
  granularity: string;
  items: Array<{
    time: string;
    tokens: number;
    requests: number;
    cost: number;
  }>;
}

/** 获取使用趋势（普通用户只能看自己） */
export async function fetchUsageTrend(params: {
  start_date: string;
  end_date: string;
  granularity?: string;
  user_id?: string;
}): Promise<TrendResponse> {
  return get<TrendResponse>('/api/v1/litellm/usage/trend', { ...params, granularity: params.granularity || 'day' });
}
