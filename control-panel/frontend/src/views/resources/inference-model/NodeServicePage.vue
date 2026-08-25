<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import {
  ElButton,
  ElCard,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElSwitch,
  ElTabs,
  ElTabPane,
  ElTag,
  ElTooltip,
  ElEmpty,
  ElAlert,
  ElDescriptions,
  ElDescriptionsItem,
} from 'element-plus';
import {
  RefreshRight,
  VideoPlay,
  VideoPause,
  Setting,
  Document,
  Download,
} from '@element-plus/icons-vue';
import {
  fetchNodeConfig,
  updateNodeConfig,
  startNodeService,
  stopNodeService,
  restartNodeService,
  fetchNodeStatus,
  fetchNodeLogs,
  fetchTemplates,
  fetchTemplateContent,
  saveTemplate,
  applyTemplate,
  type NodeServiceConfig,
  type NodeServiceStatus,
  type NodeServiceTemplate,
} from '@/api/nodeService';
import { usePolling } from '@/composables/usePolling';
import { useAuth } from '@/composables/useAuth';

// ── Constants ──
const POLL_IDLE_MS = 15_000;
const LOG_POLL_MS = 10_000;

// ── State ──
const loading = ref(false);
const error = ref('');
const node = ref('master');
const config = ref<NodeServiceConfig | null>(null);
const configDraft = ref<NodeServiceConfig | null>(null);
const status = ref<NodeServiceStatus | null>(null);
const activeConfigTab = ref('model');

// Template dialog
const templateDialogVisible = ref(false);
const templateList = ref<NodeServiceTemplate[]>([]);
const templateListLoading = ref(false);
const selectedTemplateName = ref('');
const selectedTemplateData = ref<NodeServiceConfig | null>(null);
const templatePreviewLoading = ref(false);

// Save template dialog
const saveTemplateVisible = ref(false);
const saveTemplateName = ref('');
const saveTemplateDesc = ref('');
const saveTemplateLoading = ref(false);

// Logs
const logLines = ref<string[]>([]);
const logLoading = ref(false);
const logLinesCount = ref(200);
const logAutoRefresh = ref(false);
const logScrollRef = ref<HTMLDivElement | null>(null);
const logAutoScroll = ref(true);

// Config dirty tracking
const isDirty = ref(false);
const isSaving = ref(false);

// ── Composables ──
const { effectiveIsAdmin: isAdmin } = useAuth();
const { restart: restartPollTimer, stop: stopPollTimer } = usePolling(POLL_IDLE_MS);
const { restart: restartLogTimer, stop: stopLogTimer } = usePolling(LOG_POLL_MS);

// ── Derived ──
const isRunning = computed(() => status.value?.container === 'running');
const isStarting = computed(() => {
  const p = status.value?.start_progress;
  return p && p.status !== 'idle' && p.status !== 'ready' && p.status !== 'failed';
});

const containerStatus = computed(() => {
  const s = status.value?.container;
  if (!s) return { text: '未知', type: 'info' as const, color: '#909399' };
  if (s === 'running') return { text: '运行中', type: 'success' as const, color: '#67C23A' };
  if (s === 'not running') return { text: '已停止', type: 'info' as const, color: '#909399' };
  return { text: s, type: 'warning' as const, color: '#E6A23C' };
});

const statusDotStyle = computed(() => ({
  width: '10px',
  height: '10px',
  borderRadius: '50%',
  backgroundColor: containerStatus.value.color,
  display: 'inline-block',
  marginRight: '8px',
  boxShadow: isRunning.value ? `0 0 8px ${containerStatus.value.color}` : 'none',
}));

const startProgress = computed(() => status.value?.start_progress);

const progressPercent = computed(() => {
  const s = startProgress.value?.status;
  if (!s || s === 'idle') return 0;
  if (s === 'queued') return 10;
  if (s === 'pulling') return 30;
  if (s === 'starting') return 60;
  if (s === 'waiting') return 85;
  if (s === 'ready') return 100;
  if (s === 'failed') return 100;
  return 50;
});

const progressStatus = computed(() => {
  const s = startProgress.value?.status;
  if (s === 'failed') return 'exception' as const;
  if (s === 'ready') return 'success' as const;
  return undefined;
});

