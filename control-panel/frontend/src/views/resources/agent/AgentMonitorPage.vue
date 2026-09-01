<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import {
  ElButton,
  ElInput,
  ElTable,
  ElTableColumn,
  ElPagination,
  ElPopover,
  ElCheckboxGroup,
  ElCheckbox,
  ElMessage,
  vLoading,
} from 'element-plus';
import { RefreshRight } from '@element-plus/icons-vue';
import searchIcon from '@/assets/images/search-icon.png';
import funnelIcon from '@/assets/images/funnel-icon.png';
import avatarIcon from '@/assets/images/avatar.svg';
import frameworkDefaultIcon from '@/assets/images/framework-page/default-framework-icon.png';
import { fetchInstances, type InstanceEntry } from '@/api/agent';
import { ApiError } from '@/api';
import { usePolling } from '@/composables/usePolling';
import { formatDateTime } from '@/utils/datetime';

defineOptions({
  directives: {
    loading: vLoading,
  },
});

// ── 状态色（对齐 UI 设计稿） ──
const STATUS_CONFIG: Record<string, { label: string; dot: string }> = {
  运行: { label: '运行中', dot: 'var(--success)' },
  异常: { label: '异常', dot: 'var(--error)' },
};
const STOPPED_CONFIG = { label: '已停止', dot: 'var(--text-placeholder)' };

function statusDisplay(status: string | null) {
  if (status && STATUS_CONFIG[status]) return STATUS_CONFIG[status];
  return STOPPED_CONFIG;
}

// ── 响应式状态 ──
const instances = ref<InstanceEntry[]>([]);
const listLoading = ref(true);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const totalPages = ref(1);

const filterFramework = ref('');
const filterStatus = ref<string[]>([]);
const keyword = ref('');
const sortField = ref('');
const sortOrder = ref('');
const frameworkPopoverVisible = ref(false);
const statusPopoverVisible = ref(false);
const tableRef = ref<InstanceType<typeof ElTable>>();

const overviewTotal = ref(0);
const overviewRunning = ref(0);
const overviewAbnormal = ref(0);
const overviewStopped = ref(0);
const firstLoaded = ref(false);
const lastUpdateTime = ref('');
const unavailableMsg = ref('');

let instancesAbort: AbortController | null = null;

// ── 30s 自动刷新：与 Appliance 硬件监控一致的 setTimeout 递归轮询 ──
const AUTO_REFRESH_INTERVAL = 30 * 1000;
const { restart: restartPollTimer, stop: stopPollTimer } = usePolling(AUTO_REFRESH_INTERVAL);

// ── 计算属性 ──
const pageSummary = computed(() => `总计：${total.value}`);

const statusBarSegments = computed(() => {
  const running = Math.max(0, overviewRunning.value);
  const abnormal = Math.max(0, overviewAbnormal.value);
  const stopped = Math.max(0, overviewStopped.value);
  const max = Math.max(running, abnormal, stopped);

  function barHeight(value: number): string {
    if (value <= 0 || max <= 0) {
      return '2px';
    }
    const percent = `${(value / max) * 100}%`;
    if (value === 1 && max > 1) {
      return `max(4px, ${percent})`;
    }
    return percent;
  }

  return [
    { key: 'running', label: '运行', value: running, height: barHeight(running) },
    { key: 'abnormal', label: '异常', value: abnormal, height: barHeight(abnormal) },
    { key: 'stopped', label: '停止', value: stopped, height: barHeight(stopped) },
  ];
});

const emptyText = computed(() => {
  if (listLoading.value) return '加载中...';
  if (unavailableMsg.value) return unavailableMsg.value;
  if (total.value === 0) return '暂无实例';
  if (instances.value.length === 0 && page.value > totalPages.value) {
    return '当前页无数据，数据可能已更新，请返回第 1 页或刷新';
  }
  return '暂无实例';
});

const sortParam = computed(() => (sortField.value && sortOrder.value ? `${sortField.value}:${sortOrder.value}` : ''));

