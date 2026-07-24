<template>
  <section class="tab-panel">
    <h2 class="tab-panel__title">性能监控</h2>
    <ElEmpty
      v-if="!grafanaDashboardPath"
      :description="`暂不支持该推理引擎的监控面板（${inferenceEngine || '未知'}）`"
      :image-size="80"
    />
    <iframe
      v-else
      class="tab-panel__iframe"
      :src="grafanaIframeSrc"
      title="Grafana 性能监控"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { ElEmpty } from 'element-plus';

const GRAFANA_PORT = 3000;
const GRAFANA_QUERY_BASE = 'orgId=1&from=now-30m&to=now&kiosk&theme=light';

/** 引擎名（小写）→ Grafana dashboard path */
const DASHBOARD_BY_ENGINE: Record<string, string> = {
  vllm: '/d/vllm-perf/vllm',
  sglang: '/d/sglang-perf/sglang',
};

const props = defineProps<{
  inferenceEngine?: string | null;
  grafanaJobName?: string | null;
}>();

const grafanaDashboardPath = computed(() => {
  const key = (props.inferenceEngine ?? '').trim().toLowerCase();
  return key ? DASHBOARD_BY_ENGINE[key] ?? null : null;
});

const grafanaIframeSrc = computed(() => {
  const path = grafanaDashboardPath.value;
  if (!path) return '';

  const host = window.location.hostname;
  let query = GRAFANA_QUERY_BASE;
  const job = (props.grafanaJobName ?? '').trim();
  if (job) {
    query += `&var-job=${encodeURIComponent(job)}`;
  }
  return `http://${host}:${GRAFANA_PORT}${path}?${query}`;
});
</script>

<style scoped>
.tab-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 32px 32px;
}

.tab-panel__title {
  margin: 2px 0 12px;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.tab-panel__iframe {
  flex: 1;
  width: 100%;
  min-height: 600px;
  border: none;
}
</style>
