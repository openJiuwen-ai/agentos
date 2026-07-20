<script setup lang="ts">
import { ref, watch } from 'vue';
import { ElDrawer, ElIcon } from 'element-plus';
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
  export: [];
}>();

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

// 从litellm_params.model中解析出部署模型名称（去掉provider前缀）
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
  // 根据部署模型名称和部署框架构建model字段
  const modelIdentifier = `openai/${formData.value.deployName}`;

  const saveData: Partial<ModelDetail> = {
    model_name: formData.value.model_name,
    litellm_params: {
      model: modelIdentifier,
      api_base: formData.value.litellm_params.api_base,
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
    <!-- Model Header -->
    <div class="model-header" v-if="model">
      <div class="model-header__icon">
        <el-icon :size="32" color="#2563eb"><Monitor /></el-icon>
      </div>
      <span class="model-header__name">{{ model.model_name }}</span>
      <button class="model-header__copy" @click="copyModelName" title="复制模型名称">
        <el-icon :size="16"><CopyDocument /></el-icon>
      </button>
    </div>

    <!-- View Mode -->
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
          <ModelInfoRow label="创建时间" :value="model.created_at" />
          <ModelInfoRow label="更新时间" :value="model.updated_at" />
        </div>
      </div>
    </template>

    <!-- Edit Mode -->
    <template v-if="mode === 'edit' && model">
      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('basic')">
          <el-icon :style="{ transform: sections.basic ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
          基础信息
        </h3>
        <div v-show="sections.basic" class="form-grid">
          <div class="form-group">
            <label class="form-label form-label--required">模型名称</label>
            <input v-model="formData.model_name" class="form-input" />
          </div>
          <div class="form-group">
            <label class="form-label form-label--required">部署模型名称</label>
            <input v-model="formData.deployName" class="form-input" placeholder="例如: gpt-4" />
            <span class="form-hint">仅支持Openai API格式，模型名将自动添加前缀: openai/</span>
          </div>
          <div class="form-group">
            <label class="form-label">API Base</label>
            <input v-model="formData.litellm_params.api_base" class="form-input" placeholder="例如: http://localhost:8000" />
          </div>
          <div class="form-group">
            <label class="form-label">上下文长度</label>
            <input v-model="formData.model_info.context_window" class="form-input" type="number" placeholder="例如: 4096" />
          </div>
          <div class="form-group" style="grid-column: span 2">
            <label class="form-label">模型描述</label>
            <textarea v-model="formData.model_info.description" class="form-textarea" placeholder="简要描述该模型的用途和特点..."></textarea>
          </div>
        </div>
      </div>

      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('deploy')">
          <el-icon :style="{ transform: sections.deploy ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
          部署信息
        </h3>
        <div v-show="sections.deploy" class="form-grid">
          <div class="form-group">
            <label class="form-label form-label--required">部署框架</label>
            <select v-model="formData.deployFramework" class="form-select">
              <option value="vLLM">vLLM</option>
              <option value="SGLang">SGLang</option>
            </select>
          </div>
        </div>
      </div>

      <div class="info-section">
        <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('service')">
          <el-icon :style="{ transform: sections.service ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
          服务信息
        </h3>
        <div v-show="sections.service" class="form-grid">
          <div class="form-group">
            <label class="form-label">模型监控URL</label>
            <input v-model="formData.instance_url" class="form-input" placeholder="请输入模型监控URL" />
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <template v-if="mode === 'view'">
        <button class="btn" @click="emit('export')">导出</button>
        <button class="btn btn--primary" @click="emit('edit')">编辑信息</button>
      </template>
      <template v-else>
        <button class="btn" @click="emit('close')">取消</button>
        <button class="btn btn--primary" @click="handleSave">保存更改</button>
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
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  margin-bottom: 20px;
}

.model-header__icon {
  flex-shrink: 0;
}

.model-header__name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}

.model-header__copy {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary, #6b7280);
  transition: all 0.2s;
}

.model-header__copy:hover {
  background: var(--bg-hover, #f3f4f6);
  color: var(--text-primary, #1f2937);
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
  color: var(--text-primary, #1f2937);
}

.info-section__title--clickable {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
}

.info-section__title--clickable svg {
  transition: transform 0.2s;
  flex-shrink: 0;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
}

.form-label--required::before {
  content: '*';
  color: #ef4444;
  margin-right: 4px;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  font-size: 14px;
  border: 1px solid var(--border-color, #d1d5db);
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary, #1f2937);
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.form-textarea {
  min-height: 80px;
  resize: vertical;
}

.form-hint {
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
}

.btn {
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid var(--border-color, #d1d5db);
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary, #1f2937);
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover {
  background: var(--bg-hover, #f9fafb);
}

.btn--primary {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.btn--primary:hover {
  background: #1d4ed8;
}
</style>