const canSaveConfig = computed(() => isDirty.value && !isSaving.value);
const canStart = computed(() => !isRunning.value && !isStarting.value);
const canStop = computed(() => isRunning.value && !isStarting.value);
const canRestart = computed(() => isRunning.value && !isStarting.value);

const canApplyTemplate = computed(() => {
  if (!selectedTemplateName.value) return false;
  return selectedTemplateData.value !== null;
});

// ── Config field definitions ──
interface FieldDef {
  key: string;
  label: string;
  type: 'input' | 'number' | 'switch' | 'select';
  options?: { value: any; label: string }[];
  required?: boolean;
  step?: number;
  min?: number;
  max?: number;
  precision?: number;
}

const CONFIG_TABS: { key: string; label: string; fields: FieldDef[] }[] = [
  {
    key: 'model',
    label: '模型配置',
    fields: [
      { key: 'weight_path', label: '权重路径', type: 'input', required: true },
      { key: 'model_path', label: '模型路径', type: 'input', required: true },
      { key: 'model_name', label: '模型名称', type: 'input', required: true },
    ],
  },
  {
    key: 'deploy',
    label: '部署配置',
    fields: [
      { key: 'image', label: 'Docker 镜像', type: 'input' },
      { key: 'npu_num', label: 'NPU 数量', type: 'number', min: 0, step: 1 },
    ],
  },
  {
    key: 'parallel',
    label: '并行配置',
    fields: [
      { key: 'tensor_parallel_size', label: 'Tensor 并行', type: 'number', min: 1, step: 1 },
      { key: 'data_parallel_size', label: 'DP 并行', type: 'number', min: 1, step: 1 },
      { key: 'enable_expert_parallel', label: '专家并行 (MoE)', type: 'switch' },
      { key: 'gpu_memory_utilization', label: 'GPU 显存利用率', type: 'number', min: 0, max: 1, step: 0.05, precision: 2 },
      { key: 'quantization', label: '量化方式', type: 'select', options: [
        { value: '', label: '无' },
        { value: 'ascend', label: 'Ascend 量化' },
      ]},
    ],
  },
  {
    key: 'inference',
    label: '推理参数',
    fields: [
      { key: 'max_model_len', label: '最大序列长度', type: 'number', min: 1, step: 1024 },
      { key: 'max_num_batched_tokens', label: '最大批处理 Token', type: 'number', min: 1, step: 1024 },
      { key: 'max_num_seqs', label: '最大并发序列', type: 'number', min: 1, step: 1 },
      { key: 'enforce_eager', label: '强制 Eager 模式', type: 'switch' },
    ],
  },
  {
    key: 'format',
    label: '格式配置',
    fields: [
      { key: 'tokenizer_mode', label: '分词器模式', type: 'select', options: [
        { value: 'auto', label: 'Auto' },
        { value: 'slow', label: 'Slow' },
        { value: 'fast', label: 'Fast' },
      ]},
      { key: 'tool_call_parser', label: '工具调用解析器', type: 'input' },
      { key: 'reasoning_parser', label: '推理解析器', type: 'input' },
      { key: 'trust_remote_code', label: '信任远程代码', type: 'switch' },
    ],
  },
  {
    key: 'ports',
    label: '端口配置',
    fields: [
      { key: 'controller_port', label: 'Controller 端口', type: 'number', min: 1024, max: 65535, step: 1 },
      { key: 'coordinator_infer_port', label: '协调器推理端口', type: 'number', min: 1024, max: 65535, step: 1 },
      { key: 'coordinator_mgmt_port', label: '协调器管理端口', type: 'number', min: 1024, max: 65535, step: 1 },
      { key: 'coordinator_obs_port', label: '协调器观测端口', type: 'number', min: 1024, max: 65535, step: 1 },
      { key: 'node_manager_port', label: '节点管理器端口', type: 'number', min: 1024, max: 65535, step: 1 },
      { key: 'base_port', label: '服务基础端口', type: 'number', min: 1024, max: 65535, step: 1 },
    ],
  },
];

