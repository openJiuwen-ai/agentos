<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import * as echarts from 'echarts';
import { ElAlert, ElDatePicker, ElEmpty, ElSegmented, ElSkeleton, ElTable, ElTableColumn } from 'element-plus';
import { useAuth } from '@/composables/useAuth';
import { fetchUsageOverview, fetchUsageByUser, fetchUserUsage, fetchUsageTrend } from '@/api/inference';
import type { UsageOverviewResponse, UserUsageRankResponse, UserUsageDetailResponse, TrendResponse } from '@/api/inference';
import { calculateOverviewTotals, calculateUserTotals, formatCost, formatDate, formatTokens, getDateRange } from './utils/usage';
import apiCallTimesIcon from '@/assets/images/api_call_times.svg';
import tokenIcon from '@/assets/images/token.svg';
import personIcon from '@/assets/images/person.svg';
import apiCallIcon from '@/assets/images/api_call.svg';

const { isAdmin, userId } = useAuth();
const loading = ref(false);
const error = ref('');

// 趋势图时间范围选择
type TrendPreset = '12h' | '24h' | '7d' | '30d';

const trendPreset = ref<TrendPreset | ''>('12h');
const trendDays = ref(1);
const customDateRange = ref<[Date, Date] | null>(null);
const trendPresetOptions = [
  { label: '近12小时', value: '12h' },
  { label: '近24小时', value: '24h' },
  { label: '近7天', value: '7d' },
  { label: '近30天', value: '30d' },
];

// ECharts 实例
const adminChartRef = ref<HTMLElement | null>(null);
const userChartRef = ref<HTMLElement | null>(null);
const activeUsersChartRef = ref<HTMLElement | null>(null);
let adminChart: echarts.ECharts | null = null;
let userChart: echarts.ECharts | null = null;
let activeUsersChart: echarts.ECharts | null = null;

function resizeCharts() {
  adminChart?.resize();
  userChart?.resize();
  activeUsersChart?.resize();
}

// 管理员数据
const overviewData = ref<UsageOverviewResponse | null>(null);
const userRankData = ref<UserUsageRankResponse | null>(null);
const trendData = ref<TrendResponse | null>(null);
const activeUserTrendData = ref<Array<{ date: string; count: number }>>([]);

// 普通用户数据
const userDetailData = ref<UserUsageDetailResponse | null>(null);
const userTrendData = ref<TrendResponse | null>(null);

// 调用概览数据（今日/本周/累计）
const overviewStats = ref({
  today: { requests: 0, tokens: 0 },
  week: { requests: 0, tokens: 0 },
  total: { requests: 0, tokens: 0 },
});

// 活跃用户数 / 总用户数（管理员概览）
const activeUsersCount = ref(0);
const totalUsersCount = ref(0);

function formatRequests(requests: number): string {
  return requests.toLocaleString();
}
const userRankRows = computed(() =>
  (userRankData.value?.items ?? []).map((user, index) => ({
    ...user,
    rank: index + 1,
    tokensText: formatTokens(user.tokens),
    requestsText: user.requests.toLocaleString(),
  })),
);
const userDetailRows = computed(() =>
  (userDetailData.value?.daily_activity ?? []).map((day) => ({
    ...day,
    tokensText: formatTokens(day.tokens),
    requestsText: day.requests.toLocaleString(),
    costText: formatCost(day.cost),
  })),
);
const userDetailSummary = computed(() => {
  const rows = userDetailData.value?.daily_activity ?? [];
  return {
    tokensText: formatTokens(rows.reduce((sum, day) => sum + day.tokens, 0)),
    requestsText: rows.reduce((sum, day) => sum + day.requests, 0).toLocaleString(),
    costText: formatCost(rows.reduce((sum, day) => sum + day.cost, 0)),
  };
});

// 生成完整的日期序列（用于填充没有数据的日期）
function generateDateSeries(days: number): string[] {
  const dates: string[] = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    dates.push(formatDate(d));
  }
  return dates;
}

