<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElProgress,
  ElSkeleton,
  ElTable,
  ElTableColumn,
  ElTag,
  ElText,
} from 'element-plus';
import { RefreshRight } from '@element-plus/icons-vue';
import {
  fetchApplianceMonitor,
  fetchHardwareNodes,
  type ApplianceMonitorData,
  type HardwareNodeSummary,
} from '@/api/appliance';
import { usePolling } from '@/composables/usePolling';
import cpuIcon from '@/assets/images/cpu.svg';
import npuIcon from '@/assets/images/npu.svg';
import memoryIcon from '@/assets/images/memory.svg';
import diskIcon from '@/assets/images/disk.svg';
import networkIcon from '@/assets/images/network.svg';
import networkWaveIcon from '@/assets/images/network-wave.svg';
import originalViewIcon from '@/assets/images/box.svg';
import translucentViewIcon from '@/assets/images/briefcase.svg';
import explodedViewIcon from '@/assets/images/boom.svg';
import checkmarkIcon from '@/assets/images/checkmark.svg';
import arrowDownIcon from '@/assets/images/arrow-down.svg';
import arrowUpIcon from '@/assets/images/arrow-up.svg';
import applianceBackground from '@/assets/images/appliance-background.svg';
import originalDeviceImage from '@/assets/images/original-device.svg';
import translucentDeviceImage from '@/assets/images/half-opacity-device.png';
import explodedDeviceImage from '@/assets/images/boom-device.svg';
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
const RING_RADIUS = 34;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

type DeviceViewMode = 'original' | 'translucent' | 'exploded';

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
const nodeMenuOpen = ref(false);
const npuDetailVisible = ref(false);
const diskDetailVisible = ref(false);
const deviceView = ref<DeviceViewMode>('original');
const visualRef = ref<HTMLElement | null>(null);
const devicePhotoRef = ref<HTMLImageElement | null>(null);
const deviceFrame = ref({ left: 0, top: 0, width: 0, height: 0 });

const pollTask = () => pollApplianceData();
const { restart: restartPollTimer, stop: stopPollTimer } = usePolling(POLL_INTERVAL_MS);
let deviceFrameObserver: ResizeObserver | undefined;
let loadRequestSeq = 0;
let nodesRequestSeq = 0;

const MASTER_NODE_ID = 'master';

const DEVICE_VIEWS: { key: DeviceViewMode; label: string; icon: string; image: string }[] = [
  { key: 'original', label: '原始视图', icon: originalViewIcon, image: originalDeviceImage },
  { key: 'translucent', label: '半透视图', icon: translucentViewIcon, image: translucentDeviceImage },
  { key: 'exploded', label: '爆炸视图', icon: explodedViewIcon, image: explodedDeviceImage },
];

const currentDeviceImage = computed(
  () => DEVICE_VIEWS.find((item) => item.key === deviceView.value)?.image ?? originalDeviceImage,
);

const deviceFrameStyle = computed(() => ({
  left: `${deviceFrame.value.left}px`,
  top: `${deviceFrame.value.top}px`,
  width: `${deviceFrame.value.width}px`,
  height: `${deviceFrame.value.height}px`,
}));

const watermarkStyle = computed(() => ({
  left: `${deviceFrame.value.left + deviceFrame.value.width / 2}px`,
  top: `${deviceFrame.value.top + deviceFrame.value.height * 0.08}px`,
}));

