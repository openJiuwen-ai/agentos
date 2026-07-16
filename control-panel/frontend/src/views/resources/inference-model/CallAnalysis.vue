<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue';
import * as echarts from 'echarts';
import { useAuth } from '@/composables/useAuth';
import { fetchUsageOverview, fetchUsageByModel, fetchUsageByUser, fetchUserUsage, fetchUsageTrend } from '@/api/inference';
import type { UsageOverviewResponse, ModelUsageResponse, UserUsageRankResponse, UserUsageDetailResponse, TrendResponse } from '@/api/inference';

const { isAdmin, userId } = useAuth();
const loading = ref(false);
const error = ref('');

// 趋势图时间范围选择
const trendDays = ref(30);
const trendDayOptions = [7, 15, 30];

// ECharts 实例
const adminChartRef = ref<HTMLElement | null>(null);
const userChartRef = ref<HTMLElement | null>(null);
const modelUsageChartRef = ref<HTMLElement | null>(null);
let adminChart: echarts.ECharts | null = null;
let userChart: echarts.ECharts | null = null;
let modelUsageChart: echarts.ECharts | null = null;

// 管理员数据
const overviewData = ref<UsageOverviewResponse | null>(null);
const modelUsageData = ref<ModelUsageResponse | null>(null);
const userRankData = ref<UserUsageRankResponse | null>(null);
const trendData = ref<TrendResponse | null>(null);

// 普通用户数据
const userDetailData = ref<UserUsageDetailResponse | null>(null);
const userTrendData = ref<TrendResponse | null>(null);

// 调用概览数据（今日/本周/累计）
const overviewStats = ref({
  today: { requests: 0, tokens: 0 },
  week: { requests: 0, tokens: 0 },
  total: { requests: 0, tokens: 0 },
});

// 活跃用户数（当前周期 vs 上一周期）
const activeUsersCount = ref(0);
const activeUsersPrevCount = ref(0);
const activeUsersTrend = computed(() => {
  if (activeUsersPrevCount.value === 0) return { value: 0, isUp: true };
  const change = activeUsersCount.value - activeUsersPrevCount.value;
  const pct = Math.round((change / activeUsersPrevCount.value) * 100);
  return { value: Math.abs(pct), isUp: change >= 0 };
});

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getDateRange(days: number): { start_date: string; end_date: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - days);
  return { start_date: formatDate(start), end_date: formatDate(end) };
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

function formatCost(cost: number): string {
  return '$' + cost.toFixed(4);
}

// 环形图颜色
const chartColors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'];

// 计算概览统计数据
function calculateOverviewTotals(data: UsageOverviewResponse) {
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
  const dateSeries = generateDateSeries(days);
  const dataMap = new Map<string, number>();

  if (data?.items) {
    for (const item of data.items) {
      dataMap.set(item.time, item.requests);
    }
  }

  return {
    dates: dateSeries.map(d => d.slice(5)), // 只显示月-日
    values: dateSeries.map(d => dataMap.get(d) || 0),
  };
}

