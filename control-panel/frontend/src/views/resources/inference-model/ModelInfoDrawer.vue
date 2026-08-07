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
} from 'element-plus';
import { ArrowDown, CopyDocument, Monitor } from '@element-plus/icons-vue';
import ModelInfoRow from './ModelInfoRow.vue';
import type { ModelDetail } from '@/api/inference';

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

interface FormData {
  id: string;
  model_name: string;
  deployName: string;
  deployFramework: string;
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
  instance_url?: string;
  max_concurrent?: number;
  inference_engine?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

function parseDeployName(model: string): string {
  if (!model) return '';
  const slashIndex = model.indexOf('/');
  return slashIndex >= 0 ? model.substring(slashIndex + 1) : model;
}

const formData = ref<FormData>({
  id: props.model?.id ?? '',
  model_name: props.model?.model_name ?? '',
  deployName: parseDeployName(props.model?.litellm_params?.model ?? ''),
  deployFramework: props.model?.inference_engine ?? 'vLLM',
  model_info: {
    ...props.model?.model_info,
    id: props.model?.model_info?.id ?? props.model?.id ?? '',
    description: props.model?.model_info?.description ?? '',
    context_window: props.model?.model_info?.context_window ?? null,
  },
  litellm_params: {
    ...props.model?.litellm_params,
    model: props.model?.litellm_params?.model ?? '',
    api_base: props.model?.litellm_params?.api_base ?? '',
    api_key: props.model?.litellm_params?.api_key ?? '',
  },
  instance_url: props.model?.instance_url,
  max_concurrent: props.model?.max_concurrent,
  inference_engine: props.model?.inference_engine,
  created_at: props.model?.created_at,
  updated_at: props.model?.updated_at,
});

watch(
  () => props.model,
  (val) => {
    if (val) {
      formData.value = {
        id: val.id,
        model_name: val.model_name,
        deployName: parseDeployName(val.litellm_params?.model ?? ''),
        deployFramework: val.inference_engine ?? 'vLLM',
        model_info: {
          ...val.model_info,
          id: val.model_info?.id ?? val.id,
          description: val.model_info?.description ?? '',
          context_window: val.model_info?.context_window ?? null,
        },
        litellm_params: {
          ...val.litellm_params,
          model: val.litellm_params?.model ?? '',
          api_base: val.litellm_params?.api_base ?? '',
          api_key: val.litellm_params?.api_key ?? '',
        },
        instance_url: val.instance_url,
        max_concurrent: val.max_concurrent,
        inference_engine: val.inference_engine,
        created_at: val.created_at,
        updated_at: val.updated_at,
      };
    }
  },
  { immediate: true },
);

const sections = ref({
  basic: true,
  deploy: true,
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

function handleSave() {
  const modelIdentifier = `openai/${formData.value.deployName}`;

  const saveData: Partial<ModelDetail> = {
    model_name: formData.value.model_name,
    litellm_params: {
      model: modelIdentifier,
      api_base: formData.value.litellm_params.api_base,
      ...(formData.value.litellm_params.api_key ? { api_key: formData.value.litellm_params.api_key } : {}),
    },
    model_info: {
      id: formData.value.model_info.id,
      description: formData.value.model_info.description,
      context_window: formData.value.model_info.context_window,
    } as any,
    instance_url: formData.value.instance_url,
    max_concurrent: formData.value.max_concurrent,
    inference_engine: formData.value.deployFramework,
  };
  emit('save', saveData);
}
</script>

<template>
  <ElDrawer :model-value="visible" title="模型信息" size="480px" @close="emit('close')">
    <div class="model-header" v-if="model">
      <div class="model-header__icon">
        <el-icon :size="32" color="#2563eb"><Monitor /></el-icon>
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
          <ModelInfoRow label="模型描述" :value="model.model_info?.description" />
        </div>
      </div>

      <div class="info-section">
        <h3 class="info-section__title">服务信息</h3>
        <div class="info-grid">
          <ModelInfoRow label="模型监控URL" :value="model.instance_url" />
          <ModelInfoRow label="创建时间" :value="formatDateTime(model.created_at)" />
          <ModelInfoRow label="更新时间" :value="formatDateTime(model.updated_at)" />
        </div>
      </div>
    </template>

    <template v-if="mode === 'edit' && model">
      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('basic')">
          <el-icon :style="{ transform: sections.basic ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"
            ><ArrowDown
          /></el-icon>
          基础信息
        </h3>
        <ElForm v-show="sections.basic" :model="formData" label-position="top" class="form-grid">
          <ElFormItem label="模型名称" required class="form-grid__item">
            <ElInput v-model="formData.model_name" />
          </ElFormItem>
          <ElFormItem label="部署模型名称" required class="form-grid__item">
            <ElInput v-model="formData.deployName" placeholder="例如: gpt-4" />
            <span class="form-hint">仅支持Openai API格式，模型名将自动添加前缀: openai/</span>
          </ElFormItem>
          <ElFormItem label="API Base" class="form-grid__item">
            <ElInput v-model="formData.litellm_params.api_base" placeholder="例如: http://localhost:8000/v1" />
          </ElFormItem>
          <ElFormItem label="API Key" class="form-grid__item">
            <ElInput
              v-model="formData.litellm_params.api_key"
              type="password"
              placeholder="调用模型所需的API Key（可选）"
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
              placeholder="简要描述该模型的用途和特点..."
            />
          </ElFormItem>
        </ElForm>
      </div>

      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('deploy')">
          <el-icon
            :style="{ transform: sections.deploy ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"
            ><ArrowDown
          /></el-icon>
          部署信息
        </h3>
        <ElForm v-show="sections.deploy" :model="formData" label-position="top" class="form-grid">
          <ElFormItem label="部署框架" required class="form-grid__item">
            <ElSelect v-model="formData.deployFramework" placeholder="请选择部署框架">
              <ElOption label="vLLM" value="vLLM" />
              <ElOption label="SGLang" value="SGLang" />
            </ElSelect>
          </ElFormItem>
        </ElForm>
      </div>

      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('service')">
          <el-icon
            :style="{ transform: sections.service ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"
            ><ArrowDown
          /></el-icon>
          服务信息
        </h3>
        <ElForm v-show="sections.service" :model="formData" label-position="top" class="form-grid">
          <ElFormItem label="模型监控URL" class="form-grid__item form-grid__item--full">
            <ElInput v-model="formData.instance_url" placeholder="请输入模型监控URL" />
          </ElFormItem>
        </ElForm>
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

.form-field {
  width: 100%;
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
