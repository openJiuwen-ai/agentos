<script setup lang="ts">
import { h, ref, onMounted, onUnmounted, watch, nextTick, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ElButton,
  ElInput,
  ElSelect,
  ElOption,
  ElMessage,
  ElTooltip,
  ElSwitch,
} from "element-plus";
import { ArrowLeft, CopyDocument } from "@element-plus/icons-vue";
import { useLogs, type LogLine } from "@/composables/useLogs";
import { createFileDownloadTask } from "@/api/logs";

const route = useRoute();
const router = useRouter();

const { logLines, wsConnected, addLogLines, clearLogLines } =
  useLogs();

const filePath = computed(() => (route.query.path as string) || "");
const fileName = computed(() => (route.query.name as string) || "");
const componentDisplayName = computed(() => fileName.value || filePath.value || "实时日志");
const loading = ref(false);

let ws: WebSocket | null = null;
const logContainerRef = ref<HTMLElement | null>(null);
const autoScroll = ref(true);
const wordWrap = ref(false);
const searchKeyword = ref("");
const showLines = ref(1000);

const displayLines = computed(() => {
  let lines = logLines.value;
  if (searchKeyword.value.trim()) {
    const keyword = searchKeyword.value.toLowerCase();
    lines = lines.filter((line) => line.raw.toLowerCase().includes(keyword));
  }
  return lines;
});

function connectWebSocket() {
  if (ws) ws.close();
  clearLogLines();
  wsConnected.value = false;

  const token = localStorage.getItem("access_token") || "";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const url = `${protocol}//${host}/api/v1/logs/stream?token=${encodeURIComponent(token)}&paths=${encodeURIComponent(filePath.value)}`;

  ws = new WebSocket(url);
  ws.onopen = () => {
    wsConnected.value = true;
  };
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "init" || msg.type === "new_line") {
        const lines: LogLine[] = (msg.lines || []).map(
          (l: Record<string, string>) => ({
            raw: l.raw || "",
          }),
        );
        addLogLines(lines);
      }
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => {
    wsConnected.value = false;
  };
  ws.onerror = () => {
    wsConnected.value = false;
  };
}

function disconnectWebSocket() {
  if (ws) {
    ws.close();
    ws = null;
  }
  wsConnected.value = false;
}

function goBack() {
  router.push({ name: "log-center" });
}

function copyFileName() {
  navigator.clipboard.writeText(fileName.value || filePath.value).then(() => {
    ElMessage.success("已复制");
  });
}

function getFileName(): string {
  return fileName.value || "";
}

function scrollToBottom() {
  const container = logContainerRef.value;
  if (container) container.scrollTop = container.scrollHeight;
}

function onLogScroll() {
  const container = logContainerRef.value;
  if (!container) return;
  autoScroll.value =
    container.scrollTop + container.clientHeight >=
    container.scrollHeight - 48;
}

watch(displayLines, () => {
  nextTick(() => {
    if (autoScroll.value) scrollToBottom();
  });
});

async function handleDownload() {
  if (!filePath.value) return;
  try {
    const result = await createFileDownloadTask(
      filePath.value,
      fileName.value || undefined,
    );
    ElMessage({
      message: h("span", [
        `下载任务已创建: ${result.task_id} `,
        h(
          "a",
          {
            href: "#",
            onClick: (e: Event) => {
              e.preventDefault();
              router.push({ name: "task-center" });
            },
            style: { color: "var(--el-color-primary)", textDecoration: "underline" },
          },
          "查看任务",
        ),
      ]),
      type: "success",
    });
  } catch {
    ElMessage.error("创建下载任务失败");
  }
}

const LEVEL_RE = /\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+(\w+)/;

function getLevelClass(raw: string): string {
  const m = raw.match(LEVEL_RE);
  if (!m) return "";
  const lvl = m[1].toUpperCase();
  if (lvl === "CRITICAL" || lvl === "FATAL" || lvl === "ERROR") return "error";
  if (lvl === "WARN" || lvl === "WARNING") return "warn";
  if (lvl === "INFO") return "info";
  if (lvl === "DEBUG" || lvl === "TRACE") return "debug";
  return "";
}

onMounted(() => {
  loading.value = false;
  nextTick(() => {
    connectWebSocket();
  });
});

onUnmounted(() => disconnectWebSocket());
</script>