// ── API calls ──
async function fetchStatus() {
  try {
    status.value = await fetchNodeStatus(node.value);
  } catch (e: any) {
    if (e?.status === 502 || e?.status === 404 || e?.status === 504) {
      status.value = null;
    } else {
      throw e;
    }
  }
}

async function fetchConfig() {
  try {
    const data = await fetchNodeConfig(node.value);
    config.value = data;
    configDraft.value = JSON.parse(JSON.stringify(data));
    isDirty.value = false;
  } catch (e: any) {
    if (e?.status === 502 || e?.status === 404 || e?.status === 504) {
      config.value = null;
      configDraft.value = null;
    } else {
      throw e;
    }
  }
}

async function fetchLogs() {
  logLoading.value = true;
  try {
    const data = await fetchNodeLogs(node.value, logLinesCount.value);
    logLines.value = data?.logs || [];
  } catch {
    logLines.value = [];
  } finally {
    logLoading.value = false;
  }
}

async function refreshAll(isRefresh = false) {
  if (isRefresh) loading.value = true;
  error.value = '';
  try {
    await Promise.all([fetchStatus(), fetchConfig()]);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载 node-service 信息失败';
  } finally {
    loading.value = false;
  }
}

function pollDuringStartup() {
  restartPollTimer(pollDuringStartup);
}

// ── Template dialog handlers ──
async function openTemplateDialog() {
  templateDialogVisible.value = true;
  selectedTemplateName.value = '';
  selectedTemplateData.value = null;
  templateListLoading.value = true;
  try {
    const data = await fetchTemplates(node.value);
    templateList.value = data?.templates || [];
  } catch {
    templateList.value = [];
  } finally {
    templateListLoading.value = false;
  }
}

async function handleTemplateSelect(tpl: NodeServiceTemplate) {
  selectedTemplateName.value = tpl.name;
  templatePreviewLoading.value = true;
  selectedTemplateData.value = null;
  try {
    const data = await fetchTemplateContent(node.value, tpl.name);
    if (data?.config) {
      selectedTemplateData.value = data.config;
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载模板内容失败');
  } finally {
    templatePreviewLoading.value = false;
  }
}

async function handleApplyTemplate() {
  if (!selectedTemplateName.value) return;
  try {
    await ElMessageBox.confirm(
      '应用模板将覆盖当前完整配置（含用户配置），确定继续？',
      '应用模板确认',
      { type: 'warning', confirmButtonText: '确定应用', cancelButtonText: '取消' },
    );
  } catch {
    return;
  }
  try {
    await applyTemplate(node.value, selectedTemplateName.value);
    templateDialogVisible.value = false;
    ElMessage.success('模板已应用');
    await refreshAll(true);
  } catch (e: any) {
    ElMessage.error(e?.message || '应用模板失败');
  }
}

function openSaveTemplateDialog() {
  saveTemplateName.value = '';
  saveTemplateDesc.value = '';
  saveTemplateVisible.value = true;
}

function filterTemplateName(val: string) {
  saveTemplateName.value = val.replace(/[^a-zA-Z0-9_-]/g, '');
}

async function handleSaveTemplate() {
  if (!saveTemplateName.value.trim()) {
    ElMessage.warning('请输入模板名称');
    return;
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(saveTemplateName.value.trim())) {
    ElMessage.warning('模板名称只能包含字母、数字、下划线和连字符');
    return;
  }
  saveTemplateLoading.value = true;
  try {
    await saveTemplate(node.value, {
      name: saveTemplateName.value.trim(),
      description: saveTemplateDesc.value.trim(),
    });
    ElMessage.success('模板保存成功');
    saveTemplateVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.message || '保存模板失败');
  } finally {
    saveTemplateLoading.value = false;
  }
}

// ── Config editing ──
function handleConfigChange(section: string, field: string, value: any) {
  if (!configDraft.value) return;
  (configDraft.value as any)[section][field] = value;
  isDirty.value = true;
}

