<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElTag, ElSkeleton, ElResult, ElButton, ElIcon } from 'element-plus';
import { ArrowLeft, Monitor } from '@element-plus/icons-vue';
import ModelInfoDrawer from './ModelInfoDrawer.vue';
import ChartCard from './ChartCard.vue';
import MetricDisplay from './MetricDisplay.vue';
import DataTable from './DataTable.vue';
import { fetchModelDetail, updateModel } from '@/api/inference';
import type { ModelDetail } from '@/api/inference';

const router = useRouter();
const route = useRoute();

const loading = ref(false);
const error = ref<string | null>(null);
const modelData = ref<ModelDetail | null>(null);
const drawerVisible = ref(false);
const drawerMode = ref<'view' | 'edit'>('view');
const activeTimeFilter = ref('12h');

const timeFilters = [
  { key: '12h', label: '近12小时' },
  { key: '24h', label: '近24小时' },
  { key: '7d', label: '近7天' },
  { key: '30d', label: '近30天' },
];

const metadata = computed(() => {
  if (!modelData.value) return [];
  const d = modelData.value;
  return [
    { label: '模型名称', value: d.model_name || '--' },
    { label: '模型类型', value: d.litellm_params?.model || '--' },
    { label: 'API Base', value: d.litellm_params?.api_base || '--' },
    { label: '实例URL', value: d.instance_url || '--' },
    { label: '最大并发数', value: d.max_concurrent?.toString() || '--' },
    { label: '创建时间', value: d.created_at || '--' },
    { label: '更新时间', value: d.updated_at || '--' },
  ];
});

const tokenRateColumns = [
  { key: 'name', label: '数据名称', color: '#2563eb' },
  { key: 'avg', label: '平均值' },
  { key: 'max', label: '最大值' },
  { key: 'min', label: '最小值' },
];

const tokenRateData = [
  { name: '输入token速率', avg: '18.6', max: '4,820', min: '320' },
  { name: '输出token速率', avg: '672', max: '2,140', min: '96', color: '#22c55e' },
];

const requestRateData = [
  { name: '请求速率', avg: '18.6', max: '4,820', min: '320' },
];

const kvCacheData = [
  { name: 'KV Cache使用率', avg: '63.5%', max: '88.4%', min: '28.6%' },
];