function syncDeviceFrame() {
  const visual = visualRef.value;
  const img = devicePhotoRef.value;
  if (!visual || !img) {
    return;
  }
  const visualRect = visual.getBoundingClientRect();
  const imageRect = img.getBoundingClientRect();
  deviceFrame.value = {
    left: imageRect.left - visualRect.left,
    top: imageRect.top - visualRect.top,
    width: imageRect.width,
    height: imageRect.height,
  };
}

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
const selectedNode = computed(() => nodes.value.find((item) => getNodeItemId(item) === nodeId.value));
const isNodeOnline = computed(() => {
  if (nodeOffline.value) {
    return false;
  }
  if (selectedNode.value) {
    return selectedNode.value.status === 'online';
  }
  return Boolean(viewModel.value);
});
const modelName = computed(() => viewModel.value?.modelName ?? selectedNode.value?.product_name ?? '—');
const ipAddress = computed(() => selectedNode.value?.host ?? '—');
const uptimeText = computed(() => viewModel.value?.uptimeText ?? '—');
const networkTx = computed(() => formatBytesPerSecParts(viewModel.value?.networkTxBytesPerSec ?? 0));
const networkRx = computed(() => formatBytesPerSecParts(viewModel.value?.networkRxBytesPerSec ?? 0));
const usageCards = computed(() => {
  if (!viewModel.value) {
    return [];
  }
  const vm = viewModel.value;
  return [
    {
      key: 'cpu',
      title: 'CPU',
      icon: cpuIcon,
      percent: vm.cpuUsage,
      subtitle: '平均CPU利用率',
      color: '#0a59f7',
    },
    {
      key: 'npu',
      title: 'NPU',
      icon: npuIcon,
      percent: vm.npuUsage,
      subtitle: '平均NPU利用率',
      color: '#61cfbe',
      showDetail: true,
      detailKey: 'npu',
    },
    {
      key: 'memory',
      title: '内存',
      icon: memoryIcon,
      percent: vm.memoryUsage,
      subtitle: `${vm.memoryUsedText} / ${vm.memoryTotalText}`,
      capacity: vm.memoryCapacity,
      color: '#46b1e3',
    },
    {
      key: 'disk',
      title: '磁盘',
      icon: diskIcon,
      percent: vm.diskUsage,
      subtitle: `${vm.diskUsedText} / ${vm.diskTotalText}`,
      capacity: vm.diskCapacity,
      color: '#ac49f5',
      showDetail: true,
      detailKey: 'disk',
    },
  ];
});

function ringDashOffset(percent: number): number {
  const clamped = Math.min(100, Math.max(0, percent));
  return RING_CIRCUMFERENCE * (1 - clamped / 100);
}

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

function handleDetailRefresh() {
  restartPollTimer(pollTask);
  void pollApplianceData();
}

async function pollApplianceData() {
  await Promise.all([loadNodes(true), nodeId.value ? loadMonitor(true) : Promise.resolve()]);
}

function observeDeviceFrame() {
  deviceFrameObserver?.disconnect();
  if (typeof ResizeObserver === 'undefined') {
    return;
  }
  deviceFrameObserver = new ResizeObserver(() => {
    syncDeviceFrame();
  });
  if (visualRef.value) {
    deviceFrameObserver.observe(visualRef.value);
  }
  if (devicePhotoRef.value) {
    deviceFrameObserver.observe(devicePhotoRef.value);
  }
  syncDeviceFrame();
}

onMounted(() => {
  void loadNodes().finally(() => {
    restartPollTimer(pollTask);
  });
  window.addEventListener('resize', syncDeviceFrame);
});

function openMetricDetail(key?: string) {
  if (key === 'npu') {
    npuDetailVisible.value = true;
    return;
  }
  if (key === 'disk') {
    diskDetailVisible.value = true;
  }
}

function handleNodeCommand(id: string) {
  void selectNode(id);
}

function handleNodeMenuVisible(visible: boolean) {
  nodeMenuOpen.value = visible;
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
      restartPollTimer(pollTask);
    });
  },
  { immediate: true },
);

watch(visualRef, (el) => {
  if (!el) {
    return;
  }
  void nextTick(() => {
    observeDeviceFrame();
  });
});

watch(deviceView, () => {
  void nextTick(() => {
    syncDeviceFrame();
  });
});

onUnmounted(() => {
  loadRequestSeq += 1;
  nodesRequestSeq += 1;
  stopPollTimer();
  deviceFrameObserver?.disconnect();
  window.removeEventListener('resize', syncDeviceFrame);
});
</script>

