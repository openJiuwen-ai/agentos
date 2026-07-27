<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import {
  ElButton,
  ElTable,
  ElTableColumn,
  ElInput,
  ElDialog,
  ElSelect,
  ElOption,
  ElTag,
  ElMessage,
  ElMessageBox,
  ElPagination,
  ElTooltip,
} from "element-plus";
import {
  Delete,
  Download,
  Search,
  Refresh,
} from "@element-plus/icons-vue";
import {
  createExport,
  getExports,
  getExportDownloadUrl,
  deleteExport,
  getLogComponents,
  getLogCategories,
  type LogExportTask,
  type LogComponent,
  type LogCategoryItem,
} from "@/api/logs";
import { http } from "@/api/index";

const tasks = ref<LogExportTask[]>([]);
const allComponents = ref<LogComponent[]>([]);
const categories = ref<LogCategoryItem[]>([]);
const loading = ref(false);
const searchKeyword = ref("");
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null);
const lastUpdateTime = ref("");

const currentPage = ref(1);
const pageSize = ref(10);

const filteredTasks = computed(() => {
  if (!searchKeyword.value.trim()) return tasks.value;
  const keyword = searchKeyword.value.toLowerCase();
  return tasks.value.filter(
    (t) =>
      t.task_id.toLowerCase().includes(keyword) ||
      t.component_name.toLowerCase().includes(keyword),
  );
});

const total = computed(() => filteredTasks.value.length);

const pagedTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredTasks.value.slice(start, start + pageSize.value);
});

const hasPending = computed(() =>
  tasks.value.some((t) => t.status === "pending" || t.status === "running"),
);

async function fetchTasks() {
  loading.value = true;
  try {
    tasks.value = await getExports();
    lastUpdateTime.value = formatUpdateTime(new Date());
    checkPending();
  } finally {
    loading.value = false;
  }
}

async function fetchComponents() {
  try {
    const [comps, cats] = await Promise.all([
      getLogComponents(),
      getLogCategories(),
    ]);
    allComponents.value = comps;
    categories.value = cats;
  } catch {
    /* ignore */
  }
}

function checkPending() {
  const has = tasks.value.some(
    (t) => t.status === "pending" || t.status === "running",
  );
  if (has && !pollingTimer.value) {
    startPolling();
  } else if (!has && pollingTimer.value) {
    stopPolling();
  }
}

function startPolling() {
  if (pollingTimer.value) return;
  pollingTimer.value = setInterval(async () => {
    await fetchTasks();
  }, 2000);
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value);
    pollingTimer.value = null;
  }
}

function onPageChange() {
  currentPage.value = 1;
}

