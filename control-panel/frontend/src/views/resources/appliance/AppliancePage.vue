<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import {
  ElAlert,
  ElButton,
  ElCard,
  ElDialog,
  ElProgress,
  ElSkeleton,
  ElSpace,
  ElTable,
  ElTableColumn,
  ElTag,
  ElText,
} from 'element-plus';
import { Bottom, RefreshRight, Top } from '@element-plus/icons-vue';
import { fetchApplianceMonitor, type ApplianceMonitorData } from '@/api/appliance';
import cpuIcon from '@/assets/images/cpu.svg';
import npuIcon from '@/assets/images/npu.svg';
import memoryIcon from '@/assets/images/memory.svg';
import diskIcon from '@/assets/images/disk.svg';
import networkIcon from '@/assets/images/network.svg';
import deviceImage from '@/assets/images/device.png';
import {
  formatBytes,
  formatBytesPerSecParts,
  formatMegabytes,
  formatUsagePercent,
  getNpuHealthMeta,
  listDiskMounts,
  listNpuDevices,
  mapApplianceMonitorToView,
  type ApplianceMonitorViewModel,
} from './utils/monitor';

const POLL_INTERVAL_MS = 30_000;

const loading = ref(false);
const refreshing = ref(false);
const error = ref('');
const monitorData = ref<ApplianceMonitorData | null>(null);
const viewModel = ref<ApplianceMonitorViewModel | null>(null);
const npuDetailVisible = ref(false);
const diskDetailVisible = ref(false);

let pollTimer: ReturnType<typeof setTimeout> | undefined;
let loadRequestSeq = 0;

const npuDevices = computed(() => (monitorData.value ? listNpuDevices(monitorData.value) : []));
const diskMounts = computed(() => (monitorData.value ? listDiskMounts(monitorData.value) : []));
const infoTags = computed(() => {
  if (!viewModel.value) {
    return [];
  }
  return [
    { label: '型号', value: viewModel.value.modelName },
    { label: '运行时长', value: viewModel.value.uptimeText },
  ];
});
const usageCards = computed(() => {
  if (!viewModel.value) {
    return [];
  }
  const vm = viewModel.value;
  return [
    {
      key: 'cpu',
      title: 'CPU利用率',
      icon: cpuIcon,
      percent: vm.cpuUsage,
      showUsage: false,
    },
    {
      key: 'npu',
      title: 'NPU利用率',
      icon: npuIcon,
      percent: vm.npuUsage,
      showUsage: false,
      showDetail: true,
      detailKey: 'npu',
    },
    {
      key: 'memory',
      title: '内存利用率',
      icon: memoryIcon,
      percent: vm.memoryUsage,
      showUsage: true,
      usedText: vm.memoryUsedText,
      totalText: vm.memoryTotalText,
    },
    {
      key: 'disk',
      title: '磁盘利用率',
      icon: diskIcon,
      percent: vm.diskUsage,
      showUsage: true,
      usedText: vm.diskUsedText,
      totalText: vm.diskTotalText,
      showDetail: true,
      detailKey: 'disk',
    },
  ];
});

async function loadMonitor(isRefresh = false) {
  const requestSeq = ++loadRequestSeq;

  if (isRefresh) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  error.value = '';

  try {
    const data = await fetchApplianceMonitor();
    if (requestSeq !== loadRequestSeq) {
      return;
    }
    monitorData.value = data;
    viewModel.value = mapApplianceMonitorToView(data);
  } catch (e) {
    if (requestSeq !== loadRequestSeq) {
      return;
    }
    error.value = e instanceof Error ? e.message : '加载一体机监控数据失败';
  } finally {
    if (requestSeq !== loadRequestSeq) {
      return;
    }
    loading.value = false;
    refreshing.value = false;
  }
}

function restartPollTimer() {
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer);
  }
  pollTimer = setTimeout(() => {
    void loadMonitor(true).finally(() => {
      restartPollTimer();
    });
  }, POLL_INTERVAL_MS);
}

function openMetricDetail(key: string) {
  if (key === 'npu') {
    npuDetailVisible.value = true;
    return;
  }
  if (key === 'disk') {
    diskDetailVisible.value = true;
  }
}

function handleRefresh() {
  restartPollTimer();
  void loadMonitor(true);
}

onMounted(() => {
  void loadMonitor().finally(() => {
    restartPollTimer();
  });
});

onUnmounted(() => {
  loadRequestSeq += 1;
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer);
  }
});
</script>