<template>
  <section class="appliance-page">
    <div class="appliance-page__bg" aria-hidden="true" :style="{ backgroundImage: `url(${applianceBackground})` }" />
    <header class="appliance-page__header">
      <div class="appliance-page__identity">
        <ElDropdown
          v-if="nodes.length > 0"
          trigger="click"
          @command="handleNodeCommand"
          @visible-change="handleNodeMenuVisible"
        >
          <button type="button" class="appliance-page__name-btn">
            <span class="appliance-page__device-name">{{ nodeId || '—' }}</span>
            <img
              :src="nodeMenuOpen ? arrowUpIcon : arrowDownIcon"
              alt=""
              class="appliance-page__caret"
              width="16"
              height="16"
              aria-hidden="true"
            />
          </button>
          <template #dropdown>
            <ElDropdownMenu class="appliance-node-menu">
              <ElDropdownItem
                v-for="item in nodes"
                :key="item.id"
                :command="getNodeItemId(item)"
                :class="{ 'is-node-active': getNodeItemId(item) === nodeId }"
              >
                <span class="appliance-node-menu__id">{{ getNodeItemId(item) }}</span>
                <img
                  v-if="getNodeItemId(item) === nodeId"
                  :src="checkmarkIcon"
                  alt=""
                  class="appliance-node-menu__check"
                  width="16"
                  height="16"
                />
              </ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>
        <h1 v-else class="appliance-page__device-name">{{ nodeId || '一体机监控' }}</h1>
        <span v-if="nodeId" class="appliance-page__online" :class="isNodeOnline ? 'is-online' : 'is-offline'">
          <i class="appliance-page__online-dot" aria-hidden="true" />
          {{ isNodeOnline ? '在线' : '离线' }}
        </span>
      </div>
      <div class="appliance-page__header-actions">
        <span class="appliance-page__updated">更新时间：{{ viewModel?.updatedAt ?? '—' }}</span>
        <ElButton
          text
          :loading="refreshing || listRefreshing"
          :icon="RefreshRight"
          aria-label="刷新详情"
          class="appliance-page__refresh-btn"
          @click="handleDetailRefresh"
        />
      </div>
    </header>

    <ElAlert
      v-if="nodesError"
      :title="nodesError"
      type="error"
      show-icon
      :closable="false"
      class="appliance-page__alert"
    />
    <ElAlert v-if="error" :title="error" type="error" show-icon :closable="false" class="appliance-page__alert" />
    <ElAlert
      v-else-if="nodeOffline"
      :title="nodeOfflineError ?? '节点不可达'"
      type="warning"
      show-icon
      :closable="false"
      class="appliance-page__alert"
    />

    <ElSkeleton
      v-if="(nodesLoading && nodes.length === 0) || (loading && !viewModel && !nodeOffline)"
      :rows="10"
      animated
    />

    <template v-else-if="nodeId">
      <div class="appliance-page__stage">
        <div ref="visualRef" class="appliance-page__visual">
          <div class="appliance-page__watermark" aria-hidden="true" :style="watermarkStyle">{{ modelName }}</div>
          <img
            ref="devicePhotoRef"
            :src="currentDeviceImage"
            alt=""
            class="appliance-page__device-photo"
            @load="syncDeviceFrame"
          />
          <div class="appliance-page__callouts" :style="deviceFrameStyle">
            <div class="appliance-callout appliance-callout--model">
              <div class="appliance-callout__card">
                <span class="appliance-callout__label">设备型号</span>
                <span class="appliance-callout__value">{{ modelName }}</span>
              </div>
              <span class="appliance-callout__line" aria-hidden="true" />
            </div>
            <div class="appliance-callout appliance-callout--uptime">
              <div class="appliance-callout__card">
                <span class="appliance-callout__label">运行时长</span>
                <span class="appliance-callout__value">{{ uptimeText }}</span>
              </div>
              <span class="appliance-callout__line" aria-hidden="true" />
            </div>
            <div class="appliance-callout appliance-callout--ip">
              <span class="appliance-callout__line" aria-hidden="true" />
              <div class="appliance-callout__card">
                <span class="appliance-callout__label">IP地址</span>
                <span class="appliance-callout__value">{{ ipAddress }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="appliance-page__view-switch" role="tablist" aria-label="设备视图">
          <button
            v-for="item in DEVICE_VIEWS"
            :key="item.key"
            type="button"
            class="appliance-page__view-btn"
            :class="{ 'is-active': deviceView === item.key }"
            role="tab"
            :aria-selected="deviceView === item.key"
            @click="deviceView = item.key"
          >
            <span
              class="appliance-page__view-icon"
              :style="{
                maskImage: `url(${item.icon})`,
                WebkitMaskImage: `url(${item.icon})`,
              }"
              aria-hidden="true"
            />
            {{ item.label }}
          </button>
        </div>
      </div>

      <div v-if="viewModel" class="appliance-page__metrics">
        <div
          v-for="card in usageCards"
          :key="card.key"
          class="metric-card"
          :class="{ 'metric-card--clickable': card.showDetail }"
          :role="card.showDetail ? 'button' : undefined"
          :tabindex="card.showDetail ? 0 : undefined"
          @click="openMetricDetail(card.detailKey)"
        >
          <div class="metric-card__header">
            <span class="metric-card__icon-wrap">
              <img :src="card.icon" alt="" class="metric-card__icon" width="24" height="24" />
            </span>
            <h3 class="metric-card__title">{{ card.title }}</h3>
            <ElButton
              v-if="card.showDetail"
              type="primary"
              link
              class="metric-card__detail-btn"
              @click.stop="openMetricDetail(card.detailKey)"
            >
              查看详情
            </ElButton>
          </div>
          <div class="metric-card__body">
            <div class="metric-card__info">
              <div class="metric-card__value">
                <span class="metric-card__number">{{ formatUsagePercent(card.percent) }}</span>
                <span class="metric-card__unit">%</span>
              </div>
              <span v-if="card.capacity" class="metric-card__subtitle metric-card__subtitle--capacity">
                <span class="metric-card__subtitle-num">{{ card.capacity.used }} / {{ card.capacity.total }}</span>
                <span class="metric-card__subtitle-unit">{{ card.capacity.unit }}</span>
              </span>
              <span v-else class="metric-card__subtitle">{{ card.subtitle }}</span>
            </div>
            <svg class="metric-ring" viewBox="0 0 80 80" aria-hidden="true">
              <circle class="metric-ring__track" cx="40" cy="40" :r="RING_RADIUS" :stroke="card.color" />
              <circle
                v-if="card.percent > 0"
                class="metric-ring__bar"
                cx="40"
                cy="40"
                :r="RING_RADIUS"
                :stroke="card.color"
                :stroke-dasharray="RING_CIRCUMFERENCE"
                :stroke-dashoffset="ringDashOffset(card.percent)"
              />
            </svg>
          </div>
        </div>
        <article class="metric-card metric-card--network">
          <div class="metric-card__header">
            <span class="metric-card__icon-wrap">
              <img :src="networkIcon" alt="" class="metric-card__icon" width="24" height="24" />
            </span>
            <h3 class="metric-card__title">网络</h3>
          </div>
          <div class="metric-card__body metric-card__body--network">
            <div class="network-stats">
              <div class="network-stat">
                <div class="metric-card__value">
                  <span class="metric-card__number">{{ networkTx.value }}</span>
                  <span class="metric-card__unit">{{ networkTx.unit }}</span>
                </div>
                <span class="metric-card__subtitle">上行速率</span>
              </div>
              <div class="network-stat">
                <div class="metric-card__value">
                  <span class="metric-card__number">{{ networkRx.value }}</span>
                  <span class="metric-card__unit">{{ networkRx.unit }}</span>
                </div>
                <span class="metric-card__subtitle">下行速率</span>
              </div>
            </div>
            <img :src="networkWaveIcon" alt="" class="network-wave" width="121" height="76" />
          </div>
        </article>
      </div>
      <div v-else class="appliance-page__metrics appliance-page__metrics--empty">
        <ElText type="info">暂无硬件监控数据</ElText>
      </div>

      <ElDialog
        v-model="npuDetailVisible"
        title="NPU 卡详情"
        width="720px"
        append-to-body
        destroy-on-close
        class="npu-detail-dialog"
      >
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
      <ElDialog
        v-model="diskDetailVisible"
        title="磁盘详情"
        width="720px"
        append-to-body
        destroy-on-close
        class="disk-detail-dialog"
      >
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

    <div v-else-if="!nodesLoading" class="appliance-page__empty">
      <ElText type="info">请选择节点查看硬件详情</ElText>
    </div>
  </section>