async function handleSaveConfig(shouldRestart = false) {
  if (!configDraft.value || !config.value) return;
  isSaving.value = true;
  try {
    const diff: Partial<NodeServiceConfig> = {};
    for (const section of Object.keys(configDraft.value) as (keyof NodeServiceConfig)[]) {
      const draft = configDraft.value[section];
      const current = config.value[section];
      if (JSON.stringify(draft) !== JSON.stringify(current)) {
        (diff as any)[section] = draft;
      }
    }

    if (Object.keys(diff).length === 0) {
      ElMessage.info('没有变更需要保存');
      isSaving.value = false;
      return;
    }

    await updateNodeConfig(node.value, diff);
    config.value = JSON.parse(JSON.stringify(configDraft.value));
    isDirty.value = false;
    ElMessage.success('配置已保存');

    if (shouldRestart) {
      await handleRestart();
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '保存配置失败');
  } finally {
    isSaving.value = false;
  }
}

// ── Service control ──
async function handleStart() {
  try {
    await ElMessageBox.confirm('确定要启动推理服务吗？', '启动确认', { type: 'info' });
    await startNodeService(node.value);
    ElMessage.success('启动请求已发送');
    await refreshAll(true);
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      if (e?.status === 409) {
        ElMessage.warning('启动进行中，请稍候');
      } else {
        ElMessage.error(e?.message || '启动失败');
      }
    }
  }
}

async function handleStop() {
  try {
    await ElMessageBox.confirm('确定要停止推理服务吗？服务停止后需要手动重新启动。', '停止确认', { type: 'warning' });
    await stopNodeService(node.value);
    ElMessage.success('停止请求已发送');
    await refreshAll(true);
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error(e?.message || '停止失败');
    }
  }
}

async function handleRestart() {
  try {
    await ElMessageBox.confirm('确定要重启推理服务吗？', '重启确认', { type: 'warning' });
    await restartNodeService(node.value);
    ElMessage.success('重启请求已发送');
    await refreshAll(true);
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      if (e?.status === 409) {
        ElMessage.warning('启动进行中，请稍候');
      } else {
        ElMessage.error(e?.message || '重启失败');
      }
    }
  }
}

