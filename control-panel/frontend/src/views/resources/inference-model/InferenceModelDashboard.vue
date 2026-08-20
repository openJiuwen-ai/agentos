<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessageBox, ElButton, ElTabs, ElTabPane, ElAlert, ElSkeleton, ElEmpty, ElMessage } from 'element-plus';
import ModelCard from './ModelCard.vue';
import AddModelModal from './AddModelModal.vue';
import ModelInfoDrawer from './ModelInfoDrawer.vue';
import ModelUsageGuide from './ModelUsageGuide.vue';
import OverviewStatCard from './OverviewStatCard.vue';
import {
  fetchModelList,
  fetchModelsHealth,
  fetchModelDetail,
  createModel,
  updateModel,
  deleteModel,
  restartModel,
  fetchUsageOverview,
  fetchUserUsage,
  fetchGatewayConfig,
} from '@/api/inference';
import type { ModelDetail } from '@/api/inference';
import { useAuth } from '@/composables/useAuth';
import {
  calculateOverviewTotals,
  calculateUserTotals,
  formatTokens,
  getDateRange,
  USAGE_ALL_TIME_START,
} from './utils/usage';
import apiCallIcon from '@/assets/images/api_call.svg';
import tokenIcon from '@/assets/images/token.svg';
import personIcon from '@/assets/images/person.svg';
import dataStatisticsIcon from '@/assets/images/data_statistics.svg';

const router = useRouter();
const { effectiveIsAdmin: isAdmin, userId } = useAuth();
const loading = ref(false);
const listError = ref('');

interface ModelCardData {
  id: string;
  name: string;
  status: 'success' | 'error' | 'warning';
  statusText: string;
  statusKey: 'healthy' | 'unhealthy' | 'unknown';
  tags: string[];
  e2eP95: string;
  todayCalls: string;
  todayTokens: string;
  meta: string[];
  iconSrc: undefined;
  contextWindow?: number | null;
}

const models = ref<ModelCardData[]>([]);
const gatewayUrl = ref<string>('');
const exampleModelName = computed(() => models.value[0]?.name ?? '');
const exampleContextWindow = computed(() => models.value[0]?.contextWindow ?? null);
const activeFilter = ref('all');
const searchQuery = ref('');
const showAddModal = ref(false);
const drawerVisible = ref(false);
const drawerMode = ref<'view' | 'edit'>('view');
const selectedModel = ref<ModelDetail | null>(null);

const filters = [
  { key: 'all', label: '全部状态' },
  { key: 'healthy', label: '健康' },
  { key: 'unhealthy', label: '异常' },
  { key: 'unknown', label: '未知' },
];

const filteredModels = computed(() => {
  if (activeFilter.value === 'all') return models.value;
  return models.value.filter((m) => m.statusKey === activeFilter.value);
});

// 调用概览数据
const overviewData = ref({
  today: { requests: 0, tokens: 0 },
  week: { requests: 0, tokens: 0 },
  total: { requests: 0, tokens: 0 },
});
const overviewError = ref('');
const activeUsersCount = ref(0);

const overviewCards = computed(() => [
  {
    key: 'requests',
    title: '调用次数',
    value: overviewData.value.today.requests.toLocaleString(),
    desc: '今日调用次数',
    icon: apiCallIcon,
  },
  {
    key: 'tokens',
    title: 'Token数',
    value: formatTokens(overviewData.value.today.tokens),
    desc: '今日Token使用量',
    icon: tokenIcon,
  },
  {
    key: 'users',
    title: '用户',
    value: isAdmin.value ? String(activeUsersCount.value) : '--',
    desc: '近一周活跃用户数',
    icon: personIcon,
  },
  {
    key: 'status',
    title: '调用状况',
    value: '--',
    desc: '实时并发数 QPS',
    icon: dataStatisticsIcon,
  },
]);