</template>

<style scoped>
.appliance-page {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 24px;
  padding: 24px 32px;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  box-sizing: border-box;
  background: #ffffff;
}

.appliance-page__bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-color: #ffffff;
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
}

.appliance-page > :not(.appliance-page__bg):not(.el-overlay) {
  position: relative;
  z-index: 1;
}

.appliance-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-shrink: 0;
}

.appliance-page__identity {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.appliance-page__identity :deep(.el-tooltip__trigger) {
  display: inline-flex;
  outline: none;
}

.appliance-page__name-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 8px 0 0;
  border: none;
  background: transparent;
  cursor: pointer;
  color: inherit;
}

.appliance-page__device-name {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  color: #191919;
}

.appliance-page__caret {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  object-fit: contain;
}

.appliance-page__online {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  line-height: 19px;
  color: #191919;
}

.appliance-page__online-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c9c9c9;
}

.appliance-page__online.is-online .appliance-page__online-dot {
  background: #64bb5c;
}

.appliance-page__online.is-offline {
  color: var(--text-secondary);
}

.appliance-page__updated {
  font-size: 14px;
  line-height: 19px;
  color: rgba(0, 0, 0, 0.6);
}

.appliance-page__header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 22px;
  flex-shrink: 0;
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
}

.appliance-page__refresh-btn :deep(.el-icon) {
  width: 14px;
  height: 14px;
  font-size: 14px;
  color: rgba(0, 0, 0, 0.6);
}

