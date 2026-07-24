<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElTag, ElSkeleton, ElResult, ElButton, ElIcon } from 'element-plus';
import { ArrowLeft, Monitor } from '@element-plus/icons-vue';
import ModelInfoDrawer from './ModelInfoDrawer.vue';
import { fetchModelDetail, updateModel } from '@/api/inference';
import type { ModelDetail } from '@/api/inference';
import PerformanceMonitor from './PerformanceMonitor.vue';

const router = useRouter();
const route = useRoute();

const loading = ref(false);
const error = ref<string | null>(null);
const modelData = ref<ModelDetail | null>(null);
const drawerVisible = ref(false);
const drawerMode = ref<'view' | 'edit'>('view');

const metadata = computed(() => {
  if (!modelData.value) return [];
  const d = modelData.value;
  return [
    { label: '模型名称', value: d.model_name || '--', isTag: false },
    { label: '模型类型', value: d.litellm_params?.model || '--', isTag: false },
    { label: 'API Base', value: d.litellm_params?.api_base || '--', isTag: false },
    { label: '部署框架', value: d.inference_engine || '--', isTag: false },
    { label: '模型描述', value: d.model_info?.description || '--', isTag: false },
    { label: '模型监控URL', value: d.instance_url || '--', isTag: false },
    { label: '创建时间', value: d.created_at || '--', isTag: false },
    { label: '更新时间', value: d.updated_at || '--', isTag: false },
  ];
});

async function loadModelDetail() {
  const id = route.params.id as string;
  if (!id) {
    error.value = '模型 ID 不能为空';
    return;
  }
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

async function handleSave(data: Partial<ModelDetail> | Record<string, unknown>) {
  const id = route.params.id as string;
  try {
    await updateModel(id, data as Partial<ModelDetail>);
    await loadModelDetail();
    drawerVisible.value = false;
  } catch (e) {
    console.error('保存失败:', e);
  }
}

watch(
  () => route.params.id,
  (newId) => {
    if (newId) loadModelDetail();
  },
);
onMounted(() => {
  loadModelDetail();
});
</script>

<template>
  <section class="page">
    <template v-if="loading"><ElSkeleton :rows="5" animated /></template>
    <ElResult v-else-if="error" icon="error" :title="error" sub-title="请检查网络连接或稍后重试">
      <template #extra><ElButton type="primary" @click="loadModelDetail">重试</ElButton></template>
    </ElResult>
    <template v-else-if="modelData">
      <div class="detail-header">
        <ElButton class="detail-back" text :icon="ArrowLeft" @click="goBack" />
        <div class="detail-header__icon" v-if="modelData">
          <el-icon :size="28" color="#2563eb"><Monitor /></el-icon>
        </div>
        <div class="detail-header__info">
          <div class="detail-header__name">
            <span style="font-size: 20px; font-weight: 600">{{ modelData.model_name }}</span>
          </div>
          <span style="font-size: 12px; color: var(--text-secondary)"
            >模型类型 {{ modelData.litellm_params?.model || '--' }}</span
          >
        </div>
        <ElButton class="detail-link" link type="primary" @click="openDrawer('view')">模型详情</ElButton>
      </div>

      <div class="metadata-bar">
        <div v-for="item in metadata" :key="item.label" class="metadata-item">
          <span class="metadata-item__label">{{ item.label }}</span>
          <ElTag v-if="item.isTag" size="small" type="info">{{ item.value }}</ElTag>
          <span v-else class="metadata-item__value">{{ item.value }}</span>
        </div>
      </div>
      <PerformanceMonitor
        :inference-engine="modelData.inference_engine"
        :grafana-job-name="modelData.grafana_job_name"
      />
    </template>

    <ModelInfoDrawer
      :visible="drawerVisible"
      :mode="drawerMode"
      :model="modelData"
      @close="drawerVisible = false"
      @edit="drawerMode = 'edit'"
      @save="handleSave"
      @export="() => {}"
    />
  </section>
</template>

<style scoped>
.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.detail-header__icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}
.detail-header__icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 4px;
}
.detail-link {
  margin-left: auto;
  font-size: 14px;
  height: auto;
  padding: 0;
}
.detail-back {
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--text-secondary);
}
.detail-back:hover {
  color: var(--text-primary);
}
.detail-header__info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail-header__name {
  display: flex;
  align-items: center;
  gap: 12px;
}
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-primary);
}
.status-badge__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
}
.status-badge--success .status-badge__dot {
  background: var(--success);
}
.status-badge--error .status-badge__dot {
  background: var(--error);
}
.status-badge--warning .status-badge__dot {
  background: var(--alert);
}
.metadata-bar {
  display: flex;
  gap: 24px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-separator);
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.metadata-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metadata-item__label {
  font-size: 12px;
  color: var(--text-secondary);
}
.metadata-item__value {
  font-size: 14px;
  color: var(--text-primary);
}
.performance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.charts-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.chart-metrics {
  display: flex;
  gap: 40px;
}
</style>
