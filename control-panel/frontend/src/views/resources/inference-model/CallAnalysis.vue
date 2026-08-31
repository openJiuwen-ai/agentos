<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import * as echarts from 'echarts';
import {
  ElAlert,
  ElDatePicker,
  ElEmpty,
  ElMessageBox,
  ElSegmented,
  ElSelect,
  ElOption,
  ElSkeleton,
  ElTable,
  ElTableColumn,
} from 'element-plus';
import { fetchUsageOverview, fetchUsageByUser, fetchModelTrend } from '@/api/inference';
import type { UserUsageRankResponse, ModelTrendResponse } from '@/api/inference';
import {
  calculateOverviewTotals,
  formatDate,
  formatTokens,
  generateDateSeriesFromRange,
  getDateRange,
} from './utils/usage';
import OverviewStatCard from './OverviewStatCard.vue';
import apiCallTimesIcon from '@/assets/images/api_call.svg';
import tokenIcon from '@/assets/images/token.svg';
import personIcon from '@/assets/images/person.svg';
import dataStatisticsIcon from '@/assets/images/data_statistics.svg';

const loading = ref(false);
const error = ref('');

// 趋势图时间范围选择
type TrendPreset = '12h' | '24h' | '7d' | '30d';

const trendPreset = ref<TrendPreset | ''>('12h');
const customDateRange = ref<[Date, Date] | null>(null);
const trendPresetOptions = [
  { label: '近12小时', value: '12h' },
  { label: '近24小时', value: '24h' },
  { label: '近7天', value: '7d' },
  { label: '近30天', value: '30d' },
];

// ECharts 实例
const adminChartRef = ref<HTMLElement | null>(null);
const activeUsersChartRef = ref<HTMLElement | null>(null);
let adminChart: echarts.ECharts | null = null;
let activeUsersChart: echarts.ECharts | null = null;
let adminChartLineTimer: number | null = null;

function resizeCharts() {
  adminChart?.resize();
  activeUsersChart?.resize();
}

// 管理员数据
const userRankData = ref<UserUsageRankResponse | null>(null);
const userRankTop = ref(10);
const activeUserTrendData = ref<Array<{ date: string; count: number }>>([]);
const modelUsageData = ref<ModelTrendResponse | null>(null);

// 调用概览数据（今日/本周/累计）
const overviewStats = ref({
  today: { requests: 0, tokens: 0 },
  week: { requests: 0, tokens: 0 },
  total: { requests: 0, tokens: 0 },
});

// 活跃用户数 / 总用户数（管理员概览）
const activeUsersCount = ref(0);
const totalUsersCount = ref(0);
const successRate = ref(0);

function formatRequests(requests: number): string {
  return requests.toLocaleString();
}

const overviewCards = computed(() => {
  const cards = [
    {
      key: 'requests',
      title: '调用次数',
      icon: apiCallTimesIcon,
      metrics: [
        { value: formatRequests(overviewStats.value.today.requests), label: '今日', hero: true },
        { value: formatRequests(overviewStats.value.week.requests), label: '本周' },
        { value: formatRequests(overviewStats.value.total.requests), label: '累计' },
      ],
    },
    {
      key: 'tokens',
      title: 'Token数',
      icon: tokenIcon,
      metrics: [
        { value: formatTokens(overviewStats.value.today.tokens), label: '今日', hero: true },
        { value: formatTokens(overviewStats.value.week.tokens), label: '本周' },
        { value: formatTokens(overviewStats.value.total.tokens), label: '累计' },
      ],
    },
  ];

  cards.push({
    key: 'status',
    title: '调用状况',
    icon: dataStatisticsIcon,
    metrics: [
      { value: '--', label: '实时并发数 QPS', hero: true },
      { value: successRate.value >= 0 ? successRate.value + '%' : '--', label: '近一周请求成功率' },
    ],
  });

  cards.splice(2, 0, {
    key: 'users',
    title: '用户',
    icon: personIcon,
    metrics: [
      { value: String(activeUsersCount.value), label: '近一周活跃用户数', hero: true },
      { value: String(totalUsersCount.value), label: '总用户数' },
    ],
  });

  return cards;
});