.appliance-page__alert {
  margin: 0;
  flex-shrink: 0;
}

.appliance-page__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.appliance-page__stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.appliance-page__visual {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: visible;
}

.appliance-page__watermark {
  position: absolute;
  z-index: 0;
  transform: translate(-50%, -72%) skewX(-15deg);
  font-family: 'HarmonyOS Sans', sans-serif;
  font-size: 144px;
  font-weight: 900;
  line-height: 1;
  white-space: nowrap;
  pointer-events: none;
  user-select: none;
  color: #dee0e7;
  background-image: linear-gradient(180deg, #dee0e7 0%, rgba(222, 224, 231, 0.25) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.appliance-page__device-photo {
  position: absolute;
  z-index: 1;
  left: 50%;
  top: 50%;
  display: block;
  max-height: 90%;
  max-width: 72%;
  width: auto;
  height: auto;
  object-fit: contain;
  object-position: center;
  transform: translate(-50%, -50%);
}

.appliance-page__callouts {
  position: absolute;
  z-index: 2;
  pointer-events: none;
}

.appliance-callout {
  position: absolute;
  z-index: 1;
  display: flex;
  align-items: center;
  pointer-events: none;
}

.appliance-callout--model {
  top: 49%;
  left: calc(10% + 40px);
  transform: translate(-100%, -50%);
}

.appliance-callout--uptime {
  top: 66%;
  left: calc(8% + 40px);
  transform: translate(-100%, -50%);
}

.appliance-callout--ip {
  top: 53%;
  left: calc(90% - 40px);
  transform: translateY(-50%);
}

.appliance-callout__card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: #ffffff;
  border-radius: 8px;
  white-space: nowrap;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}

.appliance-callout__label {
  font-size: 14px;
  line-height: 22px;
  color: #777777;
}

.appliance-callout__value {
  font-size: 14px;
  line-height: 22px;
  color: #191919;
}

.appliance-callout__line {
  position: relative;
  width: 128px;
  height: 2px;
  background: #e5e5ea;
  flex-shrink: 0;
}

.appliance-callout__line::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #e5e5ea;
  transform: translateY(-50%);
}

.appliance-callout--model .appliance-callout__line::after,
.appliance-callout--uptime .appliance-callout__line::after {
  right: 0;
}

.appliance-callout--ip .appliance-callout__line::after {
  left: 0;
}

.appliance-page__view-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 368px;
  padding: 4px;
  border-radius: 20px;
  background: rgba(0, 0, 0, 0.05);
  flex-shrink: 0;
}

.appliance-page__view-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 120px;
  padding: 7px 16px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: rgba(0, 0, 0, 0.6);
  font-size: 14px;
  line-height: 22px;
  cursor: pointer;
}

.appliance-page__view-btn.is-active {
  background: #ffffff;
  color: rgba(0, 0, 0, 0.9);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.appliance-page__view-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  background-color: currentColor;
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-position: center;
}

.appliance-page__metrics {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.5fr);
  gap: 16px;
  align-items: stretch;
  flex-shrink: 0;
}

.appliance-page__metrics--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 172px;
  border-radius: 24px;
  background: #ffffff;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: clamp(16px, 4vh, 44px);
  width: 100%;
  min-width: 0;
  padding: 16px 16px 20px;
  border: none;
  border-radius: 24px;
  background: #ffffff;
  text-align: left;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.04);
  box-sizing: border-box;
}

