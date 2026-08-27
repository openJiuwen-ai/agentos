<script setup lang="ts">
import { h, ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElButton, ElInput, ElSelect, ElOption, ElMessage } from 'element-plus';
import { ArrowLeft, Download } from '@element-plus/icons-vue';
import { useAuth } from '@/composables/useAuth';
import { resolveFilePath, createLokiExport } from '@/api/logs';

const route = useRoute();
const router = useRouter();
const { setGrafanaCookie } = useAuth();

const categoryFromQuery = (route.query.category as string) || '';
const keywordFromQuery = (route.query.keyword as string) || '';
const filePathFromQuery = (route.query.file_path as string) || '';
const ipFromQuery = (route.query.ip as string) || '';

const TIME_RANGE_OPTIONS = [
  { value: 'now-1h', label: '最近 1 小时' },
  { value: 'now-6h', label: '最近 6 小时' },
  { value: 'now-12h', label: '最近 12 小时' },
  { value: 'now-24h', label: '最近 24 小时' },
  { value: 'now-7d', label: '最近 7 天' },
];

const selectedCategory = ref(categoryFromQuery);
const keyword = ref(keywordFromQuery);
const filename = ref('');
const timeRange = ref('now-1h');

onMounted(async () => {
  // 写入 Grafana 鉴权 cookie，供 nginx auth_request 验证
  setGrafanaCookie();

  // iframe 只在挂载时设置一次 src，后续时间范围等参数变化走 location.replace，
  // 避免每次导航都在浏览器联合历史中新增记录
  if (iframeRef.value) {
    iframeRef.value.src = grafanaUrl.value;
  }

  if (categoryFromQuery && filePathFromQuery) {
    try {
      const result = await resolveFilePath(categoryFromQuery, filePathFromQuery);
      filename.value = result.resolved_path;
    } catch {
      filename.value = filePathFromQuery;
    }
  }
});

function buildLogQL(): string {
  let expr = '';
  if (selectedCategory.value) {
    expr = `{category="${selectedCategory.value}"}`;
  }
  if (keyword.value.trim()) {
    expr += ` |~ "(?i)${keyword.value.trim()}"`;
  }
  return expr;
}

const grafanaUrl = computed(() => {
  const params = new URLSearchParams();
  params.set('orgId', '1');
  params.set('panelId', '1');
  if (selectedCategory.value) {
    params.set('var-category', selectedCategory.value);
  }
  if (keyword.value.trim()) {
    params.set('var-keyword', keyword.value.trim());
  }
  if (filename.value.trim()) {
    params.set('var-filename', filename.value.trim());
  }
  params.set('from', timeRange.value);
  params.set('to', 'now');
  params.set('refresh', '10s');
  return `/grafana/d-solo/log-explore?${params.toString()}`;
});

function goBack() {
  router.push({ name: 'log-center' });
}

const downloadLoading = ref(false);

function parseTimeRange(value: string): { start: Date; end: Date } {
  const end = new Date();
  const match = /^now-(\d+)([smhd])$/.exec(value);
  let durationMs = 60 * 60 * 1000;
  if (match) {
    const amount = parseInt(match[1], 10);
    const unitMs: Record<string, number> = {
      s: 1000,
      m: 60_000,
      h: 3_600_000,
      d: 86_400_000,
    };
    durationMs = amount * (unitMs[match[2]] ?? 3_600_000);
  }
  return { start: new Date(end.getTime() - durationMs), end };
}

function buildTaskMessage(type: string, taskId: string) {
  return h('span', [
    `${type}已创建: ${taskId} `,
    h(
      'a',
      {
        href: '#',
        onClick: (e: Event) => {
          e.preventDefault();
          router.push({ name: 'task-center' });
        },
        style: { color: 'var(--el-color-primary)', textDecoration: 'underline' },
      },
      '查看任务',
    ),
  ]);
}

async function handleDownload() {
  const { start, end } = parseTimeRange(timeRange.value);
  downloadLoading.value = true;
  try {
    const result = await createLokiExport({
      category: selectedCategory.value || undefined,
      keyword: keyword.value.trim() || undefined,
      ip: ipFromQuery || undefined,
      filename: filename.value.trim() || undefined,
      start: start.toISOString(),
      end: end.toISOString(),
    });
    ElMessage({ message: buildTaskMessage('下载任务', result.task_id), type: 'success' });
  } catch {
    ElMessage.error('创建下载任务失败');
  } finally {
    downloadLoading.value = false;
  }
}

const iframeRef = ref<HTMLIFrameElement | null>(null);

watch(grafanaUrl, (url) => {
  const frame = iframeRef.value;
  if (!frame) return;
  if (!frame.src) {
    frame.src = url;
    return;
  }
  frame.contentWindow?.location.replace(url);
});
</script>

<template>
  <section class="page">
    <div class="breadcrumb">
      <ElButton :icon="ArrowLeft" @click="goBack" text size="small">返回日志中心</ElButton>
    </div>

    <div class="search-panel">
      <div class="search-row">
        <div class="search-field">
          <label class="search-label">关键词</label>
          <ElInput
            v-model="keyword"
            placeholder="输入关键词过滤..."
            clearable
            size="default"
            style="width: 280px"
            @keyup.enter="() => {}"
          />
        </div>

        <div class="search-field">
          <label class="search-label">时间范围</label>
          <ElSelect v-model="timeRange" size="default" style="width: 160px">
            <ElOption v-for="opt in TIME_RANGE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </ElSelect>
        </div>

        <div class="search-field search-field--download">
          <ElButton type="primary" :icon="Download" :loading="downloadLoading" @click="handleDownload"
            >下载日志</ElButton
          >
        </div>
      </div>

      <div class="logql-preview">
        <span class="logql-preview__label">LogQL:</span>
        <code class="logql-preview__expr">{{ buildLogQL() }}</code>
      </div>
    </div>

    <div class="iframe-wrapper">
      <iframe
        ref="iframeRef"
        class="grafana-iframe"
        allow="fullscreen"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      />
    </div>
  </section>
</template>

<style scoped>
.page {
  height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.breadcrumb {
  flex-shrink: 0;
  margin-bottom: 12px;
  padding: 0;
}

.search-panel {
  flex-shrink: 0;
  background: #ffffff;
  border-radius: 8px;
  padding: 16px 24px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color);
}

.search-row {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
}

.search-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.search-label {
  font-size: 13px;
  color: #777777;
  line-height: 20px;
}

.search-field--download {
  margin-left: auto;
}

.logql-preview {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.logql-preview__label {
  font-size: 12px;
  color: #999999;
  flex-shrink: 0;
}

.logql-preview__expr {
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #191919;
  word-break: break-all;
}

.iframe-wrapper {
  flex: 1;
  min-height: 0;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
}

.grafana-iframe {
  width: 100%;
  height: 100%;
  border: none;
}
</style>
