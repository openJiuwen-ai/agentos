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
import { ArrowDown, Plus, Delete } from '@element-plus/icons-vue';
import type { MetricsEndpoint } from '@/api/inference';

interface EndpointFormItem {
  inference_engine: string;
  instance_url: string;
}

interface ModelFormData {
  name: string;
  contextLength: number | null;
  description: string;
  deployName: string;
  apiKey: string | undefined;
  serviceUrl: string;
  metrics_endpoints: EndpointFormItem[];
}

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  close: [];
  save: [data: ModelFormData];
}>();

const defaultFormData = (): ModelFormData => ({
  name: '',
  contextLength: null,
  description: '',
  deployName: '',
  apiKey: undefined,
  serviceUrl: '',
  metrics_endpoints: [],
});

const formData = ref<ModelFormData>(defaultFormData());

watch(
  () => props.visible,
  (val) => {
    if (val) formData.value = defaultFormData();
  },
);

const sections = ref({
  basic: true,
  deploy: true,
  service: true,
});

function toggleSection(key: keyof typeof sections.value) {
  sections.value[key] = !sections.value[key];
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

  emit('save', {
    ...formData.value,
    name: formData.value.name.trim(),
    description: formData.value.description.trim(),
    deployName: formData.value.deployName.trim(),
    apiKey: formData.value.apiKey?.trim(),
    serviceUrl: formData.value.serviceUrl.trim(),
    metrics_endpoints: endpoints,
  });
  emit('close');
}
</script>

<template>
  <ElDrawer :model-value="visible" title="添加模型" size="480px" @close="emit('close')">
    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('basic')">
        <ElIcon :style="{ transform: sections.basic ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }">
          <ArrowDown />
        </ElIcon>
        基础信息
      </h3>
      <ElForm v-show="sections.basic" :model="formData" label-position="top" class="form-grid">
        <ElFormItem label="模型名称" required class="form-grid__item">
          <ElInput v-model="formData.name" placeholder="请输入模型名称" />
        </ElFormItem>
        <ElFormItem label="上下文长度" class="form-grid__item">
          <ElInputNumber
            v-model="formData.contextLength"
            :controls="false"
            :min="0"
            :max="2147483647"
            :precision="0"
            :step="1"
            placeholder="请输入上下文长度"
            class="form-field"
          />
        </ElFormItem>
        <ElFormItem label="模型描述" class="form-grid__item form-grid__item--full">
          <ElInput
            v-model="formData.description"
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
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('deploy')">
        <ElIcon :style="{ transform: sections.deploy ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }">
          <ArrowDown />
        </ElIcon>
        部署信息
      </h3>
      <ElForm v-show="sections.deploy" :model="formData" label-position="top" class="form-grid">
        <ElFormItem label="部署模型名称" required class="form-grid__item form-grid__item--full">
          <ElInput v-model="formData.deployName" placeholder="例如: gpt-4" />
          <span class="form-hint">仅支持 OpenAI API 格式，模型名将自动添加前缀: openai/</span>
        </ElFormItem>
        <ElFormItem label="API Key" class="form-grid__item form-grid__item--full">
          <ElInput v-model="formData.apiKey" type="password" placeholder="调用模型所需的 API Key（可选）" />
          <span class="form-hint">用于调用第三方模型服务的认证密钥</span>
        </ElFormItem>
      </ElForm>
    </div>

    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('service')">
        <ElIcon :style="{ transform: sections.service ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }">
          <ArrowDown />
        </ElIcon>
        服务访问信息
      </h3>
      <ElForm v-show="sections.service" :model="formData" label-position="top" class="form-grid">
        <ElFormItem label="服务访问地址" required class="form-grid__item form-grid__item--full">
          <ElInput v-model="formData.serviceUrl" placeholder="例如: http://192.168.1.10:8000/v1" />
          <span class="form-hint">OpenAI 兼容推理引擎通常为 http://IP:端口/v1</span>
        </ElFormItem>
      </ElForm>
      <div v-show="sections.service" class="metrics-block">
        <p class="form-hint endpoint-hint">监控节点可空；双机部署可添加多条（部署框架 + 监控 URL）。</p>
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

    <template #footer>
      <ElButton @click="emit('close')">取消</ElButton>
      <ElButton type="primary" @click="handleSave">确认添加</ElButton>
    </template>
  </ElDrawer>
</template>

<style scoped>
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

.form-hint {
  font-size: 12px;
  color: var(--text-placeholder);
}

.endpoint-hint {
  margin: 12px 0;
}

.form-field {
  width: 100%;
}

.metrics-block {
  margin-top: 4px;
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

.form-grid :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-placeholder);
}

.form-grid :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
}

.form-grid :deep(.el-input-number .el-input__inner) {
  text-align: left;
}
</style>