// ── 方法 ──
function formatUpdateTime() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function resetTableState() {
  instances.value = [];
  total.value = 0;
  totalPages.value = 1;
}

function resetOverview() {
  overviewTotal.value = 0;
  overviewRunning.value = 0;
  overviewAbnormal.value = 0;
  overviewStopped.value = 0;
}

const REGISTRY_ERROR_MSG: Record<number, string> = {
  502: '注册中心后端不可达',
  503: '注册中心服务未配置，智能体监控不可用',
  504: '注册中心后端响应超时',
};

async function loadInstances(updateOverview: boolean, refresh = false, silent = false) {
  if (instancesAbort) {
    instancesAbort.abort();
  }
  const controller = new AbortController();
  instancesAbort = controller;

  if (!silent) {
    listLoading.value = true;
  }
  unavailableMsg.value = '';

  try {
    const data = await fetchInstances(
      {
        page: page.value,
        size: pageSize.value,
        sort: sortParam.value || undefined,
        keyword: keyword.value || undefined,
        status: filterStatus.value.length > 0 ? filterStatus.value.join(',') : undefined,
        framework: filterFramework.value || undefined,
        refresh: refresh ? true : undefined,
      },
      { signal: controller.signal },
    );

    if (instancesAbort !== controller) return;
    instances.value = data.items;
    total.value = data.total;
    totalPages.value = data.total_pages;
    if (updateOverview) {
      overviewTotal.value = data.overview_total;
      overviewRunning.value = data.overview_running;
      overviewAbnormal.value = data.overview_abnormal;
      overviewStopped.value = data.overview_stopped;
      firstLoaded.value = true;
      lastUpdateTime.value = formatUpdateTime();
    }
  } catch (e) {
    if (e instanceof Error && e.message === 'canceled') return;

    if (e instanceof ApiError && e.status != null && e.status in REGISTRY_ERROR_MSG) {
      // 注册中心不可达/未配置/格式异常/超时：直接显示后端返回的错误原因
      console.error('[AgentMonitor] 注册中心异常(%d): %s', e.status, e.message);
      unavailableMsg.value = e.message;
      resetTableState();
      if (updateOverview) resetOverview();
      return;
    }

    console.error('[AgentMonitor] 加载实例失败:', e);
    unavailableMsg.value = e instanceof Error ? e.message : '加载失败';
    resetTableState();
  } finally {
    if (instancesAbort === controller) {
      listLoading.value = false;
    }
  }
}

const pollTask = () => loadInstances(true, true, true);

function handleRefresh() {
  page.value = 1;
  keyword.value = '';
  sortField.value = '';
  sortOrder.value = '';
  filterFramework.value = '';
  filterStatus.value = [];
  tableRef.value?.clearSort();
  // 手动刷新后重置 30s 倒计时（对齐 Appliance 的 handleDetailRefresh）
  restartPollTimer(pollTask);
  void loadInstances(true, true);
}

function onFilterChange() {
  page.value = 1;
  frameworkPopoverVisible.value = false;
  loadInstances(false);
}

function onStatusFilterClose() {
  page.value = 1;
  loadInstances(false);
}

function onSearchChange() {
  page.value = 1;
  loadInstances(false);
}

function onSortChange({ prop, order }: { prop: string | null; order: string | null }) {
  if (order === 'ascending') {
    sortField.value = prop || '';
    sortOrder.value = 'asc';
  } else if (order === 'descending') {
    sortField.value = prop || '';
    sortOrder.value = 'desc';
  } else {
    sortField.value = '';
    sortOrder.value = '';
  }
  page.value = 1;
  loadInstances(false);
}

function onPageChange() {
  loadInstances(false);
}

function onSizeChange() {
  page.value = 1;
  loadInstances(false);
}

function resetFrameworkFilter() {
  filterFramework.value = '';
  onFilterChange();
}

