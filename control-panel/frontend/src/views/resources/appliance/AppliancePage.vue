<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
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
import {
  fetchApplianceMonitor,
  fetchHardwareNodes,
  type ApplianceMonitorData,
  type HardwareNodeSummary,
} from '@/api/appliance';
import cpuIcon from '@/assets/images/cpu.svg';
import npuIcon from '@/assets/images/npu.svg';
import memoryIcon from '@/assets/images/memory.svg';
import diskIcon from '@/assets/images/disk.svg';
import networkIcon from '@/assets/images/network.svg';
import deviceImage from '@/assets/images/device.png';
import {
  formatBytes,
  formatBytesPerSecParts,
  formatHbmGigabytes,
  formatUsagePercent,
  getNpuHealthMeta,
  listDiskMounts,
  listNpuDevices,
  mapApplianceMonitorToView,
  type ApplianceMonitorViewModel,
} from './utils/monitor';

const POLL_INTERVAL_MS = 30_000;

const route = useRoute();
const router = useRouter();

const nodesLoading = ref(false);
const listRefreshing = ref(false);
const nodesError = ref('');
const nodes = ref<HardwareNodeSummary[]>([]);

const loading = ref(false);
const refreshing = ref(false);
const error = ref('');
const nodeId = computed(() => String(route.params.node ?? route.query.node ?? ''));
const nodeOffline = ref(false);
const nodeOfflineError = ref<string | null>(null);
const monitorData = ref<ApplianceMonitorData | null>(null);
const viewModel = ref<ApplianceMonitorViewModel | null>(null);
const npuDetailVisible = ref(false);
const diskDetailVisible = ref(false);

let pollTimer: ReturnType<typeof setTimeout> | undefined;
let loadRequestSeq = 0;
let nodesRequestSeq = 0;

const MASTER_NODE_ID = 'master';

function getNodeItemId(item: HardwareNodeSummary): string {
  return item.id || MASTER_NODE_ID;
}

function resolveDefaultNode(items: HardwareNodeSummary[]): string {
  const master = items.find((item) => getNodeItemId(item) === MASTER_NODE_ID);
  if (master) {
    return MASTER_NODE_ID;
  }
  return items[0] ? getNodeItemId(items[0]) : MASTER_NODE_ID;
}

function applianceNodePath(node: string): string {
  return `/resources/appliance/${encodeURIComponent(node)}`;
}

async function loadNodes(isRefresh = false) {
  const requestSeq = ++nodesRequestSeq;

  if (isRefresh) {
    listRefreshing.value = true;
  } else {
    nodesLoading.value = true;
  }
  if (!isRefresh) {
    nodesError.value = '';
  }

  try {
    const data = await fetchHardwareNodes();
    if (requestSeq !== nodesRequestSeq) {
      return;
    }
    nodes.value = data.nodes;
    await ensureDefaultNodeSelection(data.nodes);
  } catch (e) {
    if (requestSeq !== nodesRequestSeq) {
      return;
    }
    nodesError.value = e instanceof Error ? e.message : '加载节点列表失败';
  } finally {
    if (requestSeq !== nodesRequestSeq) {
      return;
    }
    nodesLoading.value = false;
    listRefreshing.value = false;
  }
}

async function selectNode(node: string, replace = false) {
  if (!node) {
    return;
  }
  if (node === nodeId.value) {
    void loadMonitor(false, node);
    return;
  }
  const location = { path: applianceNodePath(node) };
  if (replace) {
    await router.replace(location);
  } else {
    await router.push(location);
  }
}

async function ensureDefaultNodeSelection(items: HardwareNodeSummary[]) {
  if (nodeId.value || items.length === 0) {
    return;
  }
  const defaultNodeId = resolveDefaultNode(items);
  await selectNode(defaultNodeId, true);
  if (!nodeId.value) {
    await loadMonitor(false, defaultNodeId);
  }
}

