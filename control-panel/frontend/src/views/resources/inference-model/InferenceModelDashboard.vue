<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessageBox, ElButton, ElTabs, ElTabPane, ElAlert, ElSkeleton, ElSkeletonItem, ElEmpty, ElMessage } from 'element-plus';
import * as echarts from 'echarts';
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
  fetchUsageOverview,
  fetchUserUsage,
  fetchUserModelTrend,
  fetchGatewayConfig,
} from '@/api/inference';
import type { ModelDetail, ModelTrendResponse } from '@/api/inference';
import { useAuth } from '@/composables/useAuth';
import {
  calculateOverviewTotals,
  calculateUserTotals,
  formatTokens,
  getDateRange,
  generateDateSeriesFromRange,
  USAGE_ALL_TIME_START,
} from './utils/usage';
import apiCallIcon from '@/assets/images/api_call.svg';
import tokenIcon from '@/assets/images/token.svg';
import personIcon from '@/assets/images/person.svg';
import dataStatisticsIcon from '@/assets/images/data_statistics.svg';

const router = useRouter();
const { effectiveIsAdmin: isAdmin } = useAuth();
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
const gatewayUrl = ref('');
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
const overviewLoading = ref(false);
const activeUsersCount = ref(0);
const successRate = ref(0);
/** 个人工作台图表：与调用分析「模型调用量」同源 fetchUserModelTrend */
const userModelTrendData = ref<ModelTrendResponse | null>(null);

const requestsChartRef = ref<HTMLElement | null>(null);
const tokensChartRef = ref<HTMLElement | null>(null);
let requestsChart: echarts.ECharts | null = null;
let tokensChart: echarts.ECharts | null = null;

const adminOverviewCards = computed(() => [
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
    value: String(activeUsersCount.value),
    desc: '近一周活跃用户数',
    icon: personIcon,
  },
  {
    key: 'status',
    title: '调用状况',
    value: successRate.value >= 0 ? successRate.value + '%' : '--',
    desc: '近一周请求成功率',
    icon: dataStatisticsIcon,
  },
]);

const userTrendCards = computed(() => [
  {
    key: 'requests',
    title: '调用次数',
    icon: apiCallIcon,
    metrics: [
      { label: '今日', value: overviewData.value.today.requests.toLocaleString() },
      { label: '本周', value: overviewData.value.week.requests.toLocaleString() },
      { label: '累计', value: overviewData.value.total.requests.toLocaleString() },
    ],
  },
  {
    key: 'tokens',
    title: 'Token数',
    icon: tokenIcon,
    metrics: [
      { label: '今日', value: formatTokens(overviewData.value.today.tokens) },
      { label: '本周', value: formatTokens(overviewData.value.week.tokens) },
      { label: '累计', value: formatTokens(overviewData.value.total.tokens) },
    ],
  },
]);

function formatAxisDate(dateStr: string) {
  const parts = dateStr.split('-');
  if (parts.length < 3) return dateStr;
  return `${Number(parts[1])}-${Number(parts[2])}`;
}

/** 与 CallAnalysis.renderModelChart 相同：按日汇总各模型 metric */
function buildSeriesFromModelTrend(metric: 'requests' | 'tokens') {
  const data = userModelTrendData.value;
  if (!data?.start_date || !data?.end_date) {
    return { dates: [] as string[], values: [] as number[] };
  }
  const dates = generateDateSeriesFromRange(data.start_date, data.end_date);
  const items = (data.items ?? []).filter((m) => m.model?.trim());
  const byDate = new Map<string, number>();
  for (const d of dates) byDate.set(d, 0);
  for (const item of items) {
    if (!byDate.has(item.date)) continue;
    byDate.set(item.date, (byDate.get(item.date) || 0) + item[metric]);
  }
  return {
    dates: dates.map(formatAxisDate),
    values: dates.map((d) => byDate.get(d) || 0),
  };
}

