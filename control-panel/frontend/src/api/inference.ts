import { get, post, put, del } from './index';

// ==================== 类型定义 ====================

/** 模型状态 */
export type ModelStatus = 'success' | 'error' | 'warning';

/** LiteLLM 模型信息 */
export interface LiteLLMModelInfo {
  id: string;
  db_model?: boolean;
  blocked?: boolean;
  description?: string;
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
  key_preview: string;
  key_alias: string;
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

/** 获取模型列表 */
export async function fetchModelList(params?: { status?: string; keyword?: string }) {
  return get<ModelListResponse>('/api/v1/litellm/model', params);
}

/** 获取模型详情 */
export async function fetchModelDetail(id: string) {
  return get<ModelDetail>(`/api/v1/litellm/model/${id}`);
}

/** 更新模型信息 */
export async function updateModel(model_name: string, data: Partial<ModelDetail>) {
  return put<ModelDetail>(`/api/v1/litellm/model/${model_name}`, data);
}

/** 删除模型 */
export async function deleteModel(model_name: string) {
  return del(`/api/v1/litellm/model/${model_name}`);
}

/** 重启模型（文档规范中无此接口，保留供前端使用） */
export async function restartModel(model_name: string) {
  return post(`/api/v1/litellm/model/${model_name}/restart`);
}

/** 创建模型 */
export async function createModel(data: { model_name: string; litellm_params: LiteLLMParams; instance_url?: string }) {
  return post<InferenceModelItem>('/api/v1/litellm/model', data);
}

// ==================== API Key API 函数 ====================

/** 获取 API Key 列表 */
export async function fetchApiKeyList() {
  return get<ApiKeyListResponse>('/api/v1/litellm/key');
}

/** 创建 API Key */
export async function createApiKey(data: { model?: string }) {
  return post<CreateApiKeyResponse>('/api/v1/litellm/key/generate', data);
}

/** 删除 API Key */
export async function deleteApiKey(key_alias: string) {
  return del(`/api/v1/litellm/key/${key_alias}`);
}
