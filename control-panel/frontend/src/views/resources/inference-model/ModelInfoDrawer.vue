<script setup lang="ts">
import { ref, watch } from 'vue';
import {
  ElButton,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElMessage,
} from 'element-plus';
import { ArrowDown, CopyDocument, Monitor, Plus, Delete } from '@element-plus/icons-vue';
import ModelInfoRow from './ModelInfoRow.vue';
import type { MetricsEndpoint, ModelDetail } from '@/api/inference';
import { useAuth } from '@/composables/useAuth';

const { effectiveIsAdmin: isAdmin } = useAuth();

const props = defineProps<{
  visible: boolean;
  mode: 'view' | 'edit';
  model?: ModelDetail | null;
}>();

const emit = defineEmits<{
  close: [];
  save: [data: Partial<ModelDetail>];
  edit: [];
}>();

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '--';
  const date = new Date(value);
  return isNaN(date.getTime()) ? '--' : date.toLocaleString();
}

interface EndpointFormItem {
  inference_engine: string;
  instance_url: string;
}

interface FormData {
  id: string;
  model_name: string;
  deployName: string;
  litellm_params: {
    model: string;
    api_base: string;
    api_key?: string;
    [key: string]: unknown;
  };
  model_info: {
    id: string;
    description: string;
    context_window: number | null;
    [key: string]: unknown;
  };
  metrics_endpoints: EndpointFormItem[];
  max_concurrent?: number;
  created_at?: string;
  updated_at?: string;
}

function parseDeployName(model: string): string {
  if (!model) return '';
  const slashIndex = model.indexOf('/');
  return slashIndex >= 0 ? model.substring(slashIndex + 1) : model;
}

function cloneEndpoints(list?: MetricsEndpoint[] | null): EndpointFormItem[] {
  if (!list?.length) return [];
  return list.map((ep) => ({
    inference_engine: ep.inference_engine || 'vLLM',
    instance_url: ep.instance_url || '',
  }));
}

function buildForm(model?: ModelDetail | null): FormData {
  return {
    id: model?.id ?? '',
    model_name: model?.model_name ?? '',
    deployName: parseDeployName(model?.litellm_params?.model ?? ''),
    model_info: {
      ...model?.model_info,
      id: model?.model_info?.id ?? model?.id ?? '',
      description: model?.model_info?.description ?? '',
      context_window: model?.model_info?.context_window ?? null,
    },
    litellm_params: {
      ...model?.litellm_params,
      model: model?.litellm_params?.model ?? '',
      api_base: model?.litellm_params?.api_base ?? '',
      api_key: model?.litellm_params?.api_key ?? '',
    },
    metrics_endpoints: cloneEndpoints(model?.metrics_endpoints),
    max_concurrent: model?.max_concurrent,
    created_at: model?.created_at,
    updated_at: model?.updated_at,
  };
}

const formData = ref<FormData>(buildForm(props.model));

watch(
  () => props.model,
  (val) => {
    if (val) formData.value = buildForm(val);
  },
  { immediate: true },
);

const sections = ref({
  basic: true,
  service: true,
});

function toggleSection(key: keyof typeof sections.value) {
  sections.value[key] = !sections.value[key];
}

function copyModelName() {
  if (props.model?.model_name) {
    navigator.clipboard.writeText(props.model.model_name);
  }
}

function addEndpoint() {
  formData.value.metrics_endpoints.push({
    inference_engine: 'vLLM',
    instance_url: '',
  });
}

function removeEndpoint(index: number) {
  formData.value.metrics_endpoints.splice(index, 1);
}

function handleSave() {
  const deployName = formData.value.deployName.trim();
  const apiKey = formData.value.litellm_params.api_key?.trim();
  const modelIdentifier = `openai/${deployName}`;

  const endpoints: MetricsEndpoint[] = [];
  for (const ep of formData.value.metrics_endpoints) {
    const engine = ep.inference_engine?.trim();
    const url = ep.instance_url?.trim();
    if (!engine && !url) continue;
    if (!engine || !url) {
      ElMessage.warning('监控节点需同时填写部署框架和模型监控 URL，或删除该行');
      return;
    }
    endpoints.push({ inference_engine: engine, instance_url: url });
  }

  const saveData: Partial<ModelDetail> = {
    model_name: formData.value.model_name.trim(),
    litellm_params: {
      model: modelIdentifier,
      api_base: formData.value.litellm_params.api_base.trim(),
      ...(apiKey ? { api_key: apiKey } : {}),
    },
    model_info: {
      id: formData.value.model_info.id,
      description: formData.value.model_info.description.trim(),
      context_window: formData.value.model_info.context_window,
    } as ModelDetail['model_info'],
    metrics_endpoints: endpoints,
    max_concurrent: formData.value.max_concurrent,
  };
  emit('save', saveData);
}
</script>