const userRankRows = computed(() =>
  [...(userRankData.value?.items ?? [])]
    .sort((a, b) => b.tokens - a.tokens)
    .map((user, index) => ({
      ...user,
      rank: index + 1,
      tokensText: formatTokens(user.tokens),
      requestsText: user.requests.toLocaleString(),
    })),
);

type DateRange = { start_date: string; end_date: string };

const daysByPreset: Record<TrendPreset, number> = {
  '12h': 0,
  '24h': 1,
  '7d': 7,
  '30d': 30,
};

function getPresetRange(preset: TrendPreset): DateRange {
  return getDateRange(daysByPreset[preset]);
}

function getCurrentTrendRange(): DateRange {
  if (customDateRange.value) {
    return {
      start_date: formatDate(customDateRange.value[0]),
      end_date: formatDate(customDateRange.value[1]),
    };
  }
  if (trendPreset.value) {
    return getPresetRange(trendPreset.value);
  }
  return getDateRange(7);
}

function renderActiveUsersChart() {
  if (!activeUsersChart) return;

  activeUsersChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: {
      left: '3%',
      right: '4%',
      bottom: 40,
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: activeUserTrendData.value.map((item) => item.date.slice(5)),
      axisLabel: { fontSize: 11, color: '#999' },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '用户数',
      minInterval: 1,
      axisLabel: { fontSize: 11, color: '#999' },
      splitLine: { lineStyle: { color: '#f3f4f6' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        name: '活跃用户数',
        type: 'line',
        data: activeUserTrendData.value.map((item) => item.count),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#f4840c', width: 2 },
        itemStyle: { color: '#f4840c' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(244, 132, 12, 0.18)' },
            { offset: 1, color: 'rgba(244, 132, 12, 0)' },
          ]),
        },
      },
    ],
  });
}

async function loadUserRank(range: DateRange) {
  try {
    userRankData.value = await fetchUsageByUser({ ...range, top: userRankTop.value });
  } catch (e) {
    console.warn('加载用户排名失败:', e);
  }
}

async function handleUserRankTopChange(value: string | number | boolean) {
  const num = Number(value);
  if (num === -2) {
    // 自定义：弹出输入框让用户输入数量
    try {
      const { value: input } = await ElMessageBox.prompt('请输入要展示的用户数量', '自定义排名数量', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /^[1-9]\d*$/,
        inputErrorMessage: '请输入正整数',
      });
      userRankTop.value = Number(input);
    } catch (e) {
      return; // 用户取消，不改动
    }
  } else {
    userRankTop.value = num;
  }
  reloadFilteredPanels(getCurrentTrendRange());
}

async function loadModelUsage(range: DateRange) {
  try {
    const usage = await fetchModelTrend(range);
    modelUsageData.value = usage;
  } catch (e) {
    console.warn('加载模型用量分布失败:', e);
  }
}

async function loadActiveUserTrend(range: DateRange) {
  try {
    const response = await fetchUsageOverview(range);
    const activeUsersByDate = new Map(
      (response.daily ?? []).map((item) => [item.date.slice(0, 10), item.active_users ?? 0]),
    );
    const dates = generateDateSeriesFromRange(range.start_date, range.end_date);
    activeUserTrendData.value = dates.map((date) => ({
      date,
      count: activeUsersByDate.get(date) ?? 0,
    }));
    renderActiveUsersChart();
  } catch (e) {
    console.warn('加载活跃用户趋势失败:', e);
  }
}

async function reloadFilteredPanels(range: DateRange) {
  await Promise.all([loadActiveUserTrend(range), loadUserRank(range), loadModelUsage(range)]);
}

function handleTrendPresetChange(value: string | number | boolean) {
  const preset = String(value) as TrendPreset;

  trendPreset.value = preset;
  customDateRange.value = null;
  reloadFilteredPanels(getPresetRange(preset));
}

