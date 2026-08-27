<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import {
  ElButton,
  ElCard,
  ElTable,
  ElTableColumn,
  ElInput,
  ElTag,
  ElIcon,
  ElMessage,
  ElMessageBox,
  ElPagination,
  ElTooltip,
  vLoading,
} from "element-plus";
import {
  Delete,
  Download,
  Search,
  RefreshRight,
} from "@element-plus/icons-vue";
import {
  getExports,
  getExportDownloadUrl,
  deleteExport,
  type LogExportTask,
} from "@/api/logs";
import { http } from "@/api/index";
import { formatDateTime } from '@/utils/datetime';

defineOptions({
  directives: {
    loading: vLoading,
  },
});
const tasks = ref<LogExportTask[]>([]);
const loading = ref(false);
const searchKeyword = ref('');
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null);
const lastUpdateTime = ref('');

const currentPage = ref(1);
const pageSize = ref(10);

const filteredTasks = computed(() => {
  if (!searchKeyword.value.trim()) return tasks.value;
  const keyword = searchKeyword.value.toLowerCase();
  return tasks.value.filter(
    (t) => t.task_id.toLowerCase().includes(keyword) || t.component_name.toLowerCase().includes(keyword),
  );
});

const total = computed(() => filteredTasks.value.length);

const pagedTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredTasks.value.slice(start, start + pageSize.value);
});

const hasPending = computed(() => tasks.value.some((t) => t.status === 'pending' || t.status === 'running'));

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

function checkPending() {
  if (hasPending.value && !pollingTimer.value) {
    startPolling();
  } else if (!hasPending.value && pollingTimer.value) {
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
    await ElMessageBox.confirm('确定要删除此导出任务吗？', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    });
    await deleteExport(taskId);
    ElMessage.success('已删除');
    await fetchTasks();
  } catch {
    // cancelled
  }
}