async function loadOverviewData() {
  overviewError.value = '';
  try {
    if (isAdmin.value) {
      // 管理员：使用 /overview 接口获取所有用户数据
      const [todayRes, weekRes, totalRes] = await Promise.all([
        fetchUsageOverview(getDateRange(0)),
        fetchUsageOverview(getDateRange(7)),
        fetchUsageOverview(getDateRange(USAGE_ALL_TIME_START)),
      ]);

      overviewData.value = {
        today: calculateOverviewTotals(todayRes),
        week: calculateOverviewTotals(weekRes),
        total: calculateOverviewTotals(totalRes),
      };
      activeUsersCount.value = weekRes.users?.filter((u) => u.total_requests > 0).length || 0;
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
        fetchUserUsage({ user_id: uid, ...getDateRange(USAGE_ALL_TIME_START) }),
      ]);

      overviewData.value = {
        today: calculateUserTotals(todayRes),
        week: calculateUserTotals(weekRes),
        total: calculateUserTotals(totalRes),
      };
      activeUsersCount.value = 0;
    }
  } catch (e) {
    console.error('加载调用概览数据失败:', e);
    overviewError.value = e instanceof Error ? e.message : '加载调用概览数据失败';
  }
}

function mapModelStatus(rawStatus?: string): { status: 'success' | 'error' | 'warning'; statusText: string } {
  const statusMap: Record<string, { status: 'success' | 'error' | 'warning'; statusText: string }> = {
    healthy: { status: 'success', statusText: '健康' },
    unhealthy: { status: 'error', statusText: '异常' },
  };
  return statusMap[rawStatus ?? ''] ?? { status: 'warning', statusText: '未知' };
}

async function loadModels() {
  loading.value = true;
  listError.value = '';
  try {
    const data = await fetchModelList({ keyword: searchQuery.value });
    // 将后端数据转换为ModelCard期望的格式
    models.value =
      data?.items?.map((item) => {
        // mapModelStatus 返回 status 和 statusText，statusKey 需要根据 status 额外处理
        const { status, statusText } = mapModelStatus(item.status);
        let statusKey: ModelCardData['statusKey'];
        if (item.status === 'healthy') {
          statusKey = 'healthy';
        } else if (item.status === 'unhealthy') {
          statusKey = 'unhealthy';
        } else {
          statusKey = 'unknown';
        }
        const mapped = { status, statusText, statusKey };
        return {
          id: item.id,
          name: item.model_name,
          status: mapped.status,
          statusText: mapped.statusText,
          statusKey: mapped.statusKey,
          tags: [],
          e2eP95: '--',
          todayCalls: '--',
          todayTokens: '--',
          meta: [item.litellm_params.model],
          iconSrc: undefined,
          contextWindow: item.model_info?.context_window,
        };
      }) ?? [];
    // 列表渲染后异步刷新健康状态，不阻塞
    void refreshModelsHealth();
  } catch (e) {
    models.value = [];
    listError.value = e instanceof Error ? e.message : '加载模型列表失败';
  } finally {
    loading.value = false;
  }
}

async function refreshModelsHealth() {
  try {
    const healthMap = await fetchModelsHealth();
    if (!healthMap) return;
    models.value = models.value.map((m) => {
      const raw = healthMap[m.id];
      if (!raw) return m;
      const { status, statusText } = mapModelStatus(raw);
      return { ...m, status, statusText };
    });
  } catch (e) {
    console.error('刷新模型健康状态失败:', e);
  }
}

function goToModel(id: string) {
  router.push({ name: 'inference-model-detail', params: { id } });
}
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

async function handleRestartModel(id: string) {
  try {
    await restartModel(id);
    await loadModels();
  } catch (e) {
    console.error(e);
  }
}