function handleCustomDateChange(value: [Date, Date] | null) {
  if (!value) return;

  const [start, end] = value;
  trendPreset.value = '';
  reloadFilteredPanels({
    start_date: formatDate(start),
    end_date: formatDate(end),
  });
}

// 初始化ECharts（确保DOM已渲染）
function initChart(type: 'admin' | 'activeUsers') {
  nextTick(() => {
    if (type === 'admin' && adminChartRef.value) {
      if (adminChart) {
        adminChart.dispose();
      }
      adminChart = echarts.init(adminChartRef.value);
      renderModelChart(adminChart, modelUsageData.value);
    }
    if (type === 'activeUsers' && activeUsersChartRef.value) {
      if (activeUsersChart) {
        activeUsersChart.dispose();
      }
      activeUsersChart = echarts.init(activeUsersChartRef.value);
      renderActiveUsersChart();
    }
  });
}

// 模型调用量指标切换：tokens / requests
type ModelChartMetric = 'tokens' | 'requests';
const modelChartMetric = ref<ModelChartMetric>('tokens');
const modelChartMetricOptions = [
  { label: 'Token数', value: 'tokens' },
  { label: '调用次数', value: 'requests' },
];

function handleModelChartMetricChange(value: string | number | boolean) {
  modelChartMetric.value = String(value) as ModelChartMetric;
  if (adminChart) renderModelChart(adminChart, modelUsageData.value);
}

// 模型调用量堆叠柱状图：按日期堆叠各模型调用量（趋势+模型分布）
function renderModelChart(chart: echarts.ECharts | null, data: ModelTrendResponse | null) {
  if (!chart) return;
  if (!data || !data.start_date || !data.end_date) {
    chart.clear();
    return;
  }
  const { start_date, end_date } = data;
  // 生成完整日期序列
  const dates = generateDateSeriesFromRange(start_date, end_date);
  const items = (data.items ?? []).filter((m) => m.model?.trim());
  const metric = modelChartMetric.value;
  const metricKey = metric === 'tokens' ? 'tokens' : 'requests';
  const metricLabel = metric === 'tokens' ? 'Token数' : '调用次数';
  // 按模型聚合数据
  const byDate = new Map<string, Map<string, number>>();
  const modelTotals = new Map<string, number>();
  // 初始化所有日期
  for (const d of dates) byDate.set(d, new Map());
  for (const item of items) {
    if (byDate.has(item.date)) {
      byDate.get(item.date)!.set(item.model, (byDate.get(item.date)!.get(item.model) || 0) + item[metricKey]);
    }
    modelTotals.set(item.model, (modelTotals.get(item.model) || 0) + item[metricKey]);
  }
  const models = Array.from(modelTotals.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([m]) => m);
  // 渐变配色：每色系最多5个模型，明度从浅到深；超限换色系，色相-8°平滑过渡
  function autoPalette(n: number): string[] {
    const PER_GROUP = 5;
    const PER_HUE = 8;
    const START_HUE = 215;
    const pal: string[] = [];
    for (let i = 0; i < n; i++) {
      const group = Math.floor(i / PER_GROUP);
      const idx = i % PER_GROUP;
      const hue = (START_HUE - group * PER_HUE + 360) % 360;
      const lightness = 72 - idx * 8;
      const saturation = 50 + idx * 4;
      pal.push(`hsl(${hue}, ${Math.round(saturation)}%, ${Math.round(lightness)}%)`);
    }
    return pal;
  }
  const colors = autoPalette(models.length);

  const barSeries = models.map((model, i) => ({
    name: model,
    type: 'bar',
    stack: 'total',
    data: dates.map((d) => byDate.get(d)?.get(model) || 0),
    barWidth: '60%',
    itemStyle: { color: colors[i % colors.length], borderRadius: 0 },
    emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.2)' } },
  }));

  const totalLine = {
    name: '总' + metricLabel,
    type: 'line',
    data: dates.map((d) => {
      let total = 0;
      for (const [, v] of byDate.get(d) || []) total += v;
      return total;
    }),
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { color: '#f59e0b', width: 2.5 },
    itemStyle: { color: '#f59e0b' },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(245, 158, 11, 0.15)' },
        { offset: 1, color: 'rgba(245, 158, 11, 0)' },
      ]),
    },
  };

  const sharedOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      textStyle: { color: '#333', fontSize: 12 },
      extraCssText: 'border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.08);',
    },
    legend: {
      bottom: 0,
      data: [...models, '总' + metricLabel],
      textStyle: { color: '#666', fontSize: 11 },
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 16,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: 60,
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11, color: '#999' },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: metricLabel,
      axisLabel: {
        fontSize: 11,
        color: '#999',
        formatter: (v: number) => {
          if (v >= 10000) return (v / 10000).toFixed(1) + 'w';
          if (v >= 1000) return (v / 1000).toFixed(1) + 'k';
          return v.toString();
        },
      },
      splitLine: { lineStyle: { color: '#f3f4f6' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
  };

  // 先渲染柱状图
  chart.setOption(
    {
      ...sharedOption,
      series: barSeries,
    },
    true,
  );

  // 延迟后叠加总量折线
  if (adminChartLineTimer) clearTimeout(adminChartLineTimer);
  adminChartLineTimer = setTimeout(() => {
    chart.setOption(
      {
        ...sharedOption,
        series: [...barSeries, totalLine],
      },
      true,
    );
  }, 600);
}