// 将API数据转换为ECharts格式
function prepareTrendChartData(data: TrendResponse | null, days: number) {
  let hourlyItems: TrendResponse['items'] | null = null;
  if (trendPreset.value === '12h') {
    hourlyItems = (data?.items ?? []).slice(-12);
  } else if (trendPreset.value === '24h') {
    hourlyItems = (data?.items ?? []).slice(-24);
  } else {}

  if (hourlyItems) {
    return {
      dates: hourlyItems.map((item) => item.time.slice(-5)),
      requests: hourlyItems.map((item) => item.requests),
      tokens: hourlyItems.map((item) => item.tokens),
    };
  }

  const dateSeries = generateDateSeries(days);
  const dataMap = new Map<string, { requests: number; tokens: number }>();

  if (data?.items) {
    for (const item of data.items) {
      dataMap.set(item.time, { requests: item.requests, tokens: item.tokens });
    }
  }

  return {
    dates: dateSeries.map(d => d.slice(5)), // 只显示月-日
    requests: dateSeries.map(d => dataMap.get(d)?.requests ?? 0),
    tokens: dateSeries.map(d => dataMap.get(d)?.tokens ?? 0),
  };
}

// 渲染趋势图
function renderTrendChart(chart: echarts.ECharts | null, data: TrendResponse | null, days: number) {
  if (!chart) return;

  const { dates, requests, tokens } = prepareTrendChartData(data, days);

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    legend: {
      bottom: 0,
      data: ['调用次数', 'Token数'],
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: 40,
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 11,
        color: '#999',
      },
      axisLine: {
        lineStyle: {
          color: '#e5e7eb',
        },
      },
      axisTick: {
        show: false,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '调用次数',
        axisLabel: {
          fontSize: 11,
          color: '#999',
          formatter: (value: number) => {
            if (value >= 10000) return (value / 10000).toFixed(1) + 'w';
            if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
            return value.toString();
          },
        },
        splitLine: { lineStyle: { color: '#f3f4f6' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'value',
        name: 'Token数',
        axisLabel: {
          fontSize: 11,
          color: '#999',
          formatter: (value: number) => formatTokens(value),
        },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
    ],
    series: [
      {
        name: '调用次数',
        type: 'bar',
        data: requests,
        itemStyle: {
          color: '#bfdbfe',
          borderRadius: [2, 2, 0, 0],
        },
        emphasis: {
          itemStyle: {
            color: '#93c5fd',
          },
        },
        barWidth: '60%',
      },
      {
        name: 'Token数',
        type: 'line',
        yAxisIndex: 1,
        data: tokens,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: '#2563eb',
          width: 2,
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(37, 99, 235, 0.2)' },
            { offset: 1, color: 'rgba(37, 99, 235, 0)' },
          ]),
        },
      },
    ],
  });
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

async function loadTrend(range: { start_date: string; end_date: string }, granularity: 'hour' | 'day') {
  const params = { ...range, granularity };
  try {
    if (isAdmin.value) {
      trendData.value = await fetchUsageTrend(params);
      renderTrendChart(adminChart, trendData.value, trendDays.value);
    } else {
      const uid = userId.value;
      if (uid) {
        userTrendData.value = await fetchUsageTrend({ ...params, user_id: uid });
        renderTrendChart(userChart, userTrendData.value, trendDays.value);
      }
    }
  } catch (e) {
    console.warn('加载趋势数据失败:', e);
  }
}

function handleTrendPresetChange(value: string | number | boolean) {
  const preset = String(value) as TrendPreset;
  const daysByPreset: Record<TrendPreset, number> = {
    '12h': 1,
    '24h': 1,
    '7d': 7,
    '30d': 30,
  };

  trendPreset.value = preset;
  trendDays.value = daysByPreset[preset];
  customDateRange.value = null;
  loadTrend(getDateRange(trendDays.value), preset.endsWith('h') ? 'hour' : 'day');
}

function handleCustomDateChange(value: [Date, Date] | null) {
  if (!value) return;

  const [start, end] = value;
  trendPreset.value = '';
  trendDays.value = Math.max(
    1,
    Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1,
  );
  loadTrend(
    { start_date: formatDate(start), end_date: formatDate(end) },
    'day',
  );
}

