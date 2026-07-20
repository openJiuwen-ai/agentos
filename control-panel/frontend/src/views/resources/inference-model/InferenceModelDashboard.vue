<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElInput, ElIcon, ElMessageBox } from 'element-plus';
import { Search, Plus, ArrowRight } from '@element-plus/icons-vue';
import ModelCard from './ModelCard.vue';
import AddModelModal from './AddModelModal.vue';
import ModelInfoDrawer from './ModelInfoDrawer.vue';
import { fetchModelList, fetchModelDetail, createModel, updateModel, deleteModel, restartModel, fetchUsageOverview, fetchUserUsage } from '@/api/inference';
import type { ModelDetail, UsageOverviewResponse, UserUsageDetailResponse } from '@/api/inference';
import { ElMessage } from 'element-plus';
import { useAuth } from '@/composables/useAuth';

const router = useRouter();
const { isAdmin, userId } = useAuth();
const loading = ref(false);

interface ModelCardData {
  id: string;
  name: string;
  status: 'success' | 'error' | 'warning';
  statusText: string;
  tags: string[];
  e2eP95: string;
  todayCalls: string;
  todayTokens: string;
  meta: string[];
  iconSrc: undefined;
  contextWindow?: number | null;
}

const models = ref<ModelCardData[]>([]);
const activeFilter = ref('all');
const searchQuery = ref('');
const showAddModal = ref(false);
const drawerVisible = ref(false);
const drawerMode = ref<'view' | 'edit'>('view');
const selectedModel = ref<ModelDetail | null>(null);

const filters = [
  { key: 'all', label: '全部模型' },
];

// 调用概览数据
const overviewData = ref({
  today: { requests: 0, tokens: 0 },
  week: { requests: 0, tokens: 0 },
  total: { requests: 0, tokens: 0 },
});
const overviewError = ref('');

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getDateRange(days: number | string): { start_date: string; end_date: string } {
  const end = new Date();
  const start = typeof days === 'string' ? new Date(days) : new Date();
  if (typeof days === 'number') {
    start.setDate(end.getDate() - days);
  }
  return { start_date: formatDate(start), end_date: formatDate(end) };
}

function calculateTotals(data: UsageOverviewResponse) {
  return (data.users ?? []).reduce(
    (acc, user) => ({
      requests: acc.requests + user.total_requests,
      tokens: acc.tokens + user.total_tokens,
    }),
    { requests: 0, tokens: 0 }
  );
}

function calculateUserTotals(data: UserUsageDetailResponse) {
  return (data.daily_activity ?? []).reduce(
    (acc, day) => ({
      requests: acc.requests + day.requests,
      tokens: acc.tokens + day.tokens,
    }),
    { requests: 0, tokens: 0 }
  );
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return (tokens / 1_000_000).toFixed(2) + 'M';
  }
  if (tokens >= 1_000) {
    return (tokens / 1_000).toFixed(1) + 'K';
  }
  return tokens.toString();
}

async function loadOverviewData() {
  overviewError.value = '';
  try {
    if (isAdmin.value) {
      // 管理员：使用 /overview 接口获取所有用户数据
      const [todayRes, weekRes, totalRes] = await Promise.all([
        fetchUsageOverview(getDateRange(0)),
        fetchUsageOverview(getDateRange(7)),
        fetchUsageOverview(getDateRange('2000-01-01')),
      ]);

      overviewData.value = {
        today: calculateTotals(todayRes),
        week: calculateTotals(weekRes),
        total: calculateTotals(totalRes),
      };
    } else {
      // 普通用户：使用 /user 接口获取自己的数据
      const uid = userId.value;
      if (!uid) {
        overviewError.value = '无法获取用户信息';
        return;
      }

      const [todayRes, weekRes, totalRes] = await Promise.all([
        fetchUserUsage({ user_id: uid, ...getDateRange(0) }),
        fetchUserUsage({ user_id: uid, ...getDateRange(7) }),
        fetchUserUsage({ user_id: uid, ...getDateRange('2000-01-01') }),
      ]);

      overviewData.value = {
        today: calculateUserTotals(todayRes),
        week: calculateUserTotals(weekRes),
        total: calculateUserTotals(totalRes),
      };
    }
  } catch (e) {
    console.error('加载调用概览数据失败:', e);
    overviewError.value = e instanceof Error ? e.message : '加载调用概览数据失败';
  }
}

