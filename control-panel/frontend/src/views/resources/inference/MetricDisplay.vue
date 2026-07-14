<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
  unit?: string;
  trend?: string;
  trendLabel?: string;
  trendType?: 'up' | 'down';
}>();
</script>

<template>
  <div class="metric-display">
    <span class="metric-display__label">{{ label }}</span>
    <div class="metric-display__value">
      <span class="metric-display__number">{{ value }}</span>
      <span v-if="unit" class="metric-display__unit">{{ unit }}</span>
    </div>
    <div v-if="trend" class="metric-display__trend" :class="`metric-display__trend--${trendType}`">
      <span>{{ trend }}</span>
      <span v-if="trendLabel" class="metric-display__trend-label">{{ trendLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.metric-display {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-display__label {
  font-size: 12px;
  color: #9ca3af;
}

.metric-display__value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.metric-display__number {
  font-size: 28px;
  font-weight: 600;
  color: #111827;
}

.metric-display__unit {
  font-size: 12px;
  color: #6b7280;
}

.metric-display__trend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  margin-top: 4px;
}

.metric-display__trend--up {
  color: #ef4444;
}

.metric-display__trend--down {
  color: #22c55e;
}

.metric-display__trend-label {
  color: #9ca3af;
  font-weight: 400;
}
</style>
