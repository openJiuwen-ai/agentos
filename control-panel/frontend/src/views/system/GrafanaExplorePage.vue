<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElButton, ElInput, ElSelect, ElOption } from "element-plus";
import { ArrowLeft, Search } from "@element-plus/icons-vue";
import { useAuth } from "@/composables/useAuth";
import { resolveFilePath } from "@/api/logs";

const route = useRoute();
const router = useRouter();
const { accessToken } = useAuth();

const categoryFromQuery = (route.query.category as string) || "";
const keywordFromQuery = (route.query.keyword as string) || "";
const componentIdFromQuery = (route.query.component_id as string) || "";
const filePathFromQuery = (route.query.file_path as string) || "";

const TIME_RANGE_OPTIONS = [
  { value: "now-1h", label: "最近 1 小时" },
  { value: "now-6h", label: "最近 6 小时" },
  { value: "now-12h", label: "最近 12 小时" },
  { value: "now-24h", label: "最近 24 小时" },
  { value: "now-7d", label: "最近 7 天" },
];

const selectedCategory = ref(categoryFromQuery);
const keyword = ref(keywordFromQuery);
const filename = ref("");
const hostname = ref("");
const timeRange = ref("now-1h");

onMounted(async () => {
  if (componentIdFromQuery && filePathFromQuery) {
    try {
      const result = await resolveFilePath(componentIdFromQuery, filePathFromQuery);
      filename.value = result.resolved_path;
    } catch {
      filename.value = filePathFromQuery;
    }
  }
});

function buildLogQL(): string {
  let expr = "";
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
  params.set("orgId", "1");
  params.set("panelId", "1");
  if (selectedCategory.value) {
    params.set("var-category", selectedCategory.value);
  }
  if (keyword.value.trim()) {
    params.set("var-keyword", keyword.value.trim());
  }
  if (filename.value.trim()) {
    params.set("var-filename", filename.value.trim());
  }
  if (hostname.value.trim()) {
    params.set("var-host", hostname.value.trim());
  }
  params.set("from", timeRange.value);
  params.set("to", "now");
  params.set("refresh", "10s");
  params.set("token", accessToken.value || "");
  return `/grafana/d-solo/log-explore?${params.toString()}`;
});

function goBack() {
  router.push({ name: "log-center" });
}

watch(grafanaUrl, () => {
  if (iframeRef.value) {
    iframeRef.value.src = grafanaUrl.value;
  }
});

const iframeRef = ref<HTMLIFrameElement | null>(null);
</script>

<template>
  <section class="page">
    <div class="breadcrumb">
      <el-button :icon="ArrowLeft" @click="goBack" text size="small"
        >返回日志中心</el-button
      >
    </div>

    <div class="search-panel">
      <div class="search-row">

        <div class="search-field">
          <label class="search-label">关键词</label>
          <el-input
            v-model="keyword"
            placeholder="输入关键词过滤..."
            clearable
            size="default"
            style="width: 280px"
            @keyup.enter="() => {}"
          />
        </div>

        <div class="search-field">
          <label class="search-label">主机名</label>
          <el-input
            v-model="hostname"
            placeholder="输入主机名..."
            clearable
            size="default"
            style="width: 180px"
          />
        </div>

        <div class="search-field">
          <label class="search-label">时间范围</label>
          <el-select
            v-model="timeRange"
            size="default"
            style="width: 160px"
          >
            <el-option
              v-for="opt in TIME_RANGE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
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
        :src="grafanaUrl"
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
  font-family: "Consolas", "Monaco", "Courier New", monospace;
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