async function loadModels() {
  loading.value = true;
  try {
    const data = await fetchModelList({ keyword: searchQuery.value });
    // 将后端数据转换为ModelCard期望的格式
    models.value = data.items.map(item => ({
      id: item.id,
      name: item.model_name,
      status: 'success' as const,
      statusText: '健康',
      tags: [],
      e2eP95: '--',
      todayCalls: '--',
      todayTokens: '--',
      meta: [item.litellm_params.model],
      iconSrc: undefined,
      contextWindow: item.model_info?.context_window,
    }));
  } catch (e) { console.error('加载模型列表失败:', e); } finally { loading.value = false; }
}

function goToModel(id: string) { router.push({ name: 'inference-model-detail', params: { id } }); }
async function handleDeleteModel(id: string) {
  try {
    await ElMessageBox.confirm('确定要删除这个模型吗？删除后将无法恢复。', '确认删除', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await deleteModel(id);
    ElMessage.success('删除成功');
    await loadModels();
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
  }
}
async function handleEditModel(id: string) {
  try {
    selectedModel.value = await fetchModelDetail(id);
    drawerMode.value = 'edit';
    drawerVisible.value = true;
  } catch (e) {
    console.error(e);
  }
}

async function handleSaveModel(data: Partial<ModelDetail>) {
  if (!selectedModel.value) return;
  try {
    await updateModel(selectedModel.value.id, data);
    ElMessage.success('保存成功');
    drawerVisible.value = false;
    await loadModels();
  } catch (e) {
    ElMessage.error('保存失败: ' + (e instanceof Error ? e.message : '未知错误'));
  }
}

async function handleRestartModel(id: string) { try { await restartModel(id); await loadModels(); } catch (e) { console.error(e); } }

async function handleAddModel(formData: { name: string; type: string; contextLength: number | null; deployName: string; deployFramework: string; serviceIp: string; servicePort: number | null; metricsUrl: string; paramSize?: string; tags?: string; description?: string }) {
  // 必填项验证
  if (!formData.name?.trim()) {
    ElMessage.warning('请输入模型名称');
    return;
  }
  if (!formData.deployName?.trim()) {
    ElMessage.warning('请输入部署模型名称');
    return;
  }
  if (!formData.serviceIp?.trim()) {
    ElMessage.warning('请输入服务IP地址');
    return;
  }
  if (!formData.servicePort) {
    ElMessage.warning('请输入服务端口');
    return;
  }

  try {
    // 默认使用openai前缀
    const modelIdentifier = `openai/${formData.deployName}`;
    const serviceUrl = `http://${formData.serviceIp}:${formData.servicePort}`;

    await createModel({
      model_name: formData.name,
      litellm_params: {
        model: modelIdentifier,
        api_base: serviceUrl,
      },
      instance_url: formData.metricsUrl || undefined,
      inference_engine: formData.deployFramework || undefined,
    });
    ElMessage.success('模型创建成功');
    showAddModal.value = false;
    await loadModels();
  } catch (e) {
    ElMessage.error('创建模型失败: ' + (e instanceof Error ? e.message : '未知错误'));
  }
}

watch([activeFilter, searchQuery], () => { loadModels(); });
onMounted(() => { loadModels(); loadOverviewData(); });
</script>

<template>
  <section class="page inference-dashboard">
    <h1 class="page-title">推理模型</h1>

    <!-- Overview Card -->
    <div class="overview-card">
      <div class="overview-card__header">
        <div class="overview-card__title"><span>调用概览</span></div>
        <button class="overview-card__detail" @click="router.push({ name: 'inference-model-call-analysis' })">查看详情 <el-icon :size="14"><ArrowRight /></el-icon></button>
      </div>
      <div v-if="overviewError" class="overview-card__error">加载失败: {{ overviewError }}</div>
      <div v-else class="overview-card__content">
        <div class="overview-card__section">
          <div class="overview-card__section-header"><span>调用次数</span></div>
          <div class="overview-card__metrics">
            <div class="overview-card__metric"><span class="overview-card__metric-label">今日</span><span class="overview-card__metric-value">{{ overviewData.today.requests.toLocaleString() }}<span class="overview-card__metric-unit">次</span></span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">本周</span><span class="overview-card__metric-value">{{ overviewData.week.requests.toLocaleString() }}<span class="overview-card__metric-unit">次</span></span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">累计</span><span class="overview-card__metric-value">{{ overviewData.total.requests.toLocaleString() }}<span class="overview-card__metric-unit">次</span></span></div>
          </div>
        </div>
        <div class="overview-card__divider"></div>
        <div class="overview-card__section">
          <div class="overview-card__section-header"><span>Token数</span></div>
          <div class="overview-card__metrics">
            <div class="overview-card__metric"><span class="overview-card__metric-label">今日</span><span class="overview-card__metric-value">{{ formatTokens(overviewData.today.tokens) }}</span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">本周</span><span class="overview-card__metric-value">{{ formatTokens(overviewData.week.tokens) }}</span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">累计</span><span class="overview-card__metric-value">{{ formatTokens(overviewData.total.tokens) }}</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Model Cards -->
    <div class="card model-list-card">
      <div class="model-section__header">
        <h2 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary)">可用推理模型</h2>
        <button class="btn btn--primary" @click="showAddModal = true"><el-icon :size="16"><Plus /></el-icon> 添加模型</button>
      </div>
      <div class="model-section__toolbar">
        <div class="filter-tabs">
          <button v-for="f in filters" :key="f.key" class="filter-tab" :class="{ 'filter-tab--active': activeFilter === f.key }" @click="activeFilter = f.key">{{ f.label }}</button>
        </div>
        <ElInput v-model="searchQuery" placeholder="请输入搜索内容" :prefix-icon="Search" clearable style="width: 240px" />
      </div>
      <div class="model-grid">
        <ModelCard v-for="model in models" :key="model.id" v-bind="model" :icon-src="model.iconSrc" :is-admin="isAdmin" @click="goToModel(model.id)" @delete="handleDeleteModel(model.id)" @edit="handleEditModel(model.id)" @restart="handleRestartModel(model.id)" />
      </div>
    </div>

    <AddModelModal :visible="showAddModal" @close="showAddModal = false" @save="handleAddModel" />
    <ModelInfoDrawer :visible="drawerVisible" :mode="drawerMode" :model="selectedModel" @close="drawerVisible = false" @edit="drawerMode = 'edit'" @save="handleSaveModel" @export="() => {}" />
  </section>