// 监听DOM变化，初始化/重绘图表
watch(
  [adminChartRef, modelUsageData],
  () => {
    if (adminChartRef.value && modelUsageData.value) {
      if (!adminChart) {
        initChart('admin');
      } else {
        renderModelChart(adminChart, modelUsageData.value);
      }
    }
  },
  { flush: 'post' },
);

watch(
  [activeUsersChartRef, activeUserTrendData],
  () => {
    if (activeUsersChartRef.value && activeUserTrendData.value.length && !activeUsersChart) {
      initChart('activeUsers');
    }
  },
  { flush: 'post' },
);

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const [todayRes, weekRes, totalRes] = await Promise.all([
      fetchUsageOverview(getDateRange(0)),
      fetchUsageOverview(getDateRange(7)),
      fetchUsageOverview(getDateRange(365 * 10)),
    ]);
    overviewStats.value = {
      today: calculateOverviewTotals(todayRes),
      week: calculateOverviewTotals(weekRes),
      total: calculateOverviewTotals(totalRes),
    };
    activeUsersCount.value = weekRes.users?.filter((u) => u.total_requests > 0).length || 0;
    totalUsersCount.value = weekRes.users?.length || 0;
    successRate.value = weekRes.success_rate ?? 0;

    try {
      await reloadFilteredPanels(getPresetRange('12h'));
    } catch (e) {
      console.warn('加载趋势数据失败:', e);
    }
  } catch (e) {
    console.error('加载调用分析数据失败:', e);
    error.value = e instanceof Error ? e.message : '加载数据失败';
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  window.addEventListener('resize', resizeCharts);
  loadData();
});

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts);
  adminChart?.dispose();
  activeUsersChart?.dispose();
});
</script>