// 渲染趋势图
function renderTrendChart(chart: echarts.ECharts | null, data: TrendResponse | null, days: number) {
  if (!chart) return;

  const { dates, values } = prepareTrendChartData(data, days);

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
      formatter: (params: any) => {
        const param = Array.isArray(params) ? params[0] : params;
        return `${param.name}<br/>调用次数: ${param.value.toLocaleString()} 次`;
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
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
    yAxis: {
      type: 'value',
      axisLabel: {
        fontSize: 11,
        color: '#999',
        formatter: (value: number) => {
          if (value >= 10000) return (value / 10000).toFixed(1) + 'w';
          if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
          return value.toString();
        },
      },
      splitLine: {
        lineStyle: {
          color: '#f3f4f6',
        },
      },
      axisLine: {
        show: false,
      },
      axisTick: {
        show: false,
      },
    },
    series: [
      {
        name: '调用次数',
        type: 'bar',
        data: values,
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
        name: '趋势',
        type: 'line',
        data: values,
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

// 渲染模型用量分布图
function renderModelUsageChart(data: ModelUsageResponse | null) {
  if (!modelUsageChart) return;

  // 没有数据时显示暂无数据
  if (!data?.items?.length) {
    modelUsageChart.setOption({
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fontSize: 14,
          fill: '#999',
        },
      },
      series: [],
    });
    return;
  }

  const chartData = data.items.slice(0, 10).map((item, index) => ({
    name: item.model,
    value: item.tokens,
    itemStyle: {
      color: chartColors[index % chartColors.length],
    },
  }));

  modelUsageChart.setOption({
    graphic: { type: 'none' }, // 清除暂无数据文字
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const item = data.items.find(i => i.model === params.name);
        return `${params.name}<br/>Token数: ${formatTokens(params.value)}<br/>占比: ${item?.pct.toFixed(1) || 0}%`;
      },
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center',
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 12,
      textStyle: {
        fontSize: 13,
        color: '#191919',
      },
      formatter: (name: string) => {
        const item = data.items.find(i => i.model === name);
        if (item) {
          return `${name}  ${formatTokens(item.tokens)} (${item.pct.toFixed(1)}%)`;
        }
        return name;
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['30%', '50%'],
        avoidLabelOverlap: false,
        label: {
          show: false,
        },
        emphasis: {
          label: {
            show: false,
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.2)',
          },
        },
        labelLine: {
          show: false,
        },
        data: chartData,
      },
    ],
  });
}

// 切换趋势图时间范围
async function changeTrendDays(days: number) {
  trendDays.value = days;
  const range = getDateRange(days);
  try {
    if (isAdmin.value) {
      trendData.value = await fetchUsageTrend(range);
      renderTrendChart(adminChart, trendData.value, days);
    } else {
      const uid = userId.value;
      if (uid) {
        userTrendData.value = await fetchUsageTrend({ ...range, user_id: uid });
        renderTrendChart(userChart, userTrendData.value, days);
      }
    }
  } catch (e) {
    console.warn('加载趋势数据失败:', e);
  }
}