async function handleDelete(taskId: string) {
  try {
    await ElMessageBox.confirm("确定要删除此导出任务吗？", "确认删除", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteExport(taskId);
    ElMessage.success("已删除");
    await fetchTasks();
  } catch {
    // cancelled
  }
}

async function downloadExportFile(task: LogExportTask) {
  try {
    const response = await http.get(getExportDownloadUrl(task.task_id), {
      responseType: "blob",
    });
    const url = URL.createObjectURL(response.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `logs-${task.task_type}-${task.task_id}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    ElMessage.error("下载失败");
  }
}

function getStatusTagType(status: string) {
  switch (status) {
    case "pending":
      return "info";
    case "running":
      return "warning";
    case "completed":
      return "success";
    case "failed":
      return "danger";
    default:
      return "info";
  }
}

function getStatusText(status: string): string {
  switch (status) {
    case "pending":
      return "等待中";
    case "running":
      return "执行中";
    case "completed":
      return "成功";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}-${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function formatUpdateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatDuration(task: LogExportTask): string {
  if (!task.created_at) return "-";
  const end = task.completed_at
    ? new Date(task.completed_at)
    : task.status === "running"
      ? new Date()
      : null;
  if (!end) return "-";
  const start = new Date(task.created_at);
  const diff = Math.floor((end.getTime() - start.getTime()) / 1000);
  if (diff < 0) return "-";
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}min${diff % 60}s`;
  return `${Math.floor(diff / 3600)}h${Math.floor((diff % 3600) / 60)}min`;
}

const showExportDialog = ref(false);
const exportComponentId = ref("");
const exportLineCount = ref(500);
const exportLineOptions = [100, 200, 500, 1000];
const exportSaving = ref(false);

const filteredComponents = computed(() => {
  return allComponents.value;
});

function openExportDialog() {
  exportComponentId.value = "";
  exportLineCount.value = 500;
  showExportDialog.value = true;
}

async function handleCreateExport() {
  if (!exportComponentId.value) {
    ElMessage.warning("请选择日志组件");
    return;
  }
  exportSaving.value = true;
  try {
    const result = await createExport({
      component_id: exportComponentId.value,
      line_count: exportLineCount.value,
    });
    ElMessage.success(`导出任务已创建: ${result.task_id}`);
    showExportDialog.value = false;
    await fetchTasks();
    startPolling();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "创建导出任务失败");
  } finally {
    exportSaving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([fetchTasks(), fetchComponents()]);
});

onUnmounted(() => stopPolling());
</script>

<template>
  <section class="page">
    <h1 class="page-title">任务中心</h1>

    <div class="toolbar">
      <div class="toolbar__left">
        <el-input
          v-model="searchKeyword"
          placeholder="请输入搜索内容"
          :prefix-icon="Search"
          clearable
          size="small"
          style="width: 220px"
          @input="onPageChange"
        />
      </div>
      <div class="toolbar__right">
        <span class="update-time">更新时间：{{ lastUpdateTime || "--" }}</span>
        <el-button
          :icon="Refresh"
          size="small"
          @click="fetchTasks"
        />
      </div>
    </div>

    <el-table :data="pagedTasks" v-loading="loading" stripe class="task-table">
      <el-table-column label="任务名称" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="mono-text">{{ row.task_type === "archive" ? "日志打包" : "日志导出" }}-{{ formatDateTime(row.created_at) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作对象" min-width="90">
        <template #default="{ row }">
          {{ row.component_name || row.source_name || "—" }}
        </template>
      </el-table-column>

      <el-table-column label="状态" min-width="90">
        <template #default="{ row }">
          <el-tag :type="getStatusTagType(row.status)" size="small">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="创建时间" min-width="140">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>

      <el-table-column label="结束时间" min-width="140">
        <template #default="{ row }">
          {{
            row.completed_at
              ? new Date(row.completed_at).toLocaleString()
              : "--"
          }}
        </template>
      </el-table-column>

      <el-table-column label="耗时" min-width="80">
        <template #default="{ row }">
          {{ formatDuration(row) }}
        </template>
      </el-table-column>

      <el-table-column label="操作" min-width="100" fixed="right">
        <template #default="{ row }">
          <el-tooltip content="下载" placement="top">
            <el-button
              v-if="row.status === 'completed'"
              text
              :icon="Download"
              size="small"
              type="primary"
              @click="downloadExportFile(row)"
            />
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button
              text
              :icon="Delete"
              size="small"
              type="danger"
              @click="handleDelete(row.task_id)"
            />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-row">
      <span class="total-text">总计：{{ total }}</span>
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="sizes, prev, pager, next, jumper"
        background
        small
      />
    </div>

    <el-dialog
      v-model="showExportDialog"
      title="创建导出任务"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="export-dialog-body">
        <div class="export-form-item">
          <label class="export-form-label">日志组件</label>
          <el-select
            v-model="exportComponentId"
            placeholder="选择日志组件"
            style="width: 100%"
          >
            <el-option
              v-for="comp in filteredComponents"
              :key="comp.id"
              :label="`${comp.category} / ${comp.name}`"
              :value="comp.id"
            />
          </el-select>
        </div>
        <div class="export-form-item">
          <label class="export-form-label">导出行数</label>
          <el-select
            v-model="exportLineCount"
            placeholder="选择行数"
            style="width: 100%"
          >
            <el-option
              v-for="n in exportLineOptions"
              :key="n"
              :label="`最近 ${n} 行`"
              :value="n"
            />
          </el-select>
        </div>
      </div>
      <template #footer>
        <el-button @click="showExportDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="exportSaving"
          @click="handleCreateExport"
          >创建</el-button
        >
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 20px;
  font-weight: 600;
  flex-shrink: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.toolbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.update-time {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.task-table {
  flex: 1;
  min-height: 0;
}

.task-table :deep(td),
.task-table :deep(th) {
  font-size: 15px;
}

.mono-text {
  font-family: "Consolas", "Monaco", "Courier New", monospace;
  font-size: 14px;
}

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  flex-shrink: 0;
}

.total-text {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.export-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.export-form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.export-form-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}
</style>
