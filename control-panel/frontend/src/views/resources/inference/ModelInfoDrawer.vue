<script setup lang="ts">
import { ref, watch } from 'vue';
import { ElDrawer, ElTag, ElIcon } from 'element-plus';
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

const formData = ref({ ...props.model });

watch(
  () => props.model,
  (val) => {
    if (val) formData.value = { ...val };
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
        </div>
      </div>

      <div class="info-section">
        <h3 class="info-section__title">服务信息</h3>
        <div class="info-grid">
          <ModelInfoRow label="实例URL" :value="model.instance_url" />
          <ModelInfoRow label="最大并发数" :value="model.max_concurrent?.toString()" />
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
            <label class="form-label">模型类型</label>
            <input v-model="formData.litellm_params.model" class="form-input" />
          </div>
          <div class="form-group">
            <label class="form-label">API Base</label>
            <input v-model="formData.litellm_params.api_base" class="form-input" />
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
            <label class="form-label">实例URL</label>
            <input v-model="formData.instance_url" class="form-input" />
          </div>
          <div class="form-group">
            <label class="form-label">最大并发数</label>
            <input v-model="formData.max_concurrent" class="form-input" type="number" />
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
        <button class="btn btn--primary" @click="emit('save', formData)">保存更改</button>
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
