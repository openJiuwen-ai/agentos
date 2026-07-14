<script setup lang="ts">
import { ref, watch } from 'vue';
import { ElDrawer, ElIcon } from 'element-plus';
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
  serverLocation: string;
  serviceIp: string;
  servicePort: number | null;
  serviceUrl: string;
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
  serverLocation: '',
  serviceIp: '',
  servicePort: null,
  serviceUrl: '',
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
      <div v-show="sections.basic" class="form-grid">
        <div class="form-group">
          <label class="form-label form-label--required">模型名称</label>
          <input v-model="formData.name" class="form-input" placeholder="请输入模型名称" />
        </div>
        <div class="form-group">
          <label class="form-label">模型类型</label>
          <select v-model="formData.type" class="form-select">
            <option value="chat">chat</option>
            <option value="completion">completion</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label form-label--required">上下文长度</label>
          <input v-model="formData.contextLength" class="form-input" type="number" placeholder="请输入上下文长度" />
        </div>
        <div class="form-group">
          <label class="form-label">模型参数量</label>
          <input v-model="formData.paramSize" class="form-input" placeholder="例如 72B" />
        </div>
        <div class="form-group" style="grid-column: span 2">
          <label class="form-label">分类标签</label>
          <input v-model="formData.tags" class="form-input" placeholder="W8A8" />
          <span class="form-hint">多个标签用逗号分割</span>
        </div>
        <div class="form-group" style="grid-column: span 2">
          <label class="form-label">模型描述</label>
          <textarea
            v-model="formData.description"
            class="form-textarea"
            placeholder="简要描述该模型的用途和特点..."
          ></textarea>
        </div>
      </div>
    </div>

    <!-- 部署信息 -->
    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('deploy')">
        <el-icon :style="{ transform: sections.deploy ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
        部署信息
      </h3>
      <div v-show="sections.deploy" class="form-grid">
        <div class="form-group">
          <label class="form-label form-label--required">部署模型名称</label>
          <input v-model="formData.deployName" class="form-input" placeholder="例如: gpt-4" />
          <span class="form-hint">仅支持Openai API格式，模型名将自动添加前缀: openai/</span>
        </div>
        <div class="form-group">
          <label class="form-label form-label--required">部署框架</label>
          <select v-model="formData.deployFramework" class="form-select">
            <option value="vLLM">vLLM</option>
            <option value="TGI">TGI</option>
          </select>
        </div>
        <div class="form-group" style="grid-column: span 2">
          <label class="form-label form-label--required">服务器位置</label>
          <input v-model="formData.serverLocation" class="form-input" placeholder="请输入服务器位置" />
        </div>
      </div>
    </div>

    <!-- 服务访问信息 -->
    <div class="info-section">
      <h3 class="info-section__title info-section__title--clickable" @click="toggleSection('service')">
        <el-icon :style="{ transform: sections.service ? 'rotate(0)' : 'rotate(-90deg)', transition: 'transform 0.2s' }"><ArrowDown /></el-icon>
        服务访问信息
      </h3>
      <div v-show="sections.service" class="form-grid">
        <div class="form-group">
          <label class="form-label form-label--required">服务 IP 地址</label>
          <input v-model="formData.serviceIp" class="form-input" placeholder="请输入服务IP地址" />
        </div>
        <div class="form-group">
          <label class="form-label form-label--required">服务端口</label>
          <input v-model="formData.servicePort" class="form-input" type="number" placeholder="请输入服务端口" />
        </div>
        <div class="form-group" style="grid-column: span 2">
          <label class="form-label form-label--required">实时访问URL</label>
          <input v-model="formData.serviceUrl" class="form-input" placeholder="请输入实时访问URL" />
        </div>
      </div>
    </div>

    <template #footer>
      <button class="btn" @click="emit('close')">取消</button>
      <button class="btn btn--primary" @click="handleSave">确认添加</button>
    </template>
  </ElDrawer>
</template>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
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