function formatAxisValue(v: number) {
  if (v >= 10000) return (v / 10000).toFixed(1) + 'w';
  if (v >= 1000) return (v / 1000).toFixed(1) + 'k';
  return String(v);
}

function renderRequestsChart() {
  if (!requestsChartRef.value) return;
  if (!requestsChart) {
    requestsChart = echarts.init(requestsChartRef.value);
  }
  // 数据同源 CallAnalysis.fetchUserModelTrend；展示按设计稿为单色柱（日总量）
  const { dates, values } = buildSeriesFromModelTrend('requests');
  requestsChart.setOption(
    {
      grid: { left: 8, right: 8, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: '#e5e7eb',
        borderWidth: 1,
        textStyle: { color: '#333', fontSize: 12 },
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { fontSize: 12, color: '#aeaeae' },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        name: '次',
        nameGap: 8,
        nameTextStyle: { fontSize: 12, color: '#777', align: 'left', padding: [0, 0, 0, 0] },
        axisLabel: { fontSize: 12, color: '#aeaeae', formatter: formatAxisValue },
        splitLine: { lineStyle: { color: '#f0f0f0' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: values,
          barWidth: 16,
          itemStyle: { color: '#2070f3', borderRadius: [2, 2, 0, 0] },
        },
      ],
    },
    true,
  );
}

function renderTokensChart() {
  if (!tokensChartRef.value) return;
  if (!tokensChart) {
    tokensChart = echarts.init(tokensChartRef.value);
  }
  const { dates, values } = buildSeriesFromModelTrend('tokens');
  tokensChart.setOption(
    {
      grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: '#e5e7eb',
        borderWidth: 1,
        textStyle: { color: '#333', fontSize: 12 },
        valueFormatter: (v: unknown) => formatTokens(Number(v ?? 0)),
      },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLabel: { fontSize: 12, color: '#aeaeae' },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        name: 'Token数',
        nameGap: 8,
        nameTextStyle: { fontSize: 12, color: '#777', align: 'left', padding: [0, 0, 0, 0] },
        axisLabel: {
          fontSize: 12,
          color: '#aeaeae',
          // 与 CallAnalysis「模型调用量」Token 曲线纵坐标一致（k / w）
          formatter: formatAxisValue,
        },
        splitLine: { lineStyle: { color: '#f0f0f0' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'line',
          data: values,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          showSymbol: false,
          lineStyle: { color: '#2070f3', width: 2 },
          itemStyle: { color: '#2070f3' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(32, 112, 243, 0.28)' },
              { offset: 1, color: 'rgba(32, 112, 243, 0.02)' },
            ]),
          },
        },
      ],
    },
    true,
  );
}

function setRequestsChartEl(
  el: Element | { $el?: unknown } | null,
  _refs?: Record<string, unknown>,
) {
  void _refs;
  requestsChartRef.value = el instanceof HTMLElement ? el : null;
  tryRenderUserCharts();
}

function setTokensChartEl(
  el: Element | { $el?: unknown } | null,
  _refs?: Record<string, unknown>,
) {
  void _refs;
  tokensChartRef.value = el instanceof HTMLElement ? el : null;
  tryRenderUserCharts();
}

function tryRenderUserCharts() {
  if (isAdmin.value) return;
  if (!requestsChartRef.value || !tokensChartRef.value) return;
  renderRequestsChart();
  renderTokensChart();
}

function renderUserCharts() {
  nextTick(() => {
    tryRenderUserCharts();
  });
}

function disposeUserCharts() {
  requestsChart?.dispose();
  tokensChart?.dispose();
  requestsChart = null;
  tokensChart = null;
}

function resizeUserCharts() {
  requestsChart?.resize();
  tokensChart?.resize();
}

function goCallAnalysis() {
  router.push({ name: 'inference-model-call-analysis' });
}

async function loadGatewayConfig() {
  try {
    const data = await fetchGatewayConfig();
    gatewayUrl.value = data?.gateway_url ?? '';
  } catch (e) {
    console.error('获取 Gateway 配置失败:', e);
  }
}