// ── 生命周期 ──
onMounted(() => {
  // 首次加载完成后才开始 30s 轮询（对齐 Appliance onMounted 的 restartPollTimer）
  void loadInstances(true).finally(() => {
    restartPollTimer(pollTask);
  });
});
onUnmounted(() => {
  stopPollTimer();
  if (instancesAbort) {
    instancesAbort.abort();
  }
});
</script>

<template>
  <section class="page agent-monitor">
    <!-- 操作区 -->
    <div class="agent-monitor__header">
      <h1 class="title-l1 agent-monitor__title">智能体监控</h1>
      <div class="agent-monitor__header-right">
        <span v-if="lastUpdateTime" class="agent-monitor__update-time">更新时间：{{ lastUpdateTime }}</span>
        <ElButton
          text
          :loading="listLoading"
          :icon="RefreshRight"
          aria-label="刷新"
          class="agent-monitor__refresh"
          @click="handleRefresh"
        />
      </div>
    </div>

    <!-- 概览行 -->
    <div class="overview-row">
      <article class="overview-card">
        <h2 class="title-l3 overview-card__title">智能体实例总览</h2>
        <div class="overview-card__body">
          <div class="overview-card__main">
            <span class="title-l4 overview-card__label">智能体实例数</span>
            <span class="overview-card__big-value">
              {{ firstLoaded ? overviewTotal : '—' }}
              <span class="overview-card__unit">个</span>
            </span>
          </div>
          <div class="overview-card__chart-wrap">
            <div v-for="seg in statusBarSegments" :key="seg.key" class="status-col">
              <div class="status-col__track" aria-hidden="true">
                <span class="status-col__bar" :class="`is-${seg.key}`" :style="{ height: seg.height }" />
              </div>
              <span class="status-col__legend">
                {{ seg.label }}
                {{ firstLoaded ? seg.value : '—' }}
              </span>
            </div>
          </div>
        </div>
      </article>

      <article class="overview-card overview-card--resource"></article>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <h2 class="title-l3 table-header__title">智能体实例</h2>
      <ElInput
        v-model="keyword"
        class="table-header__search"
        placeholder="请输入搜索内容"
        clearable
        @keyup.enter="onSearchChange"
        @clear="onSearchChange"
      >
        <template #prefix>
          <img :src="searchIcon" alt="" width="14" height="14" class="table-header__search-icon" />
        </template>
      </ElInput>

      <ElTable
        ref="tableRef"
        v-loading="listLoading"
        :data="instances"
        row-key="service_id"
        class="agent-table app-table"
        :border="false"
        :empty-text="emptyText"
        @sort-change="onSortChange"
      >
        <ElTableColumn
          prop="service_id"
          label="实例名称"
          min-width="200"
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
        >
          <template #default="{ row }">
            <span>{{ row.service_id }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="framework" label="智能体框架" min-width="180">
          <template #header>
            <div class="filter-header">
              <span>智能体框架</span>
              <ElPopover v-model:visible="frameworkPopoverVisible" trigger="click" placement="bottom" :width="240">
                <template #reference>
                  <span class="filter-icon" :class="{ 'filter-icon--active': !!filterFramework }">
                    <img :src="funnelIcon" alt="" width="12" height="12" />
                  </span>
                </template>
                <div class="filter-popover">
                  <ElInput v-model="filterFramework" placeholder="输入框架名" clearable @keyup.enter="onFilterChange" />
                  <div class="filter-popover__actions">
                    <ElButton size="small" @click="resetFrameworkFilter">重置</ElButton>
                    <ElButton size="small" type="primary" @click="onFilterChange">查询</ElButton>
                  </div>
                </div>
              </ElPopover>
            </div>
          </template>
          <template #default="{ row }">
            <div class="framework-cell">
              <img :src="frameworkDefaultIcon" alt="" class="framework-cell__icon" />
              <span>{{ row.framework }}</span>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="status" label="运行状态" min-width="140">
          <template #header>
            <div class="filter-header">
              <span>运行状态</span>
              <ElPopover
                v-model:visible="statusPopoverVisible"
                trigger="click"
                placement="bottom"
                :width="160"
                @hide="onStatusFilterClose"
              >
                <template #reference>
                  <span class="filter-icon" :class="{ 'filter-icon--active': filterStatus.length > 0 }">
                    <img :src="funnelIcon" alt="" width="12" height="12" />
                  </span>
                </template>
                <div class="filter-popover filter-popover--checkbox">
                  <ElCheckboxGroup v-model="filterStatus">
                    <ElCheckbox value="运行">运行中</ElCheckbox>
                    <ElCheckbox value="异常">异常</ElCheckbox>
                    <!-- stopped 为英文 sentinel：注册中心只返回"运行"/"异常"，此处代表 status 缺失(None)的归一态"已停止" -->
                    <ElCheckbox value="stopped">已停止</ElCheckbox>
                  </ElCheckboxGroup>
                </div>
              </ElPopover>
            </div>
          </template>
          <template #default="{ row }">
            <span class="status-cell">
              <span class="status-cell__dot" :style="{ background: statusDisplay(row.status).dot }" />
              {{ statusDisplay(row.status).label }}
            </span>
          </template>
        </ElTableColumn>

        <ElTableColumn
          prop="user"
          label="所属用户"
          min-width="140"
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
        >
          <template #default="{ row }">
            <div class="user-cell">
              <img :src="avatarIcon" alt="" class="user-cell__avatar" />
              <span>{{ row.user }}</span>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn
          prop="framework_version"
          label="框架版本号"
          min-width="120"
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
        >
          <template #default="{ row }">
            <span>{{ row.framework_version }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn
          prop="address"
          label="沙箱IP地址"
          min-width="160"
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
        >
          <template #default="{ row }">
            <span>{{ row.address }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn
          prop="node"
          label="沙箱节点"
          min-width="203"
          show-overflow-tooltip
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
          class-name="col-node"
        >
          <template #default="{ row }">
            <span>{{ row.node }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn
          prop="created_at"
          label="创建时间"
          min-width="203"
          show-overflow-tooltip
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
        >
          <template #default="{ row }">
            <span>{{ formatDateTime(row.created_at) }}</span>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pagination-row">
        <span class="pagination-total">{{ pageSummary }}</span>
        <ElPagination
          v-if="total > 0"
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="sizes, prev, slot, next"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        >
          <span class="pagination-page">{{ page }}/{{ totalPages }}</span>
        </ElPagination>
      </div>
    </div>
  </section>
</template>

<style scoped>
.agent-monitor {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 24px 32px;
}

/* ── 操作区 ── */
.agent-monitor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  height: 28px;
  margin-bottom: 20px;
}

.agent-monitor__header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 22px;
  flex-shrink: 0;
}

.agent-monitor__update-time {
  font-size: 14px;
  font-weight: 400;
  line-height: 19px;
  color: rgba(0, 0, 0, 0.6);
}

.agent-monitor__refresh {
  padding: 0;
  margin: 0;
  width: 14px;
  height: 22px;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.agent-monitor__refresh :deep(.el-icon) {
  width: 14px;
  height: 14px;
  font-size: 14px;
  color: rgba(0, 0, 0, 0.6);
}

/* ── 概览行 ── */
.overview-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex-shrink: 0;
  margin-bottom: 24px;
}

.overview-card {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-width: 0;
  padding: 24px;
  background: var(--bg-2);
  border-radius: 24px;
}

.overview-card__body {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 24px;
}

.overview-card__main {
  display: flex;
  flex-direction: column;
  gap: 52px;
  flex-shrink: 0;
}

.overview-card__big-value {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
  font-size: 48px;
  font-weight: 500;
  line-height: 56px;
  color: var(--text-primary);
}

.overview-card__unit {
  font-size: 16px;
  font-weight: 500;
  line-height: 24px;
  color: var(--text-primary);
}

.overview-card__chart-wrap {
  display: flex;
  align-items: stretch;
  justify-content: flex-end;
  gap: 16px;
  flex: 1;
  min-width: 0;
}

.status-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  gap: 8px;
}

.status-col__track {
  display: flex;
  align-items: flex-end;
  flex: 1;
  width: 72px;
  min-height: 0;
}

.status-col__bar {
  display: block;
  width: 72px;
  border-radius: 8px 8px 2px 2px;
}

.status-col__bar.is-running {
  background: linear-gradient(180deg, #61cfbe 0%, #d8f7f1 100%);
}

.status-col__bar.is-abnormal {
  background: linear-gradient(180deg, #e02128 0%, #ffd4d6 100%);
}

.status-col__bar.is-stopped {
  background: linear-gradient(180deg, #c9c9c9 0%, #f5f5f5 100%);
}

.status-col__legend {
  font-size: 14px;
  font-weight: 500;
  line-height: 19px;
  color: rgba(0, 0, 0, 0.5);
  white-space: nowrap;
}

.framework-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.framework-cell__icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 4px;
  object-fit: cover;
}

@media (max-width: 1280px) {
  .overview-row {
    grid-template-columns: 1fr;
  }

  .overview-card__body {
    min-height: 0;
  }
}

/* ── 表格卡 ── */
.table-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 24px;
  background: var(--bg-2);
  border-radius: 24px;
}

.table-header__title {
  margin: 0 0 20px;
  flex-shrink: 0;
}

.table-header__search {
  width: 296px;
  flex-shrink: 0;
  margin-bottom: 12px;
}

.agent-table {
  width: 100%;
  flex: 1;
}

/* ── 列头筛选 ── */
.filter-header {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.filter-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: color 0.2s;
}

.filter-icon:hover {
  color: var(--text-primary);
}

.filter-icon--active {
  color: var(--color-primary);
}

.filter-popover {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filter-popover__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.filter-popover--checkbox {
  gap: 8px;
}

.filter-popover--checkbox :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── 状态列 ── */
.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
}

.status-cell__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ── 用户列 ── */
.user-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.user-cell__avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.1);
  object-fit: cover;
}

