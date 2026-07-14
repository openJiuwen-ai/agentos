<script setup lang="ts">
import { ElIcon } from 'element-plus';
import { DataLine } from '@element-plus/icons-vue';

defineProps<{
  title: string;
}>();
</script>

<template>
  <div class="chart-card">
    <div class="chart-card__header">
      <el-icon :size="18" color="#2563eb"><DataLine /></el-icon>
      <span style="font-weight: 500">{{ title }}</span>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.chart-card {
  background: linear-gradient(180deg, #f0f7ff 0%, rgba(240, 247, 255, 0.6) 40%, #fff 100%);
  border-radius: var(--radius-card, 12px);
  padding: 20px;
  border: 1px solid #e8f0fe;
}

.chart-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