async function loadActiveUserTrend() {
  const dates = generateDateSeries(7);
  const dailyResponses = await Promise.all(
    dates.map((date) => fetchUsageOverview({ start_date: date, end_date: date })),
  );
  activeUserTrendData.value = dailyResponses.map((response, index) => ({
    date: dates[index],
    count: response.users?.filter((user) => user.total_requests > 0).length ?? 0,
  }));
}

// 初始化ECharts（确保DOM已渲染）
function initChart(type: 'admin' | 'user' | 'activeUsers') {
  nextTick(() => {
    if (type === 'admin' && adminChartRef.value) {
      if (adminChart) {
        adminChart.dispose();
      }
      adminChart = echarts.init(adminChartRef.value);
      renderTrendChart(adminChart, trendData.value, trendDays.value);
    }
    if (type === 'user' && userChartRef.value) {
      if (userChart) {
        userChart.dispose();
      }
      userChart = echarts.init(userChartRef.value);
      renderTrendChart(userChart, userTrendData.value, trendDays.value);
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

// 监听DOM变化，初始化图表
watch([adminChartRef, trendData], () => {
  if (adminChartRef.value && trendData.value && !adminChart) {
    initChart('admin');
  }
}, { flush: 'post' });

watch([userChartRef, userTrendData], () => {
  if (userChartRef.value && userTrendData.value && !userChart) {
    initChart('user');
  }
}, { flush: 'post' });

watch([activeUsersChartRef, activeUserTrendData], () => {
  if (activeUsersChartRef.value && activeUserTrendData.value.length && !activeUsersChart) {
    initChart('activeUsers');
  }
}, { flush: 'post' });

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const range30 = getDateRange(30);

    if (isAdmin.value) {
      // 管理员：加载所有数据
      const [overview, userRank] = await Promise.all([
        fetchUsageOverview(range30),
        fetchUsageByUser({ ...range30, top: 10 }),
      ]);
      overviewData.value = overview;
      userRankData.value = userRank;

      // 计算概览统计 + 活跃用户数
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

      // 趋势图单独加载
      try {
        const [trend] = await Promise.all([
          fetchUsageTrend({ ...getDateRange(1), granularity: 'hour' }),
          loadActiveUserTrend(),
        ]);
        trendData.value = trend;
      } catch (e) {
        console.warn('加载趋势数据失败:', e);
      }
    } else {
      // 普通用户
      const uid = userId.value;
      if (!uid) {
        error.value = '无法获取用户信息';
        return;
      }

      const [detail, todayRes, weekRes, totalRes] = await Promise.all([
        fetchUserUsage({ user_id: uid, ...range30 }),
        fetchUserUsage({ user_id: uid, ...getDateRange(0) }),
        fetchUserUsage({ user_id: uid, ...getDateRange(7) }),
        fetchUserUsage({ user_id: uid, ...getDateRange(365 * 10) }),
      ]);
      userDetailData.value = detail;

      overviewStats.value = {
        today: calculateUserTotals(todayRes),
        week: calculateUserTotals(weekRes),
        total: calculateUserTotals(totalRes),
      };

      // 趋势图单独加载
      try {
        userTrendData.value = await fetchUsageTrend({
          ...getDateRange(1),
          granularity: 'hour',
          user_id: uid,
        });
      } catch (e) {
        console.warn('加载趋势数据失败:', e);
      }
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
  userChart?.dispose();
  activeUsersChart?.dispose();
});
</script>

<template>
  <div class="call-analysis">
    <ElSkeleton v-if="loading" :rows="8" animated class="call-analysis__state" />
    <ElAlert v-else-if="error" :title="error" type="error" show-icon :closable="false" class="call-analysis__state" />

    <template v-else>
      <!-- 概览指标条（对齐 DSL） -->
      <div class="call-analysis__overview-card">
        <div class="overview-row">
          <section class="overview-block">
            <header class="overview-block__header">
              <span class="overview-block__icon">
                <img :src="apiCallTimesIcon" alt="" width="22" height="22" />
              </span>
              <span class="overview-block__title">调用次数</span>
            </header>
            <div class="overview-block__metrics">
              <div class="overview-metric overview-metric--hero">
                <span class="overview-metric__value overview-metric__value--hero">{{ formatRequests(overviewStats.today.requests) }}</span>
                <span class="overview-metric__label">今日</span>
              </div>
              <div class="overview-metric">
                <span class="overview-metric__value">{{ formatRequests(overviewStats.week.requests) }}</span>
                <span class="overview-metric__label">本周</span>
              </div>
              <div class="overview-metric">
                <span class="overview-metric__value">{{ formatRequests(overviewStats.total.requests) }}</span>
                <span class="overview-metric__label">累计</span>
              </div>
            </div>
          </section>

          <div class="overview-divider" />

          <section class="overview-block">
            <header class="overview-block__header">
              <span class="overview-block__icon">
                <img :src="tokenIcon" alt="" width="22" height="22" />
              </span>
              <span class="overview-block__title">Token数</span>
            </header>
            <div class="overview-block__metrics">
              <div class="overview-metric overview-metric--hero">
                <span class="overview-metric__value overview-metric__value--hero">{{ formatTokens(overviewStats.today.tokens) }}</span>
                <span class="overview-metric__label">今日</span>
              </div>
              <div class="overview-metric">
                <span class="overview-metric__value">{{ formatTokens(overviewStats.week.tokens) }}</span>
                <span class="overview-metric__label">本周</span>
              </div>
              <div class="overview-metric">
                <span class="overview-metric__value">{{ formatTokens(overviewStats.total.tokens) }}</span>
                <span class="overview-metric__label">累计</span>
              </div>
            </div>
          </section>

          <template v-if="isAdmin">
            <div class="overview-divider" />

            <section class="overview-block">
              <header class="overview-block__header">
                <span class="overview-block__icon">
                  <img :src="personIcon" alt="" width="22" height="22" />
                </span>
                <span class="overview-block__title">用户数</span>
              </header>
              <div class="overview-block__metrics">
                <div class="overview-metric overview-metric--hero">
                  <span class="overview-metric__value overview-metric__value--hero">{{ activeUsersCount }}</span>
                  <span class="overview-metric__label">近一周活跃用户数</span>
                </div>
                <div class="overview-metric">
                  <span class="overview-metric__value">{{ totalUsersCount }}</span>
                  <span class="overview-metric__label">总用户数</span>
                </div>
              </div>
            </section>

            <div class="overview-divider" />

            <section class="overview-block">
              <header class="overview-block__header">
                <span class="overview-block__icon">
                  <img :src="apiCallIcon" alt="" width="22" height="22" />
                </span>
                <span class="overview-block__title">调用状况</span>
              </header>
              <div class="overview-block__metrics">
                <div class="overview-metric overview-metric--hero">
                  <span class="overview-metric__value overview-metric__value--hero">--</span>
                  <span class="overview-metric__label">实时并发数 QPS</span>
                </div>
                <div class="overview-metric">
                  <span class="overview-metric__value">--</span>
                  <span class="overview-metric__label">近一周请求成功率</span>
                </div>
              </div>
            </section>
          </template>
        </div>
      </div>

      <!-- 管理员视图 -->
      <template v-if="isAdmin">
        <div class="call-analysis__section-header">
          <h2 class="call-analysis__section-title">调用趋势</h2>
          <div class="call-analysis__filters">
            <ElSegmented
              :model-value="trendPreset"
              :options="trendPresetOptions"
              @change="handleTrendPresetChange"
            />
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
            <h3 class="call-analysis__card-title">模型调用量</h3>
            <div ref="adminChartRef" class="call-analysis__chart"></div>
          </div>

          <!-- 活跃用户数 -->
          <div class="call-analysis__card">
            <h3 class="call-analysis__card-title">活跃用户数</h3>
            <div ref="activeUsersChartRef" class="call-analysis__chart"></div>
          </div>
        </div>

        <div class="call-analysis__row">
          <!-- 用户用量排名 -->
          <div class="call-analysis__card call-analysis__card--half">
            <h3 class="call-analysis__card-title">用户用量排名Top10</h3>
            <ElTable :data="userRankRows" empty-text="暂无数据" stripe>
              <ElTableColumn prop="rank" label="排名" width="88" />
              <ElTableColumn prop="user_id" label="用户" />
              <ElTableColumn prop="tokensText" label="Token数" />
              <ElTableColumn prop="requestsText" label="请求数" />
              <template #empty>
                <ElEmpty description="暂无数据" :image-size="72" />
              </template>
            </ElTable>
          </div>
          <div class="call-analysis__placeholder" aria-hidden="true" />
        </div>
      </template>

      <!-- 普通用户视图 -->
      <template v-else>
        <!-- 调用趋势 -->
        <div class="call-analysis__card call-analysis__card--full">
          <div class="call-analysis__card-header">
            <h2 class="call-analysis__card-title">我的调用趋势</h2>
            <div class="call-analysis__filters">
              <ElSegmented
                :model-value="trendPreset"
                :options="trendPresetOptions"
                @change="handleTrendPresetChange"
              />
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
          <div ref="userChartRef" class="call-analysis__chart"></div>
        </div>

        <!-- 调用明细 -->
        <div class="call-analysis__card">
          <h2 class="call-analysis__card-title">我的调用明细</h2>
          <ElTable :data="userDetailRows" empty-text="暂无数据" stripe>
            <ElTableColumn prop="date" label="日期" />
            <ElTableColumn prop="tokensText" label="Token数" />
            <ElTableColumn prop="requestsText" label="请求数" />
            <ElTableColumn prop="costText" label="成本" />
            <template #empty>
              <ElEmpty description="暂无数据" :image-size="72" />
            </template>
          </ElTable>

          <div v-if="userDetailData?.daily_activity?.length" class="call-analysis__summary">
            <div class="call-analysis__summary-item">
              <span class="call-analysis__summary-label">总Token数</span>
              <span class="call-analysis__summary-value">{{ userDetailSummary.tokensText }}</span>
            </div>
            <div class="call-analysis__summary-item">
              <span class="call-analysis__summary-label">总请求数</span>
              <span class="call-analysis__summary-value">{{ userDetailSummary.requestsText }}</span>
            </div>
            <div class="call-analysis__summary-item">
              <span class="call-analysis__summary-label">总成本</span>
              <span class="call-analysis__summary-value">{{ userDetailSummary.costText }}</span>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.call-analysis {
  padding: 12px 32px 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.call-analysis__state {
  margin: 12px 0;
}

/* 概览指标条 */
.call-analysis__overview-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dfdfdf;
  padding: 20px 24px;
}

.overview-row {
  display: flex;
  align-items: stretch;
  gap: 40px;
}

.overview-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overview-block__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.overview-block__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e6f5fd;
  flex-shrink: 0;
}

.overview-block__title {
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: #191919;
}

.overview-block__metrics {
  display: flex;
  align-items: flex-end;
  gap: 24px;
  padding-left: 36px;
}

.overview-metric {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

.overview-metric--hero {
  gap: 8px;
}

.overview-metric__value {
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: #191919;
  white-space: nowrap;
}

.overview-metric__value--hero {
  font-size: 32px;
  line-height: 40px;
}

.overview-metric__label {
  font-size: 14px;
  line-height: 22px;
  color: #777;
  white-space: nowrap;
}

.overview-divider {
  width: 1px;
  align-self: stretch;
  background: #dfdfdf;
  flex-shrink: 0;
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

.call-analysis__section-title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: #191919;
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
  min-width: 0;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dfdfdf;
  padding: 20px 24px;
}

.call-analysis__card--half {
  width: 100%;
}

.call-analysis__placeholder {
  min-width: 0;
}

.call-analysis__card--full {
  width: 100%;
}

.call-analysis__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.call-analysis__card-title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  color: #191919;
  line-height: 28px;
}

/* ECharts容器 */
.call-analysis__chart {
  width: 100%;
  height: 300px;
  min-height: 300px;
}

/* 汇总统计 */
.call-analysis__summary {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
}

.call-analysis__summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.call-analysis__summary-label {
  font-size: 12px;
  color: #999;
}

.call-analysis__summary-value {
  font-size: 18px;
  font-weight: 600;
  color: #191919;
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

  .overview-divider,
  .call-analysis__placeholder {
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