/* ── 分页 ── */
.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  flex-shrink: 0;
  min-height: 32px;
}

.pagination-total {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
}

.pagination-page {
  min-width: 40px;
  padding: 0 8px;
  text-align: center;
  font-size: 14px;
  line-height: 32px;
  color: var(--text-primary);
  user-select: none;
}

:deep(.table-header__search .el-input__wrapper) {
  height: 32px;
  min-height: 32px;
  padding: 5px 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: none;
}

:deep(.table-header__search .el-input__wrapper:hover) {
  border-color: var(--border-hover);
  box-shadow: none;
}

:deep(.table-header__search .el-input__wrapper.is-focus) {
  border-color: var(--border-focus);
  box-shadow: none;
}

:deep(.table-header__search .el-input__prefix),
:deep(.table-header__search .el-input__suffix) {
  color: var(--text-primary);
}

:deep(.table-header__search .el-input__prefix) {
  margin-right: 8px;
}

.table-header__search-icon {
  display: block;
  width: 14px;
  height: 14px;
}

:deep(.pagination-row .el-pagination) {
  padding: 0;
  gap: 8px;
}

:deep(.pagination-row .el-pagination__sizes) {
  margin: 0;
}

:deep(.pagination-row .el-pagination__sizes .el-select) {
  width: 155px;
}

:deep(.pagination-row .el-pagination__sizes .el-select__wrapper) {
  min-height: 32px;
  height: 32px;
  padding: 5px 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: none;
}

:deep(.pagination-row .el-pagination button) {
  padding: 0;
  background: transparent;
}

:deep(.table-header__search .el-input__inner) {
  height: 22px;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-primary);
}

:deep(.table-header__search .el-input__inner::placeholder) {
  color: var(--text-placeholder);
}
</style>