async function handleAddModel(formData: {
  name: string;
  contextLength: number | null;
  deployName: string;
  deployFramework: string;
  serviceUrl: string;
  metricsUrl: string;
  apiKey?: string;
  description?: string;
}) {
  // 必填项验证
  if (!formData.name?.trim()) {
    ElMessage.warning('请输入模型名称');
    return;
  }
  if (!formData.deployName?.trim()) {
    ElMessage.warning('请输入部署模型名称');
    return;
  }
  if (!formData.serviceUrl?.trim()) {
    ElMessage.warning('请输入服务访问地址');
    return;
  }
  if (!formData.deployFramework) {
    ElMessage.warning('请选择部署框架');
    return;
  }

  try {
    // 默认使用openai前缀
    const modelIdentifier = `openai/${formData.deployName}`;

    await createModel({
      model_name: formData.name,
      litellm_params: {
        model: modelIdentifier,
        api_base: formData.serviceUrl,
        api_key: formData.apiKey || 'sk-1234',
      },
      model_info: {
        ...(formData.description ? { description: formData.description } : {}),
        ...(formData.contextLength ? { context_window: formData.contextLength } : {}),
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

async function loadGatewayConfig() {
  try {
    const data = await fetchGatewayConfig();
    gatewayUrl.value = data?.gateway_url ?? '';
  } catch (e) {
    console.error('获取 Gateway 配置失败:', e);
  }
}

onMounted(() => {
  loadModels();
  loadOverviewData();
  loadGatewayConfig();
});
</script>

<template>
  <section class="page inference-dashboard">
    <h1 class="page-title">推理模型</h1>

    <!-- 今日调用分析 -->
    <section class="analysis-section">
      <div class="analysis-section__header">
        <h2 class="analysis-section__title">今日调用分析</h2>
        <ElButton
          class="analysis-section__detail"
          link
          type="primary"
          @click="router.push({ name: 'inference-model-call-analysis' })"
        >
          查看详情
        </ElButton>
      </div>
      <ElAlert v-if="overviewError" :title="`加载失败: ${overviewError}`" type="error" show-icon :closable="false" />
      <div v-else class="analysis-grid">
        <OverviewStatCard
          v-for="card in overviewCards"
          :key="card.key"
          variant="hero"
          :title="card.title"
          :value="card.value"
          :desc="card.desc"
          :icon="card.icon"
        />
      </div>
    </section>

    <!-- 可用推理模型 -->
    <section class="model-section">
      <div class="model-section__header">
        <h2 class="model-section__title">可用推理模型</h2>
        <div class="model-section__actions">
          <ElButton v-if="isAdmin" type="primary" @click="showAddModal = true">添加模型</ElButton>
        </div>
      </div>
      <ElTabs v-model="activeFilter" class="model-section__tabs">
        <ElTabPane v-for="f in filters" :key="f.key" :name="f.key" :label="f.label" />
      </ElTabs>
      <div v-if="loading" class="model-list-state">
        <ElSkeleton :rows="6" animated />
      </div>
      <ElAlert v-else-if="listError" :title="listError" type="error" show-icon :closable="false" />
      <div v-else-if="!filteredModels.length" class="model-list-state">
        <ElEmpty description="暂无推理模型" :image-size="80" />
      </div>
      <div v-else class="model-grid">
        <ModelCard
          v-for="model in filteredModels"
          :key="model.id"
          v-bind="model"
          :icon-src="model.iconSrc"
          :is-admin="isAdmin"
          @click="goToModel(model.id)"
          @delete="handleDeleteModel(model.id)"
          @edit="handleEditModel(model.id)"
          @restart="handleRestartModel(model.id)"
        />
      </div>
    </section>

    <ModelUsageGuide
      :gateway-url="gatewayUrl"
      :example-model-name="exampleModelName"
      :example-context-window="exampleContextWindow"
    />

    <AddModelModal :visible="showAddModal" @close="showAddModal = false" @save="handleAddModel" />
    <ModelInfoDrawer
      :visible="drawerVisible"
      :mode="drawerMode"
      :model="selectedModel"
      @close="drawerVisible = false"
      @edit="drawerMode = 'edit'"
      @save="handleSaveModel"
    />
  </section>
</template>

<style scoped>
.inference-dashboard {
  display: flex;
  flex-direction: column;
  flex: 1 0 auto;
  box-sizing: border-box;
  gap: 40px;
}

.inference-dashboard .page-title {
  font-size: 18px;
  font-weight: 700;
  line-height: 26px;
  color: var(--text-primary);
}

.analysis-section,
.model-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.analysis-section__header,
.model-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.analysis-section__title,
.model-section__title {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: rgba(0, 0, 0, 0.9);
}

.analysis-section__detail {
  height: auto;
  padding: 0;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 24px;
}

.model-section__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-section__tabs {
  margin-top: -8px;
}

.model-section__tabs :deep(.el-tabs__header) {
  margin: 0;
}

.model-section__tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: #dfdfdf;
}

.model-section__tabs :deep(.el-tabs__item) {
  height: 32px;
  padding: 0 0 8px;
  margin-right: 32px;
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
  color: var(--text-secondary);
}

.model-section__tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-primary);
}

.model-section__tabs :deep(.el-tabs__active-bar) {
  height: 2px;
  border-radius: 1px;
  background-color: var(--color-primary);
}

.model-section__tabs :deep(.el-tabs__content) {
  display: none;
}

.model-list-state {
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 24px;
  align-content: start;
}

@media (max-width: 1400px) {
  .analysis-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .model-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .analysis-grid,
  .model-grid {
    grid-template-columns: 1fr;
  }
}
</style>