async function loadOverviewData() {
  overviewError.value = '';
  overviewLoading.value = true;
  disposeUserCharts();
  try {
    if (isAdmin.value) {
      userModelTrendData.value = null;
      disposeUserCharts();
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
      successRate.value = weekRes.success_rate ?? 0;
    } else {
      // 指标：/usage/user；图表：与调用分析「模型调用量」相同 /usage/user-model-trend
      const chartRange = getDateRange(7);
      const [todayRes, weekRes, totalRes, trendRes] = await Promise.all([
        fetchUserUsage(getDateRange(0)),
        fetchUserUsage(getDateRange(7)),
        fetchUserUsage({ start_date: USAGE_ALL_TIME_START, end_date: getDateRange(0).end_date }),
        fetchUserModelTrend(chartRange),
      ]);

      overviewData.value = {
        today: calculateUserTotals(todayRes),
        week: calculateUserTotals(weekRes),
        total: calculateUserTotals(totalRes),
      };
      activeUsersCount.value = 0;
      successRate.value = weekRes.success_rate ?? 0;
      userModelTrendData.value = trendRes
        ? {
            ...trendRes,
            start_date: trendRes.start_date || chartRange.start_date,
            end_date: trendRes.end_date || chartRange.end_date,
          }
        : { start_date: chartRange.start_date, end_date: chartRange.end_date, items: [] };
    }
  } catch (e) {
    console.error('加载调用概览数据失败:', e);
    overviewError.value = e instanceof Error ? e.message : '加载调用概览数据失败';
  } finally {
    overviewLoading.value = false;
    if (!isAdmin.value) {
      renderUserCharts();
    }
  }
}

function mapModelStatus(rawStatus?: string): {
  status: 'success' | 'error' | 'warning';
  statusText: string;
  statusKey: 'healthy' | 'unhealthy' | 'unknown';
} {
  const statusMap: Record<
    string,
    { status: 'success' | 'error' | 'warning'; statusText: string; statusKey: 'healthy' | 'unhealthy' | 'unknown' }
  > = {
    healthy: { status: 'success', statusText: '健康', statusKey: 'healthy' },
    unhealthy: { status: 'error', statusText: '异常', statusKey: 'unhealthy' },
  };
  return statusMap[rawStatus ?? ''] ?? { status: 'warning', statusText: '未知', statusKey: 'unknown' };
}

