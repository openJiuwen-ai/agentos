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
import { ArrowDown } from '@element-plus/icons-vue';

interface ModelFormData {
  name: string;
  type: string;
  contextLength: number | null;
  paramSize: string;
  tags: string;
  description: string;
  deployName: string;
  deployFramework: string;
  serviceIp: string;
  servicePort: number | null;
  metricsUrl: string;
}

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  close: [];
  save: [data: ModelFormData];
}>();

const defaultFormData: ModelFormData = {
  name: '',
  type: 'chat',
  contextLength: null,
  paramSize: '',
  tags: '',
  description: '',
  deployName: '',
  deployFramework: 'vLLM',
  serviceIp: '',
  servicePort: null,
  metricsUrl: '',
};

const formData = ref<ModelFormData>({ ...defaultFormData });

watch(
  () => props.visible,
  (val) => {
    if (val) {
      formData.value = { ...defaultFormData };
    }
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

function handleSave() {
  emit('save', { ...formData.value });
  emit('close');
}
</script>

<template>
  <ElDrawer :model-value="visible" title="添加模型" size="480px" @close="emit('close')">
    <!-- 基础信息 -->
    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('basic')">
        <el-icon :style="{ transform: sections.basic ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
        基础信息
      </h3>
      <ElForm v-show="sections.basic" :model="formData" label-position="top" class="form-grid">
        <ElFormItem label="模型名称" required class="form-grid__item">
          <ElInput v-model="formData.name" placeholder="请输入模型名称" />
        </ElFormItem>
        <ElFormItem label="模型类型" class="form-grid__item">
          <ElSelect v-model="formData.type" placeholder="请选择模型类型">
            <ElOption label="chat" value="chat" />
            <ElOption label="completion" value="completion" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="上下文长度" required class="form-grid__item">
          <ElInputNumber
            v-model="formData.contextLength"
            :controls="false"
            :min="0"
            placeholder="请输入上下文长度"
            class="form-field"
          />
        </ElFormItem>
        <ElFormItem label="模型参数量" class="form-grid__item">
          <ElInput v-model="formData.paramSize" placeholder="例如 72B" />
        </ElFormItem>
        <ElFormItem label="分类标签" class="form-grid__item form-grid__item--full">
          <ElInput v-model="formData.tags" placeholder="W8A8" />
          <span class="form-hint">多个标签用逗号分割</span>
        </ElFormItem>
        <ElFormItem label="模型描述" class="form-grid__item form-grid__item--full">
          <ElInput
            v-model="formData.description"
            type="textarea"
            :rows="4"
            resize="vertical"
            placeholder="简要描述该模型的用途和特点..."
          />
        </ElFormItem>
      </ElForm>
    </div>

    <!-- 部署信息 -->
    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('deploy')">
        <el-icon :style="{ transform: sections.deploy ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
        部署信息
      </h3>
      <ElForm v-show="sections.deploy" :model="formData" label-position="top" class="form-grid">
        <ElFormItem label="部署模型名称" required class="form-grid__item">
          <ElInput v-model="formData.deployName" placeholder="例如: gpt-4" />
          <span class="form-hint">仅支持 OpenAI API 格式，模型名将自动添加前缀: openai/</span>
        </ElFormItem>
        <ElFormItem label="部署框架" required class="form-grid__item">
          <ElSelect v-model="formData.deployFramework" placeholder="请选择部署框架">
            <ElOption label="vLLM" value="vLLM" />
            <ElOption label="SGLang" value="SGLang" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
    </div>

    <!-- 服务访问信息 -->
    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('service')">
        <el-icon :style="{ transform: sections.service ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
        服务访问信息
      </h3>
      <ElForm v-show="sections.service" :model="formData" label-position="top" class="form-grid">
        <ElFormItem label="服务 IP 地址" required class="form-grid__item">
          <ElInput v-model="formData.serviceIp" placeholder="请输入服务 IP 地址" />
        </ElFormItem>
        <ElFormItem label="服务端口" required class="form-grid__item">
          <ElInputNumber
            v-model="formData.servicePort"
            :controls="false"
            :min="0"
            placeholder="请输入服务端口"
            class="form-field"
          />
        </ElFormItem>
        <ElFormItem label="模型监控 URL" required class="form-grid__item form-grid__item--full">
          <ElInput v-model="formData.metricsUrl" placeholder="请输入模型监控 URL" />
        </ElFormItem>
      </ElForm>
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
  color: var(--text-primary, #1f2937);
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
  color: var(--text-tertiary, #9ca3af);
}

.form-field {
  width: 100%;
}

.form-grid :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
}

.form-grid :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
}

.form-grid :deep(.el-input-number .el-input__inner) {
  text-align: left;
}
</style>