async function loadModelDetail() {
  const id = route.params.id as string;
  if (!id) { error.value = '模型 ID 不能为空'; return; }
  loading.value = true;
  error.value = null;
  try {
    modelData.value = await fetchModelDetail(id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '获取模型信息失败';
  } finally {
    loading.value = false;
  }
}

function openDrawer(mode: 'view' | 'edit') {
  drawerMode.value = mode;
  drawerVisible.value = true;
}

function goBack() {
  router.push({ name: 'inference-model-dashboard' });
}

async function handleSave(data: Partial<ModelDetail>) {
  const id = route.params.id as string;
  try {
    await updateModel(id, data);
    await loadModelDetail();
    drawerVisible.value = false;
  } catch (e) {
    console.error('保存失败:', e);
  }
}

watch(() => route.params.id, (newId) => { if (newId) loadModelDetail(); });
onMounted(() => { loadModelDetail(); });
</script>

<template>
  <section class="page">
    <template v-if="loading"><ElSkeleton :rows="5" animated /></template>
    <ElResult v-else-if="error" icon="error" :title="error" sub-title="请检查网络连接或稍后重试">
      <template #extra><ElButton type="primary" @click="loadModelDetail">重试</ElButton></template>
    </ElResult>
    <template v-else-if="modelData">
      <div class="detail-header">
        <button class="detail-back" @click="goBack"><el-icon :size="20"><ArrowLeft /></el-icon></button>
        <div class="detail-header__icon" v-if="modelData">
          <el-icon :size="28" color="#2563eb"><Monitor /></el-icon>
        </div>
        <div class="detail-header__info">
          <div class="detail-header__name">
            <span style="font-size: 20px; font-weight: 600">{{ modelData.model_name }}</span>
          </div>
          <span style="font-size: 12px; color: var(--text-secondary)">模型类型 {{ modelData.litellm_params?.model || '--' }}</span>
        </div>
        <button class="detail-link" @click="openDrawer('view')">模型详情</button>
      </div>

      <div class="metadata-bar">
        <div v-for="item in metadata" :key="item.label" class="metadata-item">
          <span class="metadata-item__label">{{ item.label }}</span>
          <ElTag v-if="item.isTag" size="small" type="info">{{ item.value }}</ElTag>
          <span v-else class="metadata-item__value">{{ item.value }}</span>
        </div>
      </div>

      <div class="performance-section">
        <div class="performance-header">
          <h2 style="margin: 0; font-size: 18px; font-weight: 600">性能监控</h2>
          <div class="time-filter">
            <button v-for="f in timeFilters" :key="f.key" class="filter-tab" :class="{ 'filter-tab--active': activeTimeFilter === f.key }" @click="activeTimeFilter = f.key">{{ f.label }}</button>
          </div>
        </div>
        <div class="charts-grid">
          <ChartCard title="Token速率">
            <div class="chart-metrics">
              <MetricDisplay label="输入Token速率" value="19,080" unit="Token/s" trend="+46%" trend-label="较5分钟前" trend-type="up" />
              <MetricDisplay label="输出Token速率" value="19,080" unit="Token/s" trend="+28%" trend-label="较5分钟前" trend-type="up" />
            </div>
            <iframe width="100%" height="120" frameborder="0" style="background: #f3f4f6; border-radius: 8px;" />
            <DataTable :columns="tokenRateColumns" :data="tokenRateData" />
          </ChartCard>

          <ChartCard title="请求速率">
            <MetricDisplay label="当前值" value="18.6" unit="request/s" trend="+22.4%" trend-label="较5分钟前" trend-type="up" />
            <iframe width="100%" height="120" frameborder="0" style="background: #f3f4f6; border-radius: 8px;" />
            <DataTable :columns="tokenRateColumns" :data="requestRateData" />
          </ChartCard>

          <ChartCard title="KV Cache使用率">
            <MetricDisplay label="当前值" value="76.8" unit="%" trend="+22.4%" trend-label="较5分钟前" trend-type="up" />
            <iframe width="100%" height="120" frameborder="0" style="background: #f3f4f6; border-radius: 8px;" />
            <DataTable :columns="tokenRateColumns" :data="kvCacheData" />
          </ChartCard>

          <ChartCard title="首Token时延_TTFT">
            <div class="chart-metrics">
              <MetricDisplay label="TTFT_P95" value="720" unit="ms" trend="-10.0%" trend-label="较阈值基线" trend-type="down" />
              <MetricDisplay label="TTFT_P99" value="1,080" unit="ms" trend="-10.0%" trend-label="较阈值基线" trend-type="down" />
            </div>
            <iframe width="100%" height="120" frameborder="0" style="background: #f3f4f6; border-radius: 8px;" />
          </ChartCard>

          <ChartCard title="Token生成时延_TPOT">
            <div class="chart-metrics">
              <MetricDisplay label="TPOT_P95" value="42" unit="ms/token" trend="+16.7%" trend-label="较阈值基线" trend-type="up" />
              <MetricDisplay label="TPOT_P99" value="61" unit="ms/token" trend="+17.3%" trend-label="较阈值基线" trend-type="up" />
            </div>
            <iframe width="100%" height="120" frameborder="0" style="background: #f3f4f6; border-radius: 8px;" />
          </ChartCard>

          <ChartCard title="端到端时延_E2E Latency">
            <div class="chart-metrics">
              <MetricDisplay label="E2E_P95" value="5.4" unit="s" trend="-10.0%" trend-label="较阈值基线" trend-type="down" />
              <MetricDisplay label="E2E_P99" value="9.2" unit="s" trend="-8.0%" trend-label="较阈值基线" trend-type="down" />
            </div>
            <iframe width="100%" height="120" frameborder="0" style="background: #f3f4f6; border-radius: 8px;" />
          </ChartCard>
        </div>
      </div>
    </template>

    <ModelInfoDrawer :visible="drawerVisible" :mode="drawerMode" :model="modelData" @close="drawerVisible = false" @edit="drawerMode = 'edit'" @save="handleSave" @export="() => {}" />
  </section>
</template>

<style scoped>
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.detail-header__icon { width: 44px; height: 44px; border-radius: 10px; background: #f3f4f6; display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }
.detail-header__icon img { width: 100%; height: 100%; object-fit: contain; padding: 4px; }
.detail-link { margin-left: auto; font-size: 14px; color: #2563eb; cursor: pointer; background: none; border: none; }
.detail-link:hover { text-decoration: underline; }
.detail-back { border: none; background: none; cursor: pointer; padding: 4px; color: var(--text-secondary); }
.detail-back:hover { color: var(--text-primary); }
.detail-header__info { display: flex; flex-direction: column; gap: 4px; }
.detail-header__name { display: flex; align-items: center; gap: 12px; }
.status-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; color: #374151; }
.status-badge__dot { width: 8px; height: 8px; border-radius: 50%; background: #9ca3af; }
.status-badge--success .status-badge__dot { background: #22c55e; }
.status-badge--error .status-badge__dot { background: #ef4444; }
.status-badge--warning .status-badge__dot { background: #f59e0b; }
.metadata-bar { display: flex; gap: 24px; padding: 12px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 24px; flex-wrap: wrap; }
.metadata-item { display: flex; flex-direction: column; gap: 4px; }
.metadata-item__label { font-size: 12px; color: var(--text-secondary); }
.metadata-item__value { font-size: 14px; color: var(--text-primary); }
.performance-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.charts-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.chart-metrics { display: flex; gap: 40px; }
</style>