<template>
  <section class="appliance-page">
    <header class="appliance-page__header">
      <h1 class="appliance-page__title">一体机监控</h1>
      <div class="appliance-page__header-actions">
        <ElText type="info" class="appliance-page__updated"> 更新时间：{{ viewModel?.updatedAt ?? '—' }} </ElText>
        <ElButton
          text
          :loading="refreshing"
          :icon="RefreshRight"
          aria-label="刷新"
          class="appliance-page__refresh-btn"
          @click="handleRefresh"
        />
      </div>
    </header>

    <ElAlert v-if="error" :title="error" type="error" show-icon :closable="false" class="appliance-page__alert" />
    <ElSkeleton v-if="loading" :rows="10" animated />

    <template v-else-if="viewModel">
      <div class="appliance-page__body">
        <div class="appliance-page__visual">
          <div class="appliance-page__device-head">
            <h2 class="appliance-page__device-name">{{ viewModel.deviceName }}</h2>
            <ElSpace wrap :size="12">
              <ElTag v-for="tag in infoTags" :key="tag.label" round effect="plain" class="appliance-page__tag">
                <span class="appliance-page__tag-label">{{ tag.label }}</span>
                <span class="appliance-page__tag-value">{{ tag.value }}</span>
              </ElTag>
            </ElSpace>
          </div>
          <div class="appliance-page__device-image" aria-hidden="true">
            <img :src="deviceImage" alt="" class="appliance-page__device-photo" />
          </div>
        </div>
        <aside class="appliance-page__metrics">
          <ElCard v-for="card in usageCards" :key="card.key" shadow="never" class="metric-card">
            <div class="metric-card__header">
              <img :src="card.icon" alt="" class="metric-card__icon" width="48" height="48" />
              <h3 class="metric-card__title">{{ card.title }}</h3>
              <ElButton
                v-if="card.showDetail"
                type="primary"
                link
                class="metric-card__detail-btn"
                @click="openMetricDetail(card.detailKey!)"
              >
                查看详情
              </ElButton>
            </div>
            <div class="metric-card__body" :class="{ 'metric-card__body--usage': card.showUsage }">
              <div class="metric-card__value">
                <span class="metric-card__number">{{ formatUsagePercent(card.percent) }}</span>
                <span class="metric-card__unit">%</span>
              </div>
              <div class="metric-card__progress-wrap">
                <div v-if="card.showUsage" class="metric-card__usage-row">
                  <ElText type="info" size="small">当前使用量</ElText>
                  <ElText size="small">{{ card.usedText }}/{{ card.totalText }}</ElText>
                </div>
                <ElProgress
                  :percentage="card.percent"
                  :show-text="false"
                  :stroke-width="14"
                  class="metric-card__progress"
                />
              </div>
            </div>
          </ElCard>
          <ElCard shadow="never" class="metric-card">
            <div class="metric-card__header">
              <img :src="networkIcon" alt="" class="metric-card__icon" width="48" height="48" />
              <h3 class="metric-card__title">网络</h3>
            </div>
            <div class="metric-card__body metric-card__body--network">
              <div class="network-stats">
                <div class="network-stat">
                  <ElButton circle :icon="Top" class="network-stat__icon" aria-label="上行" />
                  <span class="network-stat__number">{{ formatBytesPerSecParts(viewModel.networkTxBytesPerSec).value }}</span>
                  <span class="network-stat__unit">{{ formatBytesPerSecParts(viewModel.networkTxBytesPerSec).unit }}</span>
                </div>
                <span class="network-stat__divider" aria-hidden="true" />
                <div class="network-stat">
                  <ElButton circle :icon="Bottom" class="network-stat__icon" aria-label="下行" />
                  <span class="network-stat__number">{{ formatBytesPerSecParts(viewModel.networkRxBytesPerSec).value }}</span>
                  <span class="network-stat__unit">{{ formatBytesPerSecParts(viewModel.networkRxBytesPerSec).unit }}</span>
                </div>
              </div>
            </div>
          </ElCard>
        </aside>
      </div>
      <ElDialog v-model="npuDetailVisible" title="NPU 卡详情" width="720px" destroy-on-close class="npu-detail-dialog">
        <div v-if="npuDevices.length === 0" class="metric-detail-empty">
          <ElText type="info">暂无 NPU 卡数据</ElText>
        </div>
        <ElTable v-else :data="npuDevices" max-height="420" class="metric-detail-table" row-key="device_id">
          <ElTableColumn label="卡号" width="64" fixed>
            <template #default="{ row }">
              <span class="metric-detail-table__primary">{{ row.device_id }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="健康状态" width="88" align="center">
            <template #default="{ row }">
              <ElTag size="small" effect="light" class="health-tag" :class="getNpuHealthMeta(row.health).tagClass">
                {{ getNpuHealthMeta(row.health).text }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="利用率" min-width="148">
            <template #default="{ row }">
              <div class="metric-detail-table__metric">
                <div class="metric-detail-table__metric-head">
                  <span class="metric-detail-table__metric-value">{{ formatUsagePercent(row.usage) }}%</span>
                </div>
                <ElProgress
                  :percentage="row.usage"
                  :show-text="false"
                  :stroke-width="4"
                  class="metric-detail-table__progress"
                />
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="HBM" min-width="168">
            <template #default="{ row }">
              <div class="metric-detail-table__metric">
                <div class="metric-detail-table__metric-head">
                  <span class="metric-detail-table__metric-value">{{ formatUsagePercent(row.hbm_usage) }}%</span>
                  <span class="metric-detail-table__metric-sub">
                    {{ `${formatMegabytes(row.hbm_used_mb)}/${formatMegabytes(row.hbm_total_mb)}` }}
                  </span>
                </div>
                <ElProgress
                  :percentage="row.hbm_usage"
                  :show-text="false"
                  :stroke-width="4"
                  class="metric-detail-table__progress"
                />
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="温度" width="80" align="right">
            <template #default="{ row }">
              <span class="metric-detail-table__plain">{{ `${row.temperature}°C` }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="功耗" width="88" align="right">
            <template #default="{ row }">
              <span class="metric-detail-table__plain">{{ `${row.power_watts.toFixed(1)}W` }}</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </ElDialog>
      <ElDialog v-model="diskDetailVisible" title="磁盘详情" width="720px" destroy-on-close class="disk-detail-dialog">
        <div v-if="diskMounts.length === 0" class="metric-detail-empty">
          <ElText type="info">暂无磁盘数据</ElText>
        </div>
        <ElTable v-else :data="diskMounts" max-height="420" class="metric-detail-table" row-key="mount_point">
          <ElTableColumn label="挂载点" min-width="96" fixed>
            <template #default="{ row }">
              <span class="metric-detail-table__primary">{{ row.mount_point }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="设备" min-width="112" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="metric-detail-table__plain">{{ row.device || '—' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="文件系统" width="96">
            <template #default="{ row }">
              <span class="metric-detail-table__plain">{{ row.fstype || '—' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="利用率" min-width="148">
            <template #default="{ row }">
              <div class="metric-detail-table__metric">
                <div class="metric-detail-table__metric-head">
                  <span class="metric-detail-table__metric-value">{{ formatUsagePercent(row.usage) }}%</span>
                  <span class="metric-detail-table__metric-sub">
                    {{ `${formatBytes(row.used_bytes)}/${formatBytes(row.total_bytes)}` }}
                  </span>
                </div>
                <ElProgress
                  :percentage="row.usage"
                  :show-text="false"
                  :stroke-width="4"
                  class="metric-detail-table__progress"
                />
              </div>
            </template>
          </ElTableColumn>
        </ElTable>
      </ElDialog>
    </template>
  </section>
</template>

<style scoped>
.appliance-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px 32px 32px;
  min-height: 100%;
  box-sizing: border-box;
}

.appliance-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.appliance-page__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.appliance-page__updated {
  font-size: 14px;
  line-height: 22px;
}

.appliance-page__header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 22px;
}

.appliance-page__refresh-btn {
  padding: 0;
  margin: 0;
  width: 14px;
  height: 22px;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
}

.appliance-page__refresh-btn :deep(.el-icon) {
  width: 14px;
  height: 14px;
  font-size: 14px;
}

.appliance-page__alert {
  margin: 0;
}

.appliance-page__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 530px;
  gap: 32px;
  align-items: start;
}

.appliance-page__visual {
  position: relative;
  min-height: 916px;
}

.appliance-page__device-head {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 720px;
}

.appliance-page__device-name {
  margin: 0;
  font-size: 32px;
  font-weight: 500;
  line-height: 40px;
  color: var(--text-primary);
}

.appliance-page__tag {
  height: 38px;
  padding: 0 16px;
  border: none;
  background: var(--bg-2);
}

.appliance-page__tag :deep(.el-tag__content) {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.appliance-page__tag-label {
  color: var(--text-secondary);
}

.appliance-page__tag-value {
  color: var(--text-primary);
}

.appliance-page__device-image {
  position: absolute;
  inset: 54px 0 0 109px;
  pointer-events: none;
}

.appliance-page__device-photo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
}

.appliance-page__metrics {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.metric-card {
  border-radius: 24px;
  border: none;
}

.metric-card :deep(.el-card__body) {
  padding: 16px 24px 20px;
}

.metric-card__header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}

.metric-card__icon {
  flex-shrink: 0;
}

.metric-card__title {
  margin: 0;
  flex: 1;
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: var(--text-primary);
}

.metric-card__detail-btn {
  flex-shrink: 0;
  padding: 0;
  height: auto;
  font-size: 14px;
  line-height: 22px;
}

.metric-card__body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.metric-card__body--usage {
  align-items: flex-start;
}

.metric-card__body--network {
  align-items: flex-end;
}

.metric-card__value {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.metric-card__number {
  font-size: 48px;
  font-weight: 500;
  line-height: 56px;
  color: var(--text-primary);
}

.metric-card__unit {
  margin-bottom: 11px;
  font-size: 28px;
  font-weight: 500;
  line-height: 36px;
  color: var(--text-secondary);
}

.metric-card__progress-wrap {
  flex: 1;
  min-width: 0;
  max-width: 320px;
}

.metric-card__usage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.metric-card__progress :deep(.el-progress-bar__outer) {
  border-radius: 100px;
  background: var(--bg-1);
}

.metric-card__progress :deep(.el-progress-bar__inner) {
  border-radius: 100px;
  background: linear-gradient(90deg, rgba(107, 152, 240, 1) 0%, rgba(140, 175, 244, 1) 100%);
}

.network-stats {
  display: flex;
  align-items: flex-end;
  gap: 18px;
}

.network-stat {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.network-stat__divider {
  flex-shrink: 0;
  align-self: flex-end;
  width: 1px;
  height: 24px;
  margin-bottom: 16px;
  background: var(--border);
}

.network-stat__icon {
  margin-bottom: 12px;
  border: none;
  background: var(--bg-active);
  color: var(--color-primary);
}

.network-stat__number {
  font-size: 48px;
  font-weight: 500;
  line-height: 56px;
  color: var(--text-primary);
}

.network-stat__unit {
  margin-bottom: 11px;
  font-size: 28px;
  line-height: 36px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.metric-detail-empty {
  padding: 24px 0;
  text-align: center;
}

.metric-detail-table :deep(.el-table__cell) {
  padding: 10px 0;
}

.metric-detail-table :deep(.el-table__header .el-table__cell) {
  padding: 8px 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
}

.metric-detail-table :deep(.el-table__row) {
  font-size: 13px;
}

.metric-detail-table__primary {
  font-weight: 500;
  color: var(--text-primary);
}

.metric-detail-table__metric {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding-right: 12px;
}

.metric-detail-table__metric-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.metric-detail-table__metric-value {
  flex-shrink: 0;
  font-weight: 500;
  color: var(--text-primary);
}

.metric-detail-table__metric-sub {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 18px;
  color: var(--text-secondary);
}

.metric-detail-table__plain {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.metric-detail-table__progress :deep(.el-progress-bar__outer) {
  border-radius: 100px;
  background: var(--bg-1);
}

.metric-detail-table__progress :deep(.el-progress-bar__inner) {
  border-radius: 100px;
  background: linear-gradient(90deg, rgba(107, 152, 240, 1) 0%, rgba(140, 175, 244, 1) 100%);
}

.health-tag {
  border: none !important;
}

.health-tag--healthy {
  color: var(--tag-text-success) !important;
  background: var(--tag-bg-success) !important;
}

.health-tag--unhealthy {
  color: var(--tag-text-error) !important;
  background: var(--tag-bg-error) !important;
}

.health-tag--unknown {
  color: var(--tag-text-info) !important;
  background: var(--tag-bg-info) !important;
}

@media (max-width: 1400px) {
  .appliance-page__body {
    grid-template-columns: 1fr;
  }

  .appliance-page__visual {
    min-height: 520px;
  }

  .appliance-page__device-image {
    position: relative;
    inset: auto;
    margin-top: 24px;
    min-height: 360px;
  }
}

@media (max-width: 768px) {
  .appliance-page {
    padding: 16px;
  }

  .appliance-page__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .metric-card__body {
    flex-direction: column;
    align-items: stretch;
  }

  .metric-card__progress-wrap {
    max-width: none;
  }
}
</style>
