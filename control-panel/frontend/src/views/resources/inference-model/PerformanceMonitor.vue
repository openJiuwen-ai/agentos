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
      :src="iframeSrc"
      title="Grafana 性能监控"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue';
import { ElEmpty } from 'element-plus';
import { useAuth } from '@/composables/useAuth';

const { accessToken, setGrafanaCookie } = useAuth();

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

const iframeSrc = ref('');

function buildGrafanaUrl(): string {
  const path = grafanaDashboardPath.value;
  if (!path) return '';

  let query = GRAFANA_QUERY_BASE;
  const job = (props.grafanaJobName ?? '').trim();
  if (job) {
    query += `&var-job=${encodeURIComponent(job)}`;
  }
  return `/grafana${path}?${query}`;
}

function refreshIframe() {
  if (!accessToken.value || !grafanaDashboardPath.value) {
    iframeSrc.value = '';
    return;
  }
  // 写入 Grafana 鉴权 cookie，供 nginx auth_request 验证
  setGrafanaCookie();
  iframeSrc.value = buildGrafanaUrl();
}

onMounted(refreshIframe);
watch(
  [() => props.inferenceEngine, () => props.grafanaJobName],
  () => refreshIframe(),
);
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