</template>

<style scoped>
.inference-dashboard {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  box-sizing: border-box;
}

.overview-card { background: #fff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 20px; margin-top: 20px; flex-shrink: 0; }
.overview-card__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.overview-card__title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; color: #111827; }
.overview-card__detail { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #2563eb; background: none; border: none; cursor: pointer; }
.overview-card__detail:hover { opacity: 0.8; }
.overview-card__content { display: flex; gap: 0; }
.overview-card__section { flex: 1; padding: 0 20px; }
.overview-card__section:first-child { padding-left: 0; }
.overview-card__section:last-child { padding-right: 0; }
.overview-card__divider { width: 1px; background: #e5e7eb; margin: 0 20px; }
.overview-card__section-header { font-size: 13px; color: #6b7280; margin-bottom: 12px; }
.overview-card__metrics { display: flex; gap: 24px; margin-bottom: 16px; }
.overview-card__metric { display: flex; flex-direction: column; gap: 2px; }
.overview-card__metric-label { font-size: 12px; color: #9ca3af; }
.overview-card__metric-value { font-size: 24px; font-weight: 600; color: #111827; }
.overview-card__metric-unit { font-size: 12px; font-weight: 400; color: #6b7280; margin-left: 2px; }
.overview-card__error { padding: 16px; color: #dc2626; font-size: 14px; }

.model-list-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-top: 24px;
}

.model-section__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-shrink: 0; }
.model-section__toolbar { display: flex; align-items: center; gap: 24px; margin-bottom: 20px; flex-shrink: 0; }
.model-grid {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
  gap: 28px;
  align-content: start;
}
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; font-size: 14px; font-weight: 500; border: 1px solid var(--border-color, #d1d5db); border-radius: 6px; background: #fff; color: var(--text-primary, #1f2937); cursor: pointer; }
.btn--primary { background: #2563eb; border-color: #2563eb; color: #fff; }
.btn--primary:hover { background: #1d4ed8; }
</style>