<template>
  <div class="call-analysis">
    <ElSkeleton v-if="loading" :rows="8" animated class="call-analysis__state" />
    <ElAlert v-else-if="error" :title="error" type="error" show-icon :closable="false" class="call-analysis__state" />

    <template v-else>
      <!-- 概览指标卡 -->
      <div class="call-analysis__overview-grid call-analysis__overview-grid--admin">
        <OverviewStatCard
          v-for="card in overviewCards"
          :key="card.key"
          variant="metrics"
          :title="card.title"
          :icon="card.icon"
          :metrics="card.metrics"
        />
      </div>

      <section class="call-analysis__section">
        <div class="call-analysis__section-header">
          <h2 class="title-l2">调用趋势</h2>
          <div class="call-analysis__filters">
            <ElSegmented :model-value="trendPreset" :options="trendPresetOptions" @change="handleTrendPresetChange" />
            <ElDatePicker
              v-model="customDateRange"
              type="daterange"
              range-separator="-"
              start-placeholder="请选择开始日期"
              end-placeholder="请选择结束日期"
              unlink-panels
              class="call-analysis__date-picker"
              @change="handleCustomDateChange"
            />
          </div>
        </div>

        <div class="call-analysis__row">
          <!-- 模型调用量 -->
          <div class="call-analysis__card">
            <div class="call-analysis__card-header">
              <h3 class="title-l3">模型调用量</h3>
              <ElSegmented
                :model-value="modelChartMetric"
                :options="modelChartMetricOptions"
                @change="handleModelChartMetricChange"
              />
            </div>
            <div ref="adminChartRef" class="call-analysis__chart"></div>
          </div>

          <!-- 活跃用户数 -->
          <div class="call-analysis__card">
            <h3 class="title-l3">活跃用户数</h3>
            <div ref="activeUsersChartRef" class="call-analysis__chart"></div>
          </div>
        </div>

        <!-- 用户用量排名 -->
        <div class="call-analysis__card call-analysis__card--full">
          <div class="call-analysis__card-header">
            <h3 class="title-l3">用户用量排名</h3>
            <ElSelect :model-value="userRankTop" style="width: 110px" @change="handleUserRankTopChange">
              <ElOption :value="10" label="TOP10" />
              <ElOption :value="-1" label="ALL" />
              <ElOption
                v-if="userRankTop !== 10 && userRankTop !== -1"
                :value="userRankTop"
                :label="String(userRankTop)"
              />
              <ElOption :value="-2" label="自定义" />
            </ElSelect>
          </div>
          <ElTable :data="userRankRows" empty-text="暂无数据" class="app-table" max-height="420">
            <ElTableColumn prop="rank" label="排名" width="88" />
            <ElTableColumn label="用户">
              <template #default="{ row }">
                {{ row.username || '非AgentBox用户' }}
              </template>
            </ElTableColumn>
            <ElTableColumn prop="tokensText" label="Token数" />
            <ElTableColumn prop="requestsText" label="请求数" />
            <template #empty>
              <ElEmpty description="暂无数据" :image-size="72" />
            </template>
          </ElTable>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.call-analysis {
  display: flex;
  flex-direction: column;
}

.call-analysis__section {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: 40px;
}

.call-analysis__state {
  margin: 12px 0;
}

/* 概览指标卡 */
.call-analysis__overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 24px;
}

.call-analysis__overview-grid--admin {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

@media (max-width: 1400px) {
  .call-analysis__overview-grid--admin {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .call-analysis__overview-grid,
  .call-analysis__overview-grid--admin {
    grid-template-columns: 1fr;
  }
}

/* 卡片布局 */
.call-analysis__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}

.call-analysis__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.call-analysis__filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.call-analysis__filters :deep(.el-segmented__item) {
  min-width: 80px;
}

.call-analysis__date-picker {
  width: 360px !important;
}

.call-analysis__card {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  background: var(--bg-2);
  border-radius: var(--radius-2xl);
  border: none;
  padding: 20px 24px;
}

.call-analysis__card--full {
  width: 100%;
}

.call-analysis__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ECharts容器 */
.call-analysis__chart {
  width: 100%;
  height: 300px;
  min-height: 300px;
}

.call-analysis :deep(.el-table) {
  margin-top: 8px;
}

@media (max-width: 1100px) {
  .overview-row,
  .call-analysis__row {
    display: grid;
    grid-template-columns: 1fr;
  }

  .overview-divider {
    display: none;
  }

  .call-analysis__section-header,
  .call-analysis__card-header,
  .call-analysis__filters {
    align-items: stretch;
    flex-direction: column;
  }

  .call-analysis__date-picker {
    width: 100% !important;
  }
}
</style>