const npuDevices = computed(() => (monitorData.value ? listNpuDevices(monitorData.value) : []));
const diskMounts = computed(() => (monitorData.value ? listDiskMounts(monitorData.value) : []));
const selectedNode = computed(() =>
  nodes.value.find((item) => getNodeItemId(item) === nodeId.value),
);
const deviceDisplayName = computed(
  () => viewModel.value?.deviceName ?? selectedNode.value?.host ?? nodeId.value ?? '—',
);
const deviceHeadTags = computed(() => {
  const node = selectedNode.value;
  const vm = viewModel.value;
  return [
    { label: '型号', value: vm?.modelName ?? node?.product_name ?? '—' },
    { label: 'IP地址', value: node?.host ?? '—' },
    { label: '运行时长', value: vm?.uptimeText ?? '—' },
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

async function loadMonitor(isRefresh = false, targetNodeId?: string) {
  const activeNodeId = targetNodeId ?? nodeId.value;
  if (!activeNodeId) {
    return;
  }

  const requestSeq = ++loadRequestSeq;

  if (isRefresh) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  error.value = '';

  try {
    const data = await fetchApplianceMonitor(activeNodeId);
    if (requestSeq !== loadRequestSeq) {
      return;
    }

    nodeOffline.value = data.status === 'offline';
    nodeOfflineError.value = data.error;

    if (data.status === 'offline' || !data.snapshot) {
      monitorData.value = null;
      viewModel.value = null;
      return;
    }

    monitorData.value = data.snapshot;
    viewModel.value = mapApplianceMonitorToView(data.snapshot);
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

function handleListRefresh() {
  void loadNodes(true);
}

function handleDetailRefresh() {
  restartPollTimer();
  void loadMonitor(true);
}

async function pollApplianceData() {
  await Promise.all([loadNodes(true), nodeId.value ? loadMonitor(true) : Promise.resolve()]);
}

onMounted(() => {
  void loadNodes().finally(() => {
    restartPollTimer();
  });
});

function restartPollTimer() {
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer);
  }
  pollTimer = setTimeout(() => {
    void pollApplianceData().finally(() => {
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

watch(
  nodeId,
  (id, previousId) => {
    if (!id) {
      loadRequestSeq += 1;
      monitorData.value = null;
      viewModel.value = null;
      nodeOffline.value = false;
      nodeOfflineError.value = null;
      return;
    }
    if (id === previousId) {
      return;
    }
    loadRequestSeq += 1;
    monitorData.value = null;
    viewModel.value = null;
    nodeOffline.value = false;
    nodeOfflineError.value = null;
    void loadMonitor(false, id).finally(() => {
      restartPollTimer();
    });
  },
  { immediate: true },
);

onUnmounted(() => {
  loadRequestSeq += 1;
  nodesRequestSeq += 1;
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
          aria-label="刷新详情"
          class="appliance-page__refresh-btn"
          @click="handleDetailRefresh"
        />
      </div>
    </header>

    <div class="appliance-page__layout">
      <aside class="appliance-page__sidebar">
        <div class="appliance-page__sidebar-head">
          <ElText type="info" size="small">节点列表</ElText>
          <ElButton
            text
            :loading="listRefreshing"
            :icon="RefreshRight"
            aria-label="刷新节点列表"
            class="appliance-page__sidebar-refresh"
            @click="handleListRefresh"
          />
        </div>

        <ElAlert
          v-if="nodesError"
          :title="nodesError"
          type="error"
          show-icon
          :closable="false"
          class="appliance-page__alert"
        />
        <ElSkeleton v-if="nodesLoading" :rows="4" animated />

        <div v-else class="appliance-page__node-list">
          <button
            v-for="item in nodes"
            :key="item.id"
            type="button"
            class="appliance-node"
            :class="{
              'appliance-node--active': getNodeItemId(item) === nodeId,
              'appliance-node--offline': item.status === 'offline',
            }"
            @click="selectNode(getNodeItemId(item))"
          >
            <span class="appliance-node__role">{{ item.role }}</span>
            <span class="appliance-node__host">{{ item.host }}</span>
            <span class="appliance-node__model">{{ item.product_name || '—' }}</span>
            <span
              class="appliance-node__status"
              :class="item.status === 'online' ? 'is-online' : 'is-offline'"
            >
              {{ item.status === 'online' ? '在线' : '离线' }}
            </span>
          </button>
        </div>
      </aside>

      <main class="appliance-page__main">
        <ElAlert v-if="error" :title="error" type="error" show-icon :closable="false" class="appliance-page__alert" />
        <ElAlert
          v-else-if="nodeOffline"
          :title="nodeOfflineError ?? '节点不可达'"
          type="warning"
          show-icon
          :closable="false"
          class="appliance-page__alert"
        />
        <ElSkeleton v-if="loading" :rows="10" animated />

        <template v-else-if="nodeId">
      <div class="appliance-page__body">
        <div class="appliance-page__visual">
          <div class="appliance-page__device-head">
            <h2 class="appliance-page__device-name">{{ deviceDisplayName }}</h2>
            <ElSpace wrap :size="12">
              <ElTag v-for="tag in deviceHeadTags" :key="tag.label" round effect="plain" class="appliance-page__tag">
                <span class="appliance-page__tag-label">{{ tag.label }}</span>
                <span class="appliance-page__tag-value">{{ tag.value }}</span>
              </ElTag>
            </ElSpace>
          </div>
          <div v-if="viewModel" class="appliance-page__device-image" aria-hidden="true">
            <img :src="deviceImage" alt="" class="appliance-page__device-photo" />
          </div>
        </div>
        <aside v-if="viewModel" class="appliance-page__metrics">
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
        <div v-else class="appliance-page__metrics appliance-page__metrics--empty">
          <ElText type="info">暂无硬件监控数据</ElText>
        </div>
      </div>
      <template v-if="viewModel">
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
          <ElTableColumn label="AI Core 利用率" min-width="148">
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
                    {{ `${formatHbmGigabytes(row.hbm_used_mb)}/${formatHbmGigabytes(row.hbm_total_mb)}` }}
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
        </template>

        <div v-else-if="!nodesLoading" class="appliance-page__empty">
          <ElText type="info">请选择节点查看硬件详情</ElText>
        </div>
      </main>
    </div>
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

.appliance-page__layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.appliance-page__sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: var(--bg-1);
}

.appliance-page__sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.appliance-page__sidebar-refresh {
  padding: 0;
  width: 14px;
  height: 22px;
}

.appliance-page__node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.appliance-node {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-2);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.appliance-node:hover {
  border-color: var(--color-primary);
}

.appliance-node--active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary);
}

.appliance-node--offline {
  opacity: 0.85;
}

.appliance-node__role {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.appliance-node__host {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

.appliance-node__model {
  font-size: 13px;
  line-height: 20px;
  color: var(--text-secondary);
}

.appliance-node__status {
  font-size: 12px;
  line-height: 18px;
}

.appliance-node__status.is-online {
  color: var(--success);
}

.appliance-node__status.is-offline {
  color: var(--text-secondary);
}

.appliance-page__main {
  min-width: 0;
}

.appliance-page__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.appliance-page__header-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.appliance-page__back-btn {
  padding: 0;
  flex-shrink: 0;
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

.appliance-page__metrics--empty {
  align-items: center;
  justify-content: center;
  min-height: 240px;
  border-radius: 24px;
  background: var(--el-fill-color-blank);
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

@media (max-width: 1200px) {
  .appliance-page__layout {
    grid-template-columns: 1fr;
  }
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
