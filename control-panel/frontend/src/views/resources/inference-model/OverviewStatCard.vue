<script setup lang="ts">
import { ElCard } from 'element-plus';

export interface OverviewMetricItem {
  value: string | number;
  label: string;
  hero?: boolean;
}

withDefaults(
  defineProps<{
    /** hero: 管理工作台今日调用分析；metrics: 调用分析页；trend: 个人工作台今日调用分析（含图表槽） */
    variant?: 'hero' | 'metrics' | 'trend';
    title: string;
    icon: string;
    /** hero 模式主数值 */
    value?: string | number;
    /** hero 模式副文案 */
    desc?: string;
    /** metrics / trend 模式指标列表 */
    metrics?: OverviewMetricItem[];
  }>(),
  {
    variant: 'hero',
    value: '',
    desc: '',
    metrics: () => [],
  },
);
</script>

<template>
  <ElCard class="overview-stat-card" :class="`overview-stat-card--${variant}`" shadow="never" :body-style="{ padding: 0 }">
    <template v-if="variant === 'hero'">
      <div class="overview-stat-card__hero">
        <span class="overview-stat-card__hero-icon-wrap">
          <img :src="icon" alt="" class="overview-stat-card__hero-icon" />
        </span>
        <div class="overview-stat-card__hero-content">
          <span class="title-l2 overview-stat-card__hero-title">{{ title }}</span>
          <div class="overview-stat-card__hero-data">
            <span class="overview-stat-card__hero-value">{{ value }}</span>
            <span v-if="desc" class="overview-stat-card__hero-desc">{{ desc }}</span>
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="variant === 'trend'">
      <div class="overview-stat-card__trend">
        <header class="overview-stat-card__trend-header">
          <img :src="icon" alt="" class="overview-stat-card__trend-icon" width="20" height="20" />
          <span class="title-l2 overview-stat-card__trend-title">{{ title }}</span>
        </header>
        <div class="overview-stat-card__trend-metrics">
          <div v-for="(item, index) in metrics" :key="index" class="overview-stat-card__trend-metric">
            <span class="overview-stat-card__trend-label">{{ item.label }}</span>
            <span class="overview-stat-card__trend-value">{{ item.value }}</span>
          </div>
        </div>
        <div class="overview-stat-card__trend-chart">
          <slot />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="overview-stat-card__metrics">
        <header class="overview-stat-card__metrics-header">
          <img :src="icon" alt="" class="overview-stat-card__metrics-icon" width="20" height="20" />
          <span class="title-l2 overview-stat-card__metrics-title">{{ title }}</span>
        </header>
        <div class="overview-stat-card__metrics-row">
          <div v-for="(item, index) in metrics" :key="index" class="overview-stat-card__metric">
            <span class="overview-stat-card__metric-value">{{ item.value }}</span>
            <span class="overview-stat-card__metric-label">{{ item.label }}</span>
          </div>
        </div>
      </div>
    </template>
  </ElCard>
</template>

<style scoped>
.overview-stat-card {
  border: none;
  border-radius: var(--radius-2xl);
  background: var(--bg-2);
  box-shadow: none;
  min-width: 0;
}

.overview-stat-card :deep(.el-card__body) {
  padding: 0;
}

/* ── hero：管理工作台今日调用分析 ── */
.overview-stat-card__hero {
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 24px;
  min-height: 162px;
  box-sizing: border-box;
}

.overview-stat-card__hero-icon-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--bg-1);
  flex-shrink: 0;
}

.overview-stat-card__hero-icon {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

.overview-stat-card__hero-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  flex: 1;
}

.overview-stat-card__hero-title {
  color: var(--text-secondary);
}

.overview-stat-card__hero-data {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.overview-stat-card__hero-value {
  font-size: 36px;
  font-weight: 500;
  line-height: 44px;
  color: var(--text-primary);
  word-break: break-all;
}

.overview-stat-card__hero-desc {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
}

/* ── trend：个人工作台今日调用分析 ── */
.overview-stat-card__trend {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  box-sizing: border-box;
  min-height: 280px;
}

.overview-stat-card__trend-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-stat-card__trend-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  object-fit: contain;
  /* 与标题同色 --text-secondary (#777) */
  filter: brightness(0) saturate(100%) invert(48%);
}

.overview-stat-card__trend-title {
  color: var(--text-secondary);
}

.overview-stat-card__trend-metrics {
  display: flex;
  align-items: flex-start;
  gap: 40px;
}

.overview-stat-card__trend-metric {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.overview-stat-card__trend-label {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.overview-stat-card__trend-value {
  font-size: 28px;
  font-weight: 500;
  line-height: 36px;
  color: var(--text-primary);
  white-space: nowrap;
}

.overview-stat-card__trend-chart {
  width: 100%;
  height: 140px;
  min-height: 140px;
  flex-shrink: 0;
}

.overview-stat-card__trend-chart > * {
  width: 100%;
  height: 140px;
}

/* ── metrics：调用分析页 ── */
.overview-stat-card--metrics {
  border-radius: var(--radius-2xl);
}

.overview-stat-card__metrics {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px 24px 24px 28px;
  box-sizing: border-box;
}

.overview-stat-card__metrics-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.overview-stat-card__metrics-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  object-fit: contain;
  /* 描边 SVG 用 mask 会空白；用 filter 近似 --text-secondary (#777) */
  filter: brightness(0) saturate(100%) invert(48%);
}

.overview-stat-card__metrics-title {
  color: var(--text-secondary);
}

.overview-stat-card__metrics-row {
  display: flex;
  align-items: flex-start;
  /* 20px 图标 + 12px 间距，与标题左对齐 → 距卡片左边 60px */
  padding-left: 32px;
  width: 100%;
  box-sizing: border-box;
}

.overview-stat-card__metric {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

.overview-stat-card__metric-value {
  font-size: 28px;
  font-weight: 500;
  line-height: 36px;
  color: var(--text-primary);
  white-space: nowrap;
}

.overview-stat-card__metric-label {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
  white-space: nowrap;
}

@media (max-width: 960px) {
  .overview-stat-card__hero {
    min-height: auto;
  }
}
</style>