async function loadModels() {
  loading.value = true;
  listError.value = '';
  try {
    const data = await fetchModelList({ keyword: searchQuery.value });
    // 将后端数据转换为ModelCard期望的格式
    models.value =
      data?.items?.map((item) => {
        const { status, statusText, statusKey } = mapModelStatus(item.status);
        return {
          id: item.id,
          name: item.model_name,
          status,
          statusText,
          statusKey,
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
      const { status, statusText, statusKey } = mapModelStatus(raw);
      return { ...m, status, statusText, statusKey };
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

async function handleAddModel(formData: {
  name: string;
  contextLength: number | null;
  deployName: string;
  serviceUrl: string;
  metrics_endpoints: Array<{ inference_engine: string; instance_url: string }>;
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
      metrics_endpoints: formData.metrics_endpoints ?? [],
    });
    ElMessage.success('模型创建成功');
    showAddModal.value = false;
    await loadModels();
  } catch (e) {
    ElMessage.error('创建模型失败: ' + (e instanceof Error ? e.message : '未知错误'));
  }
}

watch(isAdmin, () => {
  void loadOverviewData();
});

watch(
  [requestsChartRef, tokensChartRef, userModelTrendData],
  () => {
    if (!isAdmin.value && userModelTrendData.value) {
      renderUserCharts();
    }
  },
  { flush: 'post' },
);

onMounted(() => {
  loadModels();
  loadOverviewData();
  loadGatewayConfig();
  window.addEventListener('resize', resizeUserCharts);
});

onUnmounted(() => {
  window.removeEventListener('resize', resizeUserCharts);
  disposeUserCharts();
});
</script>

<template>
  <section class="page inference-dashboard">
    <h1 class="title-l1">推理模型监控</h1>

    <!-- 今日调用分析：查看详情与下方模型列表加载状态无关，始终可跳转 -->
    <section class="analysis-section">
      <div v-if="isAdmin" class="analysis-section__header">
        <h2 class="title-l2">今日调用分析</h2>
        <ElButton class="analysis-section__detail" link type="primary" @click="goCallAnalysis">
          查看详情
        </ElButton>
      </div>

      <template v-if="isAdmin">
        <ElAlert
          v-if="overviewError"
          :title="`加载失败: ${overviewError}`"
          type="error"
          show-icon
          :closable="false"
        />
        <div v-else-if="overviewLoading" class="analysis-grid">
          <ElSkeleton v-for="i in 4" :key="i" animated class="analysis-hero-skeleton">
            <template #template>
              <ElSkeletonItem variant="rect" class="analysis-hero-skeleton__block" />
            </template>
          </ElSkeleton>
        </div>
        <div v-else class="analysis-grid">
          <OverviewStatCard
            v-for="card in adminOverviewCards"
            :key="card.key"
            variant="hero"
            :title="card.title"
            :value="card.value"
            :desc="card.desc"
            :icon="card.icon"
          />
        </div>
      </template>

      <template v-else>
        <ElAlert
          v-if="overviewError"
          :title="`加载失败: ${overviewError}`"
          type="error"
          show-icon
          :closable="false"
        />
        <div v-else class="analysis-grid analysis-grid--user">
          <OverviewStatCard
            variant="trend"
            :title="userTrendCards[0].title"
            :icon="userTrendCards[0].icon"
            :metrics="userTrendCards[0].metrics"
          >
            <ElSkeleton v-if="overviewLoading" animated class="analysis-trend-skeleton">
              <template #template>
                <ElSkeletonItem variant="rect" class="analysis-trend-skeleton__block" />
              </template>
            </ElSkeleton>
            <div v-else :ref="setRequestsChartEl" class="analysis-trend-chart" />
          </OverviewStatCard>
          <OverviewStatCard
            variant="trend"
            :title="userTrendCards[1].title"
            :icon="userTrendCards[1].icon"
            :metrics="userTrendCards[1].metrics"
          >
            <ElSkeleton v-if="overviewLoading" animated class="analysis-trend-skeleton">
              <template #template>
                <ElSkeletonItem variant="rect" class="analysis-trend-skeleton__block" />
              </template>
            </ElSkeleton>
            <div v-else :ref="setTokensChartEl" class="analysis-trend-chart" />
          </OverviewStatCard>
        </div>
      </template>
    </section>

    <!-- 可用推理模型 -->
    <section class="model-section">
      <div class="model-section__header">
        <h2 class="title-l2">可用推理模型</h2>
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
}

.analysis-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: 24px;
}

.model-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: 40px;
}

.inference-dashboard > :deep(.usage-guide-section) {
  margin-top: 40px;
}

.analysis-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 26px;
}

.model-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 32px;
}

.analysis-section__detail {
  height: 26px;
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

.analysis-grid--user {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.analysis-hero-skeleton {
  width: 100%;
  min-height: 120px;
}

.analysis-hero-skeleton__block {
  width: 100%;
  height: 120px;
  border-radius: var(--radius-2xl);
}

.analysis-trend-chart {
  width: 100%;
  height: 140px;
}

.analysis-trend-skeleton {
  width: 100%;
  height: 140px;
}

.analysis-trend-skeleton__block {
  width: 100%;
  height: 140px;
  border-radius: 8px;
}

.model-section__actions {
  display: flex;
  align-items: center;
  gap: 8px;
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
  .analysis-grid:not(.analysis-grid--user) {
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