async function downloadExportFile(task: LogExportTask) {
  try {
    const response = await http.get(getExportDownloadUrl(task.task_id), {
      responseType: 'blob',
    });
    const url = URL.createObjectURL(response.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${task.task_type}-${task.task_id}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    ElMessage.error('下载失败');
  }
}

function getStatusTagType(status: string) {
  switch (status) {
    case 'pending':
      return 'info';
    case 'running':
      return 'warning';
    case 'completed':
      return 'success';
    case 'failed':
      return 'danger';
    default:
      return 'info';
  }
}

function getStatusText(status: string): string {
  switch (status) {
    case 'pending':
      return '等待中';
    case 'running':
      return '执行中';
    case 'completed':
      return '成功';
    case 'failed':
      return '失败';
    default:
      return status;
  }
}

function handleStatusClick(task: LogExportTask) {
  if (task.status === 'failed' && task.error_message) {
    void showErrorDetail(task);
  }
}

async function showErrorDetail(task: LogExportTask) {
  try {
    await ElMessageBox.alert(task.error_message ?? '无错误信息', '导出失败原因', {
      confirmButtonText: '关闭',
      type: 'error',
      customStyle: { maxHeight: '70vh', overflowY: 'auto' },
    });
  } catch {
    // 关闭弹窗，无需处理
  }
}

function formatUpdateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatDuration(task: LogExportTask): string {
  if (!task.created_at) return '-';
  const end = task.completed_at ? new Date(task.completed_at) : task.status === 'running' ? new Date() : null;
  if (!end) return '-';
  const start = new Date(task.created_at);
  const diff = Math.floor((end.getTime() - start.getTime()) / 1000);
  if (diff < 0) return '-';
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}min${diff % 60}s`;
  return `${Math.floor(diff / 3600)}h${Math.floor((diff % 3600) / 60)}min`;
}

onMounted(fetchTasks);

onUnmounted(() => stopPolling());
</script>

<template>
  <section class="page">
    <div class="page-header-row">
      <h1 class="page-title">任务中心</h1>
      <div class="page-header-row__meta">
        <span class="update-time">更新时间：{{ lastUpdateTime || "--" }}</span>
        <ElButton
          text
          :loading="loading"
          :icon="RefreshRight"
          aria-label="刷新"
          class="refresh-btn"
          @click="fetchTasks"
        />
      </div>
    </div>

    <ElCard shadow="never" class="task-panel" body-class="task-panel__body">
      <div class="toolbar">
        <ElInput
          v-model="searchKeyword"
          class="toolbar__search"
          placeholder="请输入搜索内容"
          :prefix-icon="Search"
          clearable
          @input="onPageChange"
        />
      </div>

      <ElTable :data="pagedTasks" v-loading="loading" class="task-table">
        <ElTableColumn label="任务名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="task-name">
              {{ row.task_type === "archive" ? "日志打包" : "日志导出" }}-{{ formatDateTime(row.created_at) }}
            </span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作对象" min-width="100">
          <template #default="{ row }">
            {{ row.component_name || row.source_name || "—" }}
          </template>
        </ElTableColumn>

        <ElTableColumn label="状态" min-width="100">
          <template #default="{ row }">
            <ElTag
              :type="getStatusTagType(row.status)"
              size="small"
              effect="light"
              class="status-tag"
              :class="`status-tag--${row.status}`"
            >
              {{ getStatusText(row.status) }}
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn label="创建时间" min-width="170">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </ElTableColumn>

        <ElTableColumn label="结束时间" min-width="170">
          <template #default="{ row }">
            {{
              row.completed_at
                ? new Date(row.completed_at).toLocaleString()
                : "--"
            }}
          </template>
        </ElTableColumn>

        <ElTableColumn label="耗时" min-width="100">
          <template #default="{ row }">
            {{ formatDuration(row) }}
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作" min-width="100" fixed="right">
          <template #default="{ row }">
            <ElTooltip content="下载" placement="top">
              <ElButton
                v-if="row.status === 'completed'"
                text
                :icon="Download"
                class="action-btn"
                @click="downloadExportFile(row)"
              />
            </ElTooltip>
            <ElTooltip content="删除" placement="top">
              <ElButton
                text
                :icon="Delete"
                class="action-btn action-btn--danger"
                @click="handleDelete(row.task_id)"
              />
            </ElTooltip>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pagination-row">
        <span class="total-text">总计：{{ total }}</span>
        <ElPagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :total="total"
          layout="sizes, prev, pager, next, jumper"
          background
          small
        />
      </div>
    </ElCard>
  </section>
</template>

<style scoped>
.page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow: hidden;
  padding-bottom: 24px;
}

.page-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-shrink: 0;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 26px;
  color: var(--text-primary);
}

.page-header-row__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 22px;
  flex-shrink: 0;
}

.update-time {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.refresh-btn {
  padding: 0;
  margin: 0;
  width: 14px;
  height: 22px;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.refresh-btn :deep(.el-icon) {
  width: 14px;
  height: 14px;
  font-size: 14px;
  color: rgba(0, 0, 0, 0.6);
}

.task-panel {
  --el-card-border-color: transparent;
  --el-card-border-radius: var(--radius-2xl, 24px);
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: none;
  border-radius: var(--radius-2xl, 24px);
  background: var(--bg-2);
}

.task-panel :deep(.task-panel__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.toolbar__search {
  width: 280px;
}

.toolbar__search :deep(.el-input__wrapper) {
  border-radius: var(--radius-base);
}

.task-table {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.task-table :deep(.el-table__header th) {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-1);
}

.task-table :deep(.el-table__cell) {
  font-size: 14px;
  color: var(--text-primary);
}

.task-name {
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
}

.status-tag {
  border: none;
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
  line-height: 24px;
}

.status-tag--completed {
  --el-tag-bg-color: var(--tag-bg-success);
  --el-tag-text-color: var(--tag-text-success);
  --el-tag-border-color: transparent;
}

.status-tag--failed {
  --el-tag-bg-color: var(--tag-bg-error);
  --el-tag-text-color: var(--tag-text-error);
  --el-tag-border-color: transparent;
}

.status-tag--running,
.status-tag--pending {
  --el-tag-bg-color: var(--tag-bg-info);
  --el-tag-text-color: var(--tag-text-info);
  --el-tag-border-color: transparent;
}

.action-btn {
  width: 28px;
  height: 28px;
  min-height: 28px;
  margin: 0;
  padding: 0;
  color: var(--text-secondary);
}

.action-btn:hover {
  color: var(--color-primary);
}

.action-btn--danger:hover {
  color: var(--error);
}

.status-tag--clickable {
  cursor: pointer;
}

.status-tag__icon {
  margin-left: 2px;
  vertical-align: -0.125em;
}

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding-top: 8px;
}

.total-text {
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}
</style>