.metric-card--clickable {
  cursor: pointer;
}

.metric-card--clickable:hover {
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08);
}

.appliance-page__name-btn:focus-visible,
.metric-card--clickable:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.metric-card__header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.metric-card__icon-wrap {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #f1f3f5;
}

.metric-card__icon {
  display: block;
  width: 24px;
  height: 24px;
}

.metric-card__title {
  flex: 1;
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: #191919;
}

.metric-card__detail-btn {
  flex-shrink: 0;
  padding: 0;
  height: auto;
  font-size: 14px;
  line-height: 22px;
  --el-button-text-color: var(--color-primary);
  --el-button-hover-text-color: var(--color-primary);
  --el-button-hover-link-text-color: var(--color-primary);
  color: var(--color-primary);
}

.metric-card__body {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 0 12px;
}

.metric-card__info,
.network-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.metric-card__value {
  display: flex;
  align-items: flex-end;
  gap: 4px;
}

.metric-card__number {
  font-size: 40px;
  font-weight: 500;
  line-height: 56px;
  color: #191919;
}

.metric-card__unit {
  margin-bottom: 9px;
  font-size: 18px;
  font-weight: 500;
  line-height: 24px;
  color: #777777;
  white-space: nowrap;
}

.metric-card__subtitle {
  font-size: 16px;
  line-height: 21px;
  color: rgba(0, 0, 0, 0.6);
}

.metric-card__subtitle--capacity {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
}

.metric-card__subtitle-num {
  color: #191919;
}

.metric-card__subtitle-unit {
  color: #777777;
}

.metric-ring {
  width: 80px;
  height: 80px;
  flex-shrink: 0;
  transform: rotate(-90deg);
}

.metric-ring__track,
.metric-ring__bar {
  fill: none;
  stroke-width: 12;
}

.metric-ring__track {
  opacity: 0.15;
}

.metric-ring__bar {
  stroke-linecap: round;
  transition: stroke-dashoffset 0.6s ease;
}

.metric-card--network .metric-card__body--network {
  align-items: flex-start;
  padding: 0;
}

.network-stats {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  flex: 1;
  min-width: 0;
}

.network-wave {
  display: block;
  width: 121px;
  height: 76px;
  flex-shrink: 0;
  object-fit: contain;
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

.appliance-node-menu__id {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.appliance-node-menu__check {
  width: 16px;
  height: 16px;
  margin-left: 12px;
  flex-shrink: 0;
  object-fit: contain;
}

@media (max-width: 1400px) {
  .appliance-page {
    gap: 16px;
    padding: 16px 24px;
  }

  .appliance-page__metrics {
    gap: 12px;
  }
}

@media (max-width: 1100px) {
  .appliance-callout--model {
    left: calc(10% + 24px);
  }

  .appliance-callout--uptime {
    left: calc(8% + 24px);
  }

  .appliance-callout--ip {
    left: calc(90% - 24px);
  }

  .appliance-callout__line {
    width: 72px;
  }

  .appliance-page__device-photo {
    max-width: 86%;
  }
}

@media (max-width: 768px) {
  .appliance-page {
    height: auto;
    min-height: 100%;
    overflow: auto;
    padding: 16px;
  }

  .appliance-page__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .appliance-page__metrics {
    grid-template-columns: 1fr;
  }

  .metric-card--network {
    grid-column: auto;
  }

  .appliance-page__view-switch {
    width: 100%;
    max-width: 368px;
  }

  .appliance-callout {
    position: static;
    transform: none;
    margin-top: 8px;
    pointer-events: auto;
  }

  .appliance-callout__line {
    display: none;
  }

  .appliance-page__visual {
    flex-direction: column;
    align-items: center;
    min-height: 320px;
  }

  .appliance-page__device-photo {
    position: relative;
    left: auto;
    top: auto;
    transform: none;
    max-width: 100%;
    height: 280px;
  }

  .appliance-page__callouts {
    position: static;
    width: 100% !important;
    height: auto !important;
    left: auto !important;
    top: auto !important;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
}
</style>

<style>
.appliance-node-menu .el-dropdown-menu__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 160px;
}
</style>