<template>
  <ElDrawer :model-value="visible" title="模型信息" size="480px" @close="emit('close')">
    <div v-if="model" class="model-header">
      <div class="model-header__icon">
        <ElIcon :size="32" color="#2563eb"><Monitor /></ElIcon>
      </div>
      <span class="model-header__name">{{ model.model_name }}</span>
      <ElButton class="model-header__copy" text :icon="CopyDocument" title="复制模型名称" @click="copyModelName" />
    </div>

    <template v-if="mode === 'view' && model">
      <div class="info-section">
        <h3 class="info-section__title">基础信息</h3>
        <div class="info-grid">
          <ModelInfoRow label="模型名称" :value="model.model_name" />
          <ModelInfoRow label="模型类型" :value="model.litellm_params?.model" />
          <ModelInfoRow label="API Base" :value="model.litellm_params?.api_base" />
        </div>
      </div>

      <div class="info-section">
        <h3 class="info-section__title">监控信息</h3>
        <div v-if="isAdmin" class="info-grid">
          <template v-if="model.metrics_endpoints?.length">
            <div
              v-for="(ep, idx) in model.metrics_endpoints"
              :key="`${ep.instance_url}-${idx}`"
              class="endpoint-view form-grid__item--full"
            >
              <ModelInfoRow label="部署框架" :value="ep.inference_engine" />
              <ModelInfoRow label="模型监控 URL" :value="ep.instance_url" span="full" />
            </div>
          </template>
          <ModelInfoRow v-else label="监控节点" value="未配置" span="full" />
        </div>
        <div class="info-grid" style="margin-top: 12px">
          <ModelInfoRow label="创建时间" :value="formatDateTime(model.created_at)" />
          <ModelInfoRow label="更新时间" :value="formatDateTime(model.updated_at)" />
        </div>
      </div>
    </template>

    <template v-if="mode === 'edit' && model">
      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('basic')">
          <ElIcon :style="{ transform: sections.basic ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }">
            <ArrowDown />
          </ElIcon>
          基础信息
        </h3>
        <ElForm v-show="sections.basic" :model="formData" label-position="top" class="form-grid">
          <ElFormItem label="模型名称" required class="form-grid__item">
            <ElInput v-model="formData.model_name" />
          </ElFormItem>
          <ElFormItem label="部署模型名称" required class="form-grid__item">
            <ElInput v-model="formData.deployName" placeholder="例如: gpt-4" />
            <span class="form-hint">仅支持 Openai API 格式，模型名将自动添加前缀: openai/</span>
          </ElFormItem>
          <ElFormItem label="API Base" class="form-grid__item">
            <ElInput v-model="formData.litellm_params.api_base" placeholder="例如: http://localhost:8000/v1" />
          </ElFormItem>
          <ElFormItem label="API Key" class="form-grid__item">
            <ElInput
              v-model="formData.litellm_params.api_key"
              type="password"
              placeholder="调用模型所需的 API Key（可选）"
            />
            <span class="form-hint">用于调用第三方模型服务的认证密钥</span>
          </ElFormItem>
          <ElFormItem label="上下文长度" class="form-grid__item">
            <ElInputNumber
              v-model="formData.model_info.context_window"
              :controls="false"
              :min="0"
              :max="2147483647"
              :precision="0"
              :step="1"
              placeholder="例如: 4096"
              class="form-field"
            />
          </ElFormItem>
          <ElFormItem label="模型描述" class="form-grid__item form-grid__item--full">
            <ElInput
              v-model="formData.model_info.description"
              type="textarea"
              :rows="4"
              resize="vertical"
              maxlength="500"
              show-word-limit
              placeholder="简要描述该模型的用途和特点..."
            />
          </ElFormItem>
        </ElForm>
      </div>

      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('service')">
          <ElIcon
            :style="{ transform: sections.service ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"
          >
            <ArrowDown />
          </ElIcon>
          监控信息
        </h3>
        <div v-show="sections.service">
          <p class="form-hint endpoint-hint">可添加多个监控节点（双机部署）；允许为空。Grafana 默认看第一项。</p>
          <div v-for="(ep, index) in formData.metrics_endpoints" :key="index" class="endpoint-row">
            <ElForm :model="ep" label-position="top" class="form-grid">
              <ElFormItem label="部署框架" required class="form-grid__item">
                <ElSelect v-model="ep.inference_engine" placeholder="请选择部署框架">
                  <ElOption label="vLLM" value="vLLM" />
                  <ElOption label="SGLang" value="SGLang" />
                </ElSelect>
              </ElFormItem>
              <ElFormItem label="模型监控 URL" required class="form-grid__item">
                <ElInput v-model="ep.instance_url" placeholder="例如: http://192.168.1.10:8000" />
              </ElFormItem>
            </ElForm>
            <ElButton
              class="endpoint-row__remove"
              text
              type="danger"
              :icon="Delete"
              title="删除该监控节点"
              @click="removeEndpoint(index)"
            />
          </div>
          <ElButton class="endpoint-add" :icon="Plus" @click="addEndpoint">添加监控节点</ElButton>
        </div>
      </div>
    </template>

    <template #footer>
      <template v-if="mode === 'view'">
        <ElButton type="primary" @click="emit('edit')">编辑信息</ElButton>
      </template>
      <template v-else>
        <ElButton @click="emit('close')">取消</ElButton>
        <ElButton type="primary" @click="handleSave">保存更改</ElButton>
      </template>
    </template>
  </ElDrawer>
</template>

<style scoped>
.model-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-separator, #e5e7eb);
  margin-bottom: 20px;
}

.model-header__icon {
  flex-shrink: 0;
}

.model-header__name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.model-header__copy {
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-secondary);
}

.info-section {
  margin-bottom: 24px;
}

.info-section:last-child {
  margin-bottom: 0;
}

.info-section__title {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.info-section__title--clickable {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex: 1;
  min-width: 0;
}

.form-grid__item {
  margin-bottom: 0;
}

.form-grid__item--full {
  grid-column: span 2;
}

.form-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.endpoint-hint {
  margin: 0 0 12px;
}

.form-field {
  width: 100%;
}

.endpoint-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid var(--border-separator, #e5e7eb);
  border-radius: 8px;
}

.endpoint-row__remove {
  margin-top: 28px;
  flex-shrink: 0;
}

.endpoint-add {
  width: 100%;
}

.endpoint-view {
  display: contents;
}

.form-grid :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-grid :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
}

.form-grid :deep(.el-input-number .el-input__inner) {
  text-align: left;
}
</style>