// ── Log auto-scroll ──
watch(logLines, () => {
  if (logAutoScroll.value) {
    nextTick(() => {
      const el = logScrollRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
}, { flush: 'post' });

function handleLogScroll() {
  const el = logScrollRef.value;
  if (!el) return;
  logAutoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
}

function scrollToBottom() {
  const el = logScrollRef.value;
  if (el) {
    el.scrollTop = el.scrollHeight;
    logAutoScroll.value = true;
  }
}

function formatLogLine(line: string): { text: string; cls: string } {
  if (/error/i.test(line)) return { text: line, cls: 'log-line--error' };
  if (/warn/i.test(line)) return { text: line, cls: 'log-line--warn' };
  return { text: line, cls: '' };
}

// ── Lifecycle ──
onMounted(async () => {
  await refreshAll();
  restartPollTimer(pollDuringStartup);
  await fetchLogs();
});

onUnmounted(() => {
  stopPollTimer();
  stopLogTimer();
});

watch(logAutoRefresh, (val) => {
  if (val) {
    restartLogTimer(fetchLogs);
  } else {
    stopLogTimer();
  }
});

watch(node, () => {
  refreshAll(true);
  fetchLogs();
});

// Template preview field labels
const TEMPLATE_FIELD_LABELS: Record<string, Record<string, string>> = {
  model: { weight_path: '权重路径', model_path: '模型路径', model_name: '模型名称' },
  deploy: { image: 'Docker 镜像', npu_num: 'NPU 数量' },
  parallel: {
    tensor_parallel_size: 'Tensor 并行', data_parallel_size: 'DP 并行',
    enable_expert_parallel: '专家并行', gpu_memory_utilization: 'GPU 显存利用率',
    quantization: '量化方式',
  },
  inference: {
    max_model_len: '最大序列长度', max_num_batched_tokens: '最大批处理 Token',
    max_num_seqs: '最大并发序列', enforce_eager: '强制 Eager',
  },
  format: {
    tokenizer_mode: '分词器模式', tool_call_parser: '工具调用解析器',
    reasoning_parser: '推理解析器', trust_remote_code: '信任远程代码',
  },
  ports: {
    controller_port: 'Controller 端口', coordinator_infer_port: '协调器推理端口',
    coordinator_mgmt_port: '协调器管理端口', coordinator_obs_port: '协调器观测端口',
    node_manager_port: '节点管理器端口', base_port: '服务基础端口',
  },
};

function formatFieldValue(val: any): string {
  if (val === null || val === undefined || val === '') return '—';
  if (typeof val === 'boolean') return val ? '是' : '否';
  return String(val);
}

const TAB_LABELS: Record<string, string> = {
  model: '模型配置', deploy: '部署配置', parallel: '并行配置',
  inference: '推理参数', format: '格式配置', ports: '端口配置',
};
</script>

<template>
  <section class="node-service-page">
    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header__top">
        <div class="page-header__left">
          <h1 class="page-title">推理服务部署</h1>
          <el-select v-model="node" size="small" style="width: 140px" placeholder="选择节点">
            <el-option label="Master" value="master" />
            <el-option label="Worker-1" value="worker-1" />
            <el-option label="Worker-2" value="worker-2" />
            <el-option label="Worker-3" value="worker-3" />
          </el-select>
          <el-tag :type="containerStatus.type" effect="light" size="small" disable-transitions>
            {{ containerStatus.text }}
          </el-tag>
        </div>
        <div class="page-header__actions">
          <el-button :icon="RefreshRight" :loading="loading" size="small" @click="refreshAll(true)">刷新</el-button>
          <el-button type="success" :icon="VideoPlay" size="small" :disabled="!canStart" @click="handleStart">启动</el-button>
          <el-button type="danger" :icon="VideoPause" size="small" :disabled="!canStop" @click="handleStop">停止</el-button>
          <el-button type="warning" :icon="RefreshRight" size="small" :disabled="!canRestart" @click="handleRestart">重启</el-button>
        </div>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="mb-16" />

    <!-- ── Start Progress ── -->
    <el-card v-if="startProgress && startProgress.status !== 'idle' && startProgress.status !== 'ready'" shadow="never" class="mb-16 progress-card">
      <div class="progress-row">
        <el-tag :type="startProgress.status === 'failed' ? 'danger' : 'warning'" effect="light" size="small">
          {{ startProgress.status }}
        </el-tag>
        <div class="progress-bar-area">
          <el-progress :percentage="progressPercent" :status="progressStatus" :stroke-width="16" :text-inside="true" style="flex: 1" />
          <span class="progress-message">{{ startProgress.message }}</span>
        </div>
      </div>
      <div v-if="startProgress.error" class="progress-error">{{ startProgress.error }}</div>
    </el-card>

    <!-- ── Config Editor ── -->
    <el-card v-if="configDraft" shadow="never" class="mb-16 config-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span class="card-header__title">
            <el-icon><Setting /></el-icon>
            服务配置
          </span>
          <div class="card-header__actions">
            <el-tooltip content="应用模板（覆盖完整配置）" placement="top">
              <el-button size="small" :icon="Download" @click="openTemplateDialog">使用模板</el-button>
            </el-tooltip>
            <el-tooltip content="将当前配置保存为新模板" placement="top">
              <el-button size="small" :icon="Download" @click="openSaveTemplateDialog">保存为模板</el-button>
            </el-tooltip>
            <el-button v-if="isDirty" size="small" @click="fetchConfig()">重置</el-button>
            <el-button type="primary" size="small" :loading="isSaving" :disabled="!canSaveConfig" @click="handleSaveConfig(true)">保存并重启</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeConfigTab" type="border-card">
        <el-tab-pane v-for="tab in CONFIG_TABS" :key="tab.key" :label="tab.label" :name="tab.key">
          <el-form label-width="160px" label-position="left" class="config-form">
            <el-form-item v-for="field in tab.fields" :key="field.key" :label="field.label" :required="field.required">
              <el-input
                v-if="field.type === 'input'"
                :model-value="(configDraft as any)[tab.key]?.[field.key] ?? ''"
                @update:model-value="(v: string) => handleConfigChange(tab.key, field.key, v)"
                :placeholder="field.required ? '必填' : ''"
              />
              <el-input-number
                v-else-if="field.type === 'number'"
                :model-value="(configDraft as any)[tab.key]?.[field.key]"
                @update:model-value="(v: number) => handleConfigChange(tab.key, field.key, v)"
                :min="field.min" :max="field.max" :step="field.step" :precision="field.precision"
                controls-position="right" style="width: 180px"
              />
              <el-switch
                v-else-if="field.type === 'switch'"
                :model-value="(configDraft as any)[tab.key]?.[field.key]"
                @update:model-value="(v: boolean) => handleConfigChange(tab.key, field.key, v)"
              />
              <el-select
                v-else-if="field.type === 'select'"
                :model-value="(configDraft as any)[tab.key]?.[field.key]"
                @update:model-value="(v: string) => handleConfigChange(tab.key, field.key, v)"
                style="width: 180px"
              >
                <el-option v-for="opt in field.options" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-empty v-if="!loading && !config" description="无法获取 node-service 配置，请确认服务已安装并运行" />

    <!-- ── Log Section (direct container logs) ── -->
    <el-card shadow="never" class="mb-16 log-card">
      <template #header>
        <div class="card-header">
          <span class="card-header__title">
            <el-icon><Document /></el-icon>
            容器日志
          </span>
          <div class="card-header__actions">
            <el-select v-model="logLinesCount" size="small" style="width: 100px" @change="fetchLogs">
              <el-option :value="50" label="50 行" />
              <el-option :value="100" label="100 行" />
              <el-option :value="200" label="200 行" />
              <el-option :value="500" label="500 行" />
            </el-select>
            <el-switch v-model="logAutoRefresh" active-text="自动刷新" size="small" />
            <el-button size="small" :icon="RefreshRight" :loading="logLoading" @click="fetchLogs">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="log-section">
        <div ref="logScrollRef" class="log-scroll" @scroll="handleLogScroll" v-loading="logLoading">
          <div v-if="logLines.length === 0 && !logLoading" class="log-empty">暂无日志</div>
          <div
            v-for="(line, idx) in logLines"
            :key="idx"
            class="log-line"
            :class="formatLogLine(line).cls"
          >{{ line }}</div>
        </div>
        <div v-if="!logAutoScroll" class="log-back-to-latest">
          <el-button size="small" text @click="scrollToBottom">回到最新</el-button>
        </div>
      </div>
    </el-card>

    <!-- ── Template Selection Dialog ── -->
    <el-dialog v-model="templateDialogVisible" title="应用模板" width="680px" :close-on-click-modal="false">
      <div class="tpl-dialog-body">
        <!-- Left: template list -->
        <div class="tpl-list" v-loading="templateListLoading">
          <div v-if="templateList.length === 0 && !templateListLoading" class="tpl-empty">暂无可用模板</div>
          <div
            v-for="tpl in templateList"
            :key="tpl.name"
            class="tpl-item"
            :class="{ 'tpl-item--active': selectedTemplateName === tpl.name }"
            @click="handleTemplateSelect(tpl)"
          >
            <div class="tpl-item__name">{{ tpl.name }}</div>
            <div class="tpl-item__desc">{{ tpl.description || '暂无描述' }}</div>
            <el-tag v-if="tpl.source === 'system'" type="info" size="small" effect="plain">系统</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">用户</el-tag>
          </div>
        </div>

        <!-- Right: template preview -->
        <div class="tpl-preview" v-loading="templatePreviewLoading">
          <template v-if="selectedTemplateData">
            <div class="tpl-preview__title">配置预览 — {{ selectedTemplateName }}</div>
            <div class="tpl-preview__scroll">
              <div v-for="(fields, section) in TEMPLATE_FIELD_LABELS" :key="section" class="tpl-preview__section">
                <div class="tpl-preview__section-title">{{ TAB_LABELS[section] || section }}</div>
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item v-for="(label, field) in fields" :key="field" :label="label">
                    {{ formatFieldValue((selectedTemplateData as any)?.[section]?.[field]) }}
                  </el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </template>
          <div v-else-if="!templatePreviewLoading && selectedTemplateName" class="tpl-preview__empty">
            无法加载模板内容
          </div>
          <div v-else class="tpl-preview__empty">请从左侧选择一个模板</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="templateDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!canApplyTemplate" @click="handleApplyTemplate">应用模板</el-button>
      </template>
    </el-dialog>

    <!-- ── Save Template Dialog ── -->
    <el-dialog v-model="saveTemplateVisible" title="保存为模板" width="420px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="模板名称" required>
          <el-input
            :model-value="saveTemplateName"
            @update:model-value="filterTemplateName"
            placeholder="输入模板名称"
            maxlength="50"
          />
          <div class="form-hint">仅允许字母、数字、下划线和连字符</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="saveTemplateDesc" type="textarea" :rows="3" placeholder="可选的描述信息" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveTemplateVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveTemplateLoading" @click="handleSaveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.node-service-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding: 20px 24px 24px;
}

.page-header { flex-shrink: 0; margin-bottom: 16px; }
.page-header__top { display: flex; align-items: center; justify-content: space-between; }
.page-header__left { display: flex; align-items: center; gap: 16px; }
.page-header__actions { display: flex; gap: 8px; }
.page-title { margin: 0; font-size: 20px; font-weight: 600; }
.status-indicator { display: flex; align-items: center; }
.status-text { font-size: 14px; font-weight: 500; }
.mb-16 { margin-bottom: 16px; }

.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-header__title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }
.card-header__actions { display: flex; gap: 8px; align-items: center; }

.progress-card :deep(.el-card__body) { padding: 16px 20px; }
.progress-row { display: flex; align-items: center; gap: 12px; }
.progress-bar-area { flex: 1; display: flex; align-items: center; gap: 12px; }
.progress-message { font-size: 13px; color: var(--el-text-color-secondary); flex-shrink: 0; }
.progress-error { margin-top: 8px; font-size: 13px; color: var(--el-color-danger); }

.config-card :deep(.el-card__header) { padding: 12px 20px; }
.config-form { padding: 8px 0; }
.config-form :deep(.el-form-item) { margin-bottom: 16px; }
.config-form :deep(.el-form-item:last-child) { margin-bottom: 0; }

/* ── Log Section ── */
.log-card { flex: 1; display: flex; flex-direction: column; min-height: 300px; }
.log-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; padding: 12px 20px 20px; min-height: 0; }
.log-section { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.log-scroll {
  flex: 1; min-height: 200px; overflow-y: auto;
  background: #f8f9fa; border-radius: 6px; padding: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px; line-height: 1.6;
}
.log-empty { text-align: center; padding: 40px 0; color: var(--el-text-color-placeholder); font-size: 14px; }
.log-line { white-space: pre-wrap; word-break: break-all; color: #333; padding: 1px 4px; border-radius: 2px; }
.log-line:hover { background: rgba(0, 0, 0, 0.03); }
.log-line--error { color: #f56c6c; background: rgba(245, 108, 108, 0.06); }
.log-line--warn { color: #e6a23c; background: rgba(230, 162, 60, 0.06); }
.log-back-to-latest { text-align: center; padding: 8px 0 0; }

/* ── Template Dialog ── */
.tpl-dialog-body { display: flex; gap: 16px; min-height: 400px; }
.tpl-list {
  width: 220px; flex-shrink: 0; border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px; overflow-y: auto; max-height: 450px;
}
.tpl-empty { text-align: center; padding: 40px 0; color: var(--el-text-color-placeholder); font-size: 13px; }
.tpl-item {
  padding: 12px; cursor: pointer; border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.15s;
}
.tpl-item:last-child { border-bottom: none; }
.tpl-item:hover { background: #f5f7fa; }
.tpl-item--active { background: #ecf5ff; border-left: 3px solid var(--el-color-primary); }
.tpl-item__name { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
.tpl-item__desc { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.tpl-preview { flex: 1; min-width: 0; }
.tpl-preview__title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.tpl-preview__scroll { max-height: 400px; overflow-y: auto; }
.tpl-preview__section { margin-bottom: 16px; }
.tpl-preview__section-title { font-size: 13px; font-weight: 500; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.tpl-preview__empty { text-align: center; padding: 60px 0; color: var(--el-text-color-placeholder); font-size: 14px; }

.form-hint { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.4; margin-top: 4px; }
</style>