// 初始化ECharts（确保DOM已渲染）
function initChart(type: 'admin' | 'user' | 'modelUsage') {
  nextTick(() => {
    if (type === 'admin' && adminChartRef.value) {
      if (adminChart) {
        adminChart.dispose();
      }
      adminChart = echarts.init(adminChartRef.value);
      window.addEventListener('resize', () => adminChart?.resize());
      renderTrendChart(adminChart, trendData.value, trendDays.value);
    }
    if (type === 'user' && userChartRef.value) {
      if (userChart) {
        userChart.dispose();
      }
      userChart = echarts.init(userChartRef.value);
      window.addEventListener('resize', () => userChart?.resize());
      renderTrendChart(userChart, userTrendData.value, trendDays.value);
    }
    if (type === 'modelUsage' && modelUsageChartRef.value) {
      if (modelUsageChart) {
        modelUsageChart.dispose();
      }
      modelUsageChart = echarts.init(modelUsageChartRef.value);
      window.addEventListener('resize', () => modelUsageChart?.resize());
      renderModelUsageChart(modelUsageData.value);
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

watch([modelUsageChartRef, modelUsageData], () => {
  if (modelUsageChartRef.value && modelUsageData.value && !modelUsageChart) {
    initChart('modelUsage');
  }
}, { flush: 'post' });

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const range30 = getDateRange(30);

    if (isAdmin.value) {
      // 管理员：加载所有数据
      const [overview, modelUsage, userRank] = await Promise.all([
        fetchUsageOverview(range30),
        fetchUsageByModel(range30),
        fetchUsageByUser({ ...range30, top: 10 }),
      ]);
      overviewData.value = overview;
      modelUsageData.value = modelUsage;
      userRankData.value = userRank;

      // 计算概览统计 + 活跃用户数
      const [todayRes, weekRes, totalRes, prevWeekRes] = await Promise.all([
        fetchUsageOverview(getDateRange(0)),
        fetchUsageOverview(getDateRange(7)),
        fetchUsageOverview(getDateRange(365 * 10)),
        fetchUsageOverview({ start_date: formatDate(new Date(Date.now() - 14 * 86400000)), end_date: formatDate(new Date(Date.now() - 7 * 86400000)) }),
      ]);
      overviewStats.value = {
        today: calculateOverviewTotals(todayRes),
        week: calculateOverviewTotals(weekRes),
        total: calculateOverviewTotals(totalRes),
      };
      activeUsersCount.value = weekRes.users?.filter(u => u.total_requests > 0).length || 0;
      activeUsersPrevCount.value = prevWeekRes.users?.filter(u => u.total_requests > 0).length || 0;

      // 趋势图单独加载
      try {
        trendData.value = await fetchUsageTrend(range30);
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
        userTrendData.value = await fetchUsageTrend({ ...range30, user_id: uid });
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
  loadData();
});
</script>

<template>
  <div class="call-analysis">
    <div v-if="loading" class="call-analysis__loading">加载中...</div>
    <div v-else-if="error" class="call-analysis__error">{{ error }}</div>

    <template v-else>
      <!-- 调用概览卡片 -->
      <div class="call-analysis__overview-card">
        <div class="call-analysis__overview-header">
          <span class="call-analysis__overview-title">调用概览</span>
        </div>
        <div class="call-analysis__overview-content">
          <div class="call-analysis__overview-section">
            <div class="call-analysis__overview-section-title">调用次数</div>
            <div class="call-analysis__overview-metrics">
              <div class="call-analysis__overview-metric">
                <span class="call-analysis__overview-metric-label">今日</span>
                <span class="call-analysis__overview-metric-value">{{ overviewStats.today.requests.toLocaleString() }}<span class="call-analysis__overview-metric-unit">次</span></span>
              </div>
              <div class="call-analysis__overview-metric">
                <span class="call-analysis__overview-metric-label">本周</span>
                <span class="call-analysis__overview-metric-value">{{ overviewStats.week.requests.toLocaleString() }}<span class="call-analysis__overview-metric-unit">次</span></span>
              </div>
              <div class="call-analysis__overview-metric">
                <span class="call-analysis__overview-metric-label">累计</span>
                <span class="call-analysis__overview-metric-value">{{ overviewStats.total.requests.toLocaleString() }}<span class="call-analysis__overview-metric-unit">次</span></span>
              </div>
            </div>
          </div>
          <div class="call-analysis__overview-divider"></div>
          <div class="call-analysis__overview-section">
            <div class="call-analysis__overview-section-title">Token数</div>
            <div class="call-analysis__overview-metrics">
              <div class="call-analysis__overview-metric">
                <span class="call-analysis__overview-metric-label">今日</span>
                <span class="call-analysis__overview-metric-value">{{ formatTokens(overviewStats.today.tokens) }}</span>
              </div>
              <div class="call-analysis__overview-metric">
                <span class="call-analysis__overview-metric-label">本周</span>
                <span class="call-analysis__overview-metric-value">{{ formatTokens(overviewStats.week.tokens) }}</span>
              </div>
              <div class="call-analysis__overview-metric">
                <span class="call-analysis__overview-metric-label">累计</span>
                <span class="call-analysis__overview-metric-value">{{ formatTokens(overviewStats.total.tokens) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 管理员视图 -->
      <template v-if="isAdmin">
        <!-- 顶部统计卡片 -->
        <div class="call-analysis__stats">
          <div class="call-analysis__stat-card">
            <span class="call-analysis__stat-label">活跃用户数（本周）</span>
            <div class="call-analysis__stat-row">
              <span class="call-analysis__stat-value">{{ activeUsersCount }}</span>
              <span v-if="activeUsersPrevCount > 0" class="call-analysis__stat-trend" :class="{ 'call-analysis__stat-trend--up': activeUsersTrend.isUp, 'call-analysis__stat-trend--down': !activeUsersTrend.isUp }">
                <span>{{ activeUsersTrend.isUp ? '↑' : '↓' }}</span>
                <span>{{ activeUsersTrend.value }}%</span>
              </span>
            </div>
            <span class="call-analysis__stat-hint">较上周 {{ activeUsersPrevCount }} 人</span>
          </div>
        </div>

        <!-- 调用趋势 -->
        <div class="call-analysis__card call-analysis__card--full">
          <div class="call-analysis__card-header">
            <h2 class="call-analysis__card-title">调用趋势</h2>
            <div class="call-analysis__trend-tabs">
              <button
                v-for="days in trendDayOptions"
                :key="days"
                class="call-analysis__trend-tab"
                :class="{ 'call-analysis__trend-tab--active': trendDays === days }"
                @click="changeTrendDays(days)"
              >
                {{ days }}天
              </button>
            </div>
          </div>
          <div ref="adminChartRef" class="call-analysis__chart"></div>
        </div>

        <div class="call-analysis__row">
          <!-- 模型用量分布卡片 -->
          <div class="call-analysis__card">
            <h2 class="call-analysis__card-title">模型用量分布</h2>
            <div ref="modelUsageChartRef" class="call-analysis__pie-chart"></div>
          </div>

          <!-- 用户用量排名卡片 -->
          <div class="call-analysis__card">
            <h2 class="call-analysis__card-title">用户用量排名Top10</h2>
            <div class="call-analysis__table">
              <div class="call-analysis__table-header">
                <span class="call-analysis__th call-analysis__th--rank">排名</span>
                <span class="call-analysis__th">用户</span>
                <span class="call-analysis__th">Token数</span>
                <span class="call-analysis__th">请求数</span>
              </div>
              <div v-for="(user, index) in (userRankData?.items || [])" :key="user.user_id" class="call-analysis__table-row">
                <span class="call-analysis__td call-analysis__td--rank">{{ index + 1 }}</span>
                <span class="call-analysis__td">{{ user.user_id }}</span>
                <span class="call-analysis__td">{{ formatTokens(user.tokens) }}</span>
                <span class="call-analysis__td">{{ user.requests.toLocaleString() }}</span>
              </div>
              <div v-if="!userRankData?.items?.length" class="call-analysis__empty">暂无数据</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 普通用户视图 -->
      <template v-else>
        <!-- 调用趋势 -->
        <div class="call-analysis__card call-analysis__card--full">
          <div class="call-analysis__card-header">
            <h2 class="call-analysis__card-title">我的调用趋势</h2>
            <div class="call-analysis__trend-tabs">
              <button
                v-for="days in trendDayOptions"
                :key="days"
                class="call-analysis__trend-tab"
                :class="{ 'call-analysis__trend-tab--active': trendDays === days }"
                @click="changeTrendDays(days)"
              >
                {{ days }}天
              </button>
            </div>
          </div>
          <div ref="userChartRef" class="call-analysis__chart"></div>
        </div>

        <!-- 调用明细 -->
        <div class="call-analysis__card">
          <h2 class="call-analysis__card-title">我的调用明细</h2>
          <div class="call-analysis__table">
            <div class="call-analysis__table-header">
              <span class="call-analysis__th">日期</span>
              <span class="call-analysis__th">Token数</span>
              <span class="call-analysis__th">请求数</span>
              <span class="call-analysis__th">成本</span>
            </div>
            <div v-for="day in (userDetailData?.daily_activity || [])" :key="day.date" class="call-analysis__table-row">
              <span class="call-analysis__td">{{ day.date }}</span>
              <span class="call-analysis__td">{{ formatTokens(day.tokens) }}</span>
              <span class="call-analysis__td">{{ day.requests.toLocaleString() }}</span>
              <span class="call-analysis__td">{{ formatCost(day.cost) }}</span>
            </div>
            <div v-if="!userDetailData?.daily_activity?.length" class="call-analysis__empty">暂无数据</div>
          </div>

          <div v-if="userDetailData?.daily_activity?.length" class="call-analysis__summary">
            <div class="call-analysis__summary-item">
              <span class="call-analysis__summary-label">总Token数</span>
              <span class="call-analysis__summary-value">{{ formatTokens(userDetailData.daily_activity.reduce((sum, d) => sum + d.tokens, 0)) }}</span>
            </div>
            <div class="call-analysis__summary-item">
              <span class="call-analysis__summary-label">总请求数</span>
              <span class="call-analysis__summary-value">{{ userDetailData.daily_activity.reduce((sum, d) => sum + d.requests, 0).toLocaleString() }}</span>
            </div>
            <div class="call-analysis__summary-item">
              <span class="call-analysis__summary-label">总成本</span>
              <span class="call-analysis__summary-value">{{ formatCost(userDetailData.daily_activity.reduce((sum, d) => sum + d.cost, 0)) }}</span>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.call-analysis {
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.call-analysis__loading,
.call-analysis__error,
.call-analysis__empty {
  padding: 40px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}

.call-analysis__error {
  color: #dc2626;
}

/* 调用概览卡片 */
.call-analysis__overview-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  padding: 20px;
}

.call-analysis__overview-header {
  margin-bottom: 20px;
}

.call-analysis__overview-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.call-analysis__overview-content {
  display: flex;
  gap: 0;
}

.call-analysis__overview-section {
  flex: 1;
  padding: 0 20px;
}

.call-analysis__overview-section:first-child {
  padding-left: 0;
}

.call-analysis__overview-section:last-child {
  padding-right: 0;
}

.call-analysis__overview-divider {
  width: 1px;
  background: #e5e7eb;
  margin: 0 20px;
}

.call-analysis__overview-section-title {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 12px;
}

.call-analysis__overview-metrics {
  display: flex;
  gap: 24px;
}

.call-analysis__overview-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.call-analysis__overview-metric-label {
  font-size: 12px;
  color: #9ca3af;
}

.call-analysis__overview-metric-value {
  font-size: 24px;
  font-weight: 600;
  color: #111827;
}

.call-analysis__overview-metric-unit {
  font-size: 12px;
  font-weight: 400;
  color: #6b7280;
  margin-left: 2px;
}

/* 统计卡片 */
.call-analysis__stats {
  display: flex;
  gap: 24px;
}

.call-analysis__stat-card {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dfdfdf;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.call-analysis__stat-label {
  font-size: 14px;
  color: #666;
}

.call-analysis__stat-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.call-analysis__stat-value {
  font-size: 32px;
  font-weight: 600;
  color: #191919;
}

.call-analysis__stat-trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 500;
}

.call-analysis__stat-trend--up {
  color: #22c55e;
}

.call-analysis__stat-trend--down {
  color: #ef4444;
}

.call-analysis__stat-hint {
  font-size: 12px;
  color: #999;
}

/* 卡片布局 */
.call-analysis__row {
  display: flex;
  gap: 24px;
}

.call-analysis__card {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dfdfdf;
  padding: 20px 24px;
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
  font-size: 18px;
  font-weight: 500;
  color: #191919;
  line-height: 26px;
}

/* 趋势图时间范围选择 */
.call-analysis__trend-tabs {
  display: flex;
  gap: 4px;
  background: #f3f4f6;
  border-radius: 6px;
  padding: 2px;
}

.call-analysis__trend-tab {
  padding: 4px 12px;
  font-size: 13px;
  border: none;
  background: transparent;
  color: #666;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.call-analysis__trend-tab:hover {
  color: #191919;
}

.call-analysis__trend-tab--active {
  background: #fff;
  color: #191919;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* ECharts容器 */
.call-analysis__chart {
  width: 100%;
  height: 300px;
  min-height: 300px;
}

.call-analysis__pie-chart {
  width: 100%;
  height: 300px;
  min-height: 300px;
}

/* 表格 */
.call-analysis__table {
  width: 100%;
}

.call-analysis__table-header {
  display: flex;
  padding: 9px 16px;
  background: rgba(25, 25, 25, 0.05);
  border-bottom: 1px solid #dfdfdf;
}

.call-analysis__th {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: #191919;
  line-height: 22px;
}

.call-analysis__th--rank {
  flex: 0 0 88px;
}

.call-analysis__table-row {
  display: flex;
  padding: 9px 16px;
  border-bottom: 1px solid #f3f3f3;
}

.call-analysis__table-row:last-child {
  border-bottom: none;
}

.call-analysis__table-row:hover {
  background: #f9fafb;
}

.call-analysis__td {
  flex: 1;
  font-size: 14px;
  color: #191919;
  line-height: 22px;
}

.call-analysis__td--rank {
  flex: 0 0 88px;
  font-weight: 500;
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
</style>