<template>
  <section class="page">
    <div class="breadcrumb">
      <el-button :icon="ArrowLeft" @click="goBack" text size="small"
        >返回</el-button
      >
    </div>

    <div class="content-card">
      <div class="card-header">
        <div class="card-header__left">
          <h1 class="card-title">
            {{ componentDisplayName }}
          </h1>
        </div>
        <div class="card-header__right">
          <el-select
            v-model="showLines"
            size="small"
            style="width: 100px"
          >
            <el-option label="100行" :value="100" />
            <el-option label="500行" :value="500" />
            <el-option label="1000行" :value="1000" />
            <el-option label="5000行" :value="5000" />
            <el-option label="全部" :value="0" />
          </el-select>
          <el-button
            type="default"
            size="small"
            @click="handleDownload"
            class="download-btn"
            >下载</el-button
          >
        </div>
      </div>

      <div class="card-toolbar">
        <div class="toolbar-item">
          <span class="toolbar-label">自动换行</span>
          <el-switch v-model="wordWrap" />
        </div>

        <div class="toolbar-item">
          <span class="toolbar-label">搜索关键词</span>
          <el-input
            v-model="searchKeyword"
            placeholder="请输入搜索内容"
            clearable
            style="width: 296px"
          />
        </div>
      </div>

      <div class="log-container">
        <div class="log-container__header">
          <span class="log-container__filename">{{
            getFileName() || "—"
          }}</span>
          <el-tooltip content="复制" placement="top">
            <el-button
              :icon="CopyDocument"
              text
              size="small"
              @click="copyFileName"
            />
          </el-tooltip>
          <span class="log-container__copy-text" @click="copyFileName"
            >复制</span
          >
        </div>

        <div
          ref="logContainerRef"
          class="log-container__body"
          :class="{ 'log-container__body--wrap': wordWrap }"
          @scroll="onLogScroll"
        >
          <div
            v-for="(line, i) in displayLines"
            :key="i"
            class="log-line"
            :class="getLevelClass(line.raw)"
          >
            {{ line.raw }}
          </div>
          <div v-if="displayLines.length === 0" class="log-container__empty">
            <span v-if="!wsConnected">正在连接...</span>
            <span v-else-if="searchKeyword">无匹配结果</span>
            <span v-else>等待日志数据...</span>
          </div>
        </div>
      </div>
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
  margin-bottom: 13px;
  padding: 0;
}

.content-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 8px;
  padding: 16px 24px 20px 24px;
  gap: 20px;
  min-height: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-shrink: 0;
}

.card-header__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  color: #191919;
  line-height: 28px;
}

.card-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-update-time {
  font-size: 14px;
  color: #777777;
  line-height: 22px;
}

.download-btn {
  background-color: #0067d1;
  color: #ffffff;
  border: none;
  border-radius: 4px;
  padding: 5px 30px;
  font-size: 14px;
}

.download-btn:hover {
  background-color: #0056b3;
  color: #ffffff;
}

.card-toolbar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

.toolbar-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-label {
  min-width: 80px;
  font-size: 16px;
  white-space: nowrap;
  color: #191919;
  line-height: 16px;
  flex-shrink: 0;
}

.log-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #dfdfdf;
  border-radius: 8px;
  min-height: 0;
  overflow: hidden;
}

.log-container__header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  background: #f3f3f3;
  border-radius: 8px 8px 0 0;
  border-bottom: 1px solid #dfdfdf;
  flex-shrink: 0;
}

.log-container__filename {
  font-size: 12px;
  color: #191919;
  line-height: 20px;
  font-family: "Consolas", "Monaco", "Courier New", monospace;
}

.log-container__copy-text {
  font-size: 12px;
  color: #191919;
  line-height: 20px;
  cursor: pointer;
  user-select: none;
}

.log-container__copy-text:hover {
  color: #0067d1;
}

.log-container__body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: #ffffff;
  border-radius: 0 0 8px 8px;
  padding: 4px 16px 8px 16px;
  font-family: "Consolas", "Monaco", "Courier New", monospace;
  font-size: 12px;
  line-height: 16px;
  position: relative;
}

.log-container__body--wrap {
  white-space: pre-wrap;
  word-break: break-word;
}

.log-container__body--wrap .log-line {
  white-space: pre-wrap;
}

.log-container__empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #aeaeae;
  font-size: 14px;
}

.log-line {
  white-space: pre;
  min-height: 16px;
  color: #191919;
}

.log-line.error {
  color: #d32f2f;
}

.log-line.warn {
  color: #f57c00;
}

.log-line.info {
  color: #1976d2;
}

.log-line.debug {
  color: #757575;
}
</style>
