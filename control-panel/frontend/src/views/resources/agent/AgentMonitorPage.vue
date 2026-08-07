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
  ElConfigProvider,
  ElMessage,
} from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import refreshIcon from '@/assets/images/refresh-icon.svg';
import searchIcon from '@/assets/images/search-icon.png';
import funnelIcon from '@/assets/images/funnel-icon.png';
import statusRunningIcon from '@/assets/images/status-running.png';
import statusAbnormalIcon from '@/assets/images/status-abnormal.png';
import statusStoppedIcon from '@/assets/images/status-stopped.png';
import overviewBgIcon from '@/assets/images/overview-bg.png';
import overviewBgRightIcon from '@/assets/images/overview-bg-right.png';
import avatarIcon from '@/assets/images/avatar.svg';
import { fetchInstances, type InstanceEntry } from '@/api/agent';
import { ApiError } from '@/api';

// ── 分页 jumper 文案：去掉默认"前往…页"，后缀改为"…跳转" ──
const agentLocale = {
  ...zhCn,
  el: {
    ...zhCn.el,
    pagination: { ...zhCn.el.pagination, goto: '', pageClassifier: '跳转' },
  },
};

// ── 状态色（对齐 UI 设计稿） ──
const STATUS_CONFIG: Record<string, { label: string; dot: string }> = {
  运行: { label: '运行中', dot: 'var(--success)' },
  异常: { label: '异常', dot: '#FCC800' },
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

// ── 计算属性 ──
const pageSummary = computed(() => `总计：${total.value}`);

const emptyText = computed(() => {
  if (listLoading.value) return '加载中...';
  if (unavailableMsg.value) return unavailableMsg.value;
  if (total.value === 0) return '暂无实例';
  if (instances.value.length === 0 && page.value > totalPages.value) {
    return '当前页无数据，数据可能已更新，请返回第 1 页或刷新';
  }
  return '暂无实例';
});

const sortParam = computed(() =>
  sortField.value && sortOrder.value ? `${sortField.value}:${sortOrder.value}` : '',
);

// ── 方法 ──
function formatUpdateTime() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

async function loadInstances(updateOverview: boolean, refresh = false) {
  if (instancesAbort) {
    instancesAbort.abort();
  }
  const controller = new AbortController();
  instancesAbort = controller;

  listLoading.value = true;
  unavailableMsg.value = '';
  try {
    const data = await fetchInstances(
      {
        page: page.value,
        size: pageSize.value,
        sort: sortParam.value || undefined,
        keyword: keyword.value || undefined,
        // 逗号分隔多选状态，后端 split(",") 逐个匹配，不选=不过滤
        status: filterStatus.value.length > 0 ? filterStatus.value.join(",") : undefined,
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
    if (e instanceof Error && e.message === 'canceled') {
      return;
    }
    if (e instanceof ApiError && e.status) {
      switch (e.status) {
        case 503: unavailableMsg.value = '未接入注册中心'; break;
        case 502:
          unavailableMsg.value = e.message.includes('格式')
            ? '返回数据格式异常'
            : e.message.includes('返回错误')
              ? '注册中心返回错误'
              : '无法连接注册中心';
          break;
        case 504: unavailableMsg.value = '无法连接注册中心'; break;
        default:
          ElMessage.error(e instanceof Error ? e.message : '加载失败');
      }
      if (e.status === 502 || e.status === 503 || e.status === 504) return;
    } else {
      ElMessage.error(e instanceof Error ? e.message : '加载失败');
    }
  } finally {
    if (instancesAbort === controller) {
      listLoading.value = false;
    }
  }
}

function handleRefresh() {
  page.value = 1;
  keyword.value = '';
  sortField.value = '';
  sortOrder.value = '';
  filterFramework.value = '';
  filterStatus.value = [];
  tableRef.value?.clearSort();
  loadInstances(true, true);
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

function formatDate(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// ── 生命周期 ──
onMounted(() => loadInstances(true));
onUnmounted(() => {
  if (instancesAbort) {
    instancesAbort.abort();
  }
});
</script>

<template>
  <section class="page agent-monitor">
    <!-- 操作区 -->
    <div class="agent-monitor__header">
      <h1 class="agent-monitor__title">智能体监控</h1>
      <div class="agent-monitor__header-right">
        <span v-if="lastUpdateTime" class="agent-monitor__update-time">
          更新时间：{{ lastUpdateTime }}
        </span>
        <img
          :src="refreshIcon"
          alt="刷新"
          width="14"
          height="14"
          class="agent-monitor__refresh"
          :class="{ 'agent-monitor__refresh--disabled': listLoading }"
          @click="!listLoading && handleRefresh()"
        />
      </div>
    </div>

    <!-- 概览行 -->
    <div class="overview-row">
      <div class="overview-card">
        <img :src="overviewBgIcon" alt="" class="overview-card__bg" />
        <h2 class="overview-card__title">Agent实例总览</h2>
        <div class="overview-card__body">
          <div class="overview-card__main">
            <span class="overview-card__label">Agent实例数</span>
            <span class="overview-card__big-value">
              {{ firstLoaded ? overviewTotal : '—' }}
              <span class="overview-card__unit">个</span>
            </span>
          </div>
          <div class="overview-card__statuses">
            <div class="overview-card__status">
              <img :src="statusRunningIcon" alt="" class="overview-card__chart" />
              <div class="overview-card__status-info">
                <span class="overview-card__status-label">运行</span>
                <span class="overview-card__status-value" style="color: var(--success)">
                  {{ firstLoaded ? overviewRunning : '—' }}
                </span>
              </div>
            </div>
            <div class="overview-card__status">
              <img :src="statusAbnormalIcon" alt="" class="overview-card__chart" />
              <div class="overview-card__status-info">
                <span class="overview-card__status-label">异常</span>
                <span class="overview-card__status-value" style="color: #FCC800">
                  {{ firstLoaded ? overviewAbnormal : '—' }}
                </span>
              </div>
            </div>
            <div class="overview-card__status">
              <img :src="statusStoppedIcon" alt="" class="overview-card__chart" />
              <div class="overview-card__status-info">
                <span class="overview-card__status-label">停止</span>
                <span class="overview-card__status-value" style="color: var(--text-primary)">
                  {{ firstLoaded ? overviewStopped : '—' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="overview-card overview-card--right">
        <img :src="overviewBgRightIcon" alt="" class="overview-card__bg" />
      </div>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <div class="table-header">
        <h2 class="table-header__title">智能体实例</h2>
        <ElInput
          v-model="keyword"
          class="table-header__search"
          placeholder="请输入搜索内容"
          clearable
          @keyup.enter="onSearchChange"
          @clear="onSearchChange"
        >
          <template #prefix>
            <img :src="searchIcon" alt="" width="14" height="14" />
          </template>
        </ElInput>
      </div>

      <ElTable
        ref="tableRef"
        v-loading="listLoading"
        :data="instances"
        row-key="service_id"
        class="agent-table"
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
                  <ElInput
                    v-model="filterFramework"
                    placeholder="输入框架名"
                    clearable
                    @keyup.enter="onFilterChange"
                  />
                  <div class="filter-popover__actions">
                    <ElButton size="small" @click="resetFrameworkFilter">重置</ElButton>
                    <ElButton size="small" type="primary" @click="onFilterChange">查询</ElButton>
                  </div>
                </div>
              </ElPopover>
            </div>
          </template>
          <template #default="{ row }">
            <span>{{ row.framework }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn prop="status" label="运行状态" min-width="140">
          <template #header>
            <div class="filter-header">
              <span>运行状态</span>
              <ElPopover v-model:visible="statusPopoverVisible" trigger="click" placement="bottom" :width="160" @hide="onStatusFilterClose">
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
            <span>{{ formatDate(row.created_at) }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn
          prop="last_active_at"
          label="最近活跃"
          min-width="203"
          show-overflow-tooltip
          sortable="custom"
          :sort-orders="['ascending', 'descending']"
        >
          <template #default="{ row }">
            <span>{{ formatDate(row.last_active_at) }}</span>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pagination-row">
        <span class="pagination-total">{{ pageSummary }}</span>
        <ElConfigProvider :locale="agentLocale">
          <ElPagination
            v-if="total > 0"
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="sizes, prev, pager, next, jumper"
            background
            @current-change="onPageChange"
            @size-change="onSizeChange"
          />
        </ElConfigProvider>
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
  padding: 24px 16px;
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

.agent-monitor__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.agent-monitor__header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-monitor__update-time {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-secondary);
}

.agent-monitor__refresh {
  cursor: pointer;
  color: var(--text-primary);
  transition: opacity 0.2s;
}

.agent-monitor__refresh:hover {
  opacity: 0.7;
}

.agent-monitor__refresh--disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* ── 概览行 ── */
.overview-row {
  display: flex;
  gap: 20px;
  flex-shrink: 0;
  margin-bottom: 24px;
}

.overview-card {
  flex: 0 1 50%;
  background: var(--bg-2);
  border-radius: var(--radius-lg);
  padding: 32px 40px;
  min-width: 380px;
  position: relative;
}

.overview-card--right {
  flex: 1;
}

.overview-card__bg {
  position: absolute;
  top: 0;
  right: 24px;
  z-index: 0;
  pointer-events: none;
}

.overview-card > *:not(.overview-card__bg) {
  position: relative;
  z-index: 1;
}

.overview-card__title {
  margin: 0 0 24px;
  font-size: 18px;
  font-weight: 500;
  color: var(--text-primary);
}

.overview-card__body {
  display: flex;
  align-items: center;
  gap: 44px;
  flex-wrap: wrap;
}

.overview-card__main {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.overview-card__label {
  font-size: 16px;
  font-weight: 400;
  color: var(--text-primary);
}

.overview-card__big-value {
  font-size: 48px;
  font-weight: 500;
  line-height: 56px;
  color: var(--text-primary);
}

.overview-card__unit {
  font-size: 16px;
  font-weight: 500;
  margin-left: 2px;
}

.overview-card__statuses {
  display: flex;
  gap: 61px;
  flex-wrap: wrap;
}

.overview-card__status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.overview-card__chart {
  width: 47px;
  height: 34px;
  display: block;
}

.overview-card__status-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.overview-card__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.overview-card__status-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.overview-card__status-value {
  font-size: 20px;
  font-weight: 500;
}

/* ── 表格卡 ── */
.table-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 20px 24px 8px;
  background: var(--bg-2);
  border-radius: var(--radius-lg);
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.table-header__title {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  color: var(--text-primary);
}

.table-header__search {
  width: 296px;
}

.agent-table {
  width: 100%;
}

/* ── 列头筛选 ── */
.filter-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
  margin-top: 20px;
  flex-shrink: 0;
  min-height: 32px;
}

.pagination-total {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
}

/* ── 表头样式 ── */
:deep(.agent-table .el-table__header th) {
  color: var(--text-primary);
  font-weight: 500;
  background: rgba(25, 25, 25, 0.05);
  height: 48px;
  padding: 0;
  border-bottom: 1px solid var(--border-separator);
}

:deep(.agent-table .el-table__body td) {
  color: var(--text-primary);
  font-weight: 400;
  height: 48px;
  padding: 0;
  border-bottom: 1px solid var(--border-separator-subtle);
}

:deep(.agent-table .el-table__body tr:hover > td) {
  background: rgba(25, 25, 25, 0.03);
}

:deep(.agent-table .el-table__body td .cell),
:deep(.agent-table .el-table__header th .cell) {
  padding: 0 4px;
  font-size: 15px;
}

/* ── 排序图标 ── */
:deep(.agent-table .caret-wrapper) {
  background-image: url('../../../assets/images/sort-icon.png');
  background-repeat: no-repeat;
  background-position: center;
  background-size: 12px;
  width: 14px;
  height: 14px;
  opacity: 0.4;
  transition: opacity 0.2s;
}

:deep(.agent-table .caret-wrapper .sort-caret) {
  display: none !important;
}

:deep(.agent-table th.ascending .caret-wrapper),
:deep(.agent-table th.descending .caret-wrapper) {
  opacity: 1;
}

:deep(.agent-table .el-table__body td.col-node .cell) {
  padding-left: 16px;
}

:deep(.table-header__search .el-input__wrapper) {
  border-radius: var(--radius-base);
}
</style>
