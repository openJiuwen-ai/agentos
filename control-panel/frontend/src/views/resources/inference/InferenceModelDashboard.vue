<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElInput, ElIcon, ElMessageBox } from 'element-plus';
import { Search, Plus, ArrowUp, ArrowRight } from '@element-plus/icons-vue';
import ModelCard from './ModelCard.vue';
import AddModelModal from './AddModelModal.vue';
import ModelInfoDrawer from './ModelInfoDrawer.vue';
import { fetchModelList, fetchModelDetail, createModel, deleteModel, restartModel } from '@/api/inference';
import type { InferenceModelItem, ModelDetail } from '@/api/inference';
import { ElMessage } from 'element-plus';

const router = useRouter();
const loading = ref(false);
const models = ref<InferenceModelItem[]>([]);
const activeFilter = ref('all');
const searchQuery = ref('');
const showAddModal = ref(false);
const drawerVisible = ref(false);
const drawerMode = ref<'view' | 'edit'>('view');
const selectedModel = ref<ModelDetail | null>(null);

const filters = [
  { key: 'all', label: '全部状态' },
  { key: 'healthy', label: '健康' },
  { key: 'error', label: '异常' },
  { key: 'offline', label: '离线' },
];

async function loadModels() {
  loading.value = true;
  try {
    const data = await fetchModelList({ status: activeFilter.value, keyword: searchQuery.value });
    // 将后端数据转换为ModelCard期望的格式
    models.value = data.items.map(item => ({
      id: item.id,
      name: item.model_name,
      status: 'success' as const,
      statusText: '健康',
      tags: [],
      e2eP95: '--',
      todayCalls: '--',
      todayTokens: '--',
      meta: [item.litellm_params.model],
      iconSrc: undefined,
    }));
  } catch (e) { console.error('加载模型列表失败:', e); } finally { loading.value = false; }
}

function goToModel(id: string) { router.push({ name: 'inference-model-detail', params: { id } }); }
async function handleDeleteModel(id: string) {
  try {
    await ElMessageBox.confirm('确定要删除这个模型吗？删除后将无法恢复。', '确认删除', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await deleteModel(id);
    ElMessage.success('删除成功');
    await loadModels();
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
  }
}
async function handleEditModel(id: string) { try { selectedModel.value = await fetchModelDetail(id); drawerMode.value = 'edit'; drawerVisible.value = true; } catch (e) { console.error(e); } }
async function handleRestartModel(id: string) { try { await restartModel(id); await loadModels(); } catch (e) { console.error(e); } }

async function handleAddModel(formData: { name: string; type: string; contextLength: number | null; deployName: string; deployFramework: string; serverLocation: string; serviceIp: string; servicePort: number | null; serviceUrl: string; paramSize?: string; tags?: string; description?: string }) {
  // 必填项验证
  if (!formData.name?.trim()) {
    ElMessage.warning('请输入模型名称');
    return;
  }
  if (!formData.deployName?.trim()) {
    ElMessage.warning('请输入部署模型名称');
    return;
  }
  if (!formData.serviceUrl?.trim()) {
    ElMessage.warning('请输入服务URL');
    return;
  }

  try {
    // 默认使用openai前缀
    const modelIdentifier = `openai/${formData.deployName}`;
    
    await createModel({
      model_name: formData.name,
      litellm_params: {
        model: modelIdentifier,
        api_base: formData.serviceUrl || undefined,
      },
      instance_url: formData.serviceUrl ? `${formData.serviceIp}:${formData.servicePort}` : undefined,
    });
    ElMessage.success('模型创建成功');
    showAddModal.value = false;
    await loadModels();
  } catch (e) {
    ElMessage.error('创建模型失败: ' + (e instanceof Error ? e.message : '未知错误'));
  }
}

watch([activeFilter, searchQuery], () => { loadModels(); });
onMounted(() => { loadModels(); });
</script>

<template>
  <section class="page">
    <h1 class="page-title">推理模型</h1>

    <!-- Overview Card -->
    <div class="overview-card">
      <div class="overview-card__header">
        <div class="overview-card__title"><span>调用概览</span></div>
        <button class="overview-card__detail" @click="router.push({ name: 'inference-model-call-analysis' })">查看详情 <el-icon :size="14"><ArrowRight /></el-icon></button>
      </div>
      <div class="overview-card__content">
        <div class="overview-card__section">
          <div class="overview-card__section-header"><span>调用次数</span></div>
          <div class="overview-card__metrics">
            <div class="overview-card__metric"><span class="overview-card__metric-label">今日</span><span class="overview-card__metric-value">128<span class="overview-card__metric-unit">次</span></span><span class="overview-card__trend"><el-icon :size="12"><ArrowUp /></el-icon> +22%</span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">本周</span><span class="overview-card__metric-value">846<span class="overview-card__metric-unit">次</span></span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">累计</span><span class="overview-card__metric-value">12,436<span class="overview-card__metric-unit">次</span></span></div>
          </div>
        </div>
        <div class="overview-card__divider"></div>
        <div class="overview-card__section">
          <div class="overview-card__section-header"><span>Token数</span></div>
          <div class="overview-card__metrics">
            <div class="overview-card__metric"><span class="overview-card__metric-label">今日</span><span class="overview-card__metric-value">279.1K</span><span class="overview-card__trend"><el-icon :size="12"><ArrowUp /></el-icon> +22%</span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">本周</span><span class="overview-card__metric-value">1.92M</span></div>
            <div class="overview-card__metric"><span class="overview-card__metric-label">累计</span><span class="overview-card__metric-value">28.58M</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Model Cards -->
    <div class="card" style="margin-top: 24px">
      <div class="model-section__header">
        <h2 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary)">可用推理模型</h2>
        <button class="btn btn--primary" @click="showAddModal = true"><el-icon :size="16"><Plus /></el-icon> 添加模型</button>
      </div>
      <div class="model-section__toolbar">
        <div class="filter-tabs">
          <button v-for="f in filters" :key="f.key" class="filter-tab" :class="{ 'filter-tab--active': activeFilter === f.key }" @click="activeFilter = f.key">{{ f.label }}</button>
        </div>
        <ElInput v-model="searchQuery" placeholder="请输入搜索内容" :prefix-icon="Search" clearable style="width: 240px" />
      </div>
      <div class="model-grid">
        <ModelCard v-for="model in models" :key="model.id" v-bind="model" :icon-src="model.iconSrc" @click="goToModel(model.id)" @delete="handleDeleteModel(model.id)" @edit="handleEditModel(model.id)" @restart="handleRestartModel(model.id)" />
      </div>
    </div>

    <AddModelModal :visible="showAddModal" @close="showAddModal = false" @save="handleAddModel" />
    <ModelInfoDrawer :visible="drawerVisible" :mode="drawerMode" :model="selectedModel" @close="drawerVisible = false" @edit="drawerMode = 'edit'" @save="() => { drawerVisible = false; loadModels(); }" @export="() => {}" />
  </section>
</template>

<style scoped>
.overview-card { background: #fff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 20px; margin-top: 20px; }
.overview-card__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.overview-card__title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; color: #111827; }
.overview-card__detail { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #2563eb; background: none; border: none; cursor: pointer; }
.overview-card__detail:hover { opacity: 0.8; }
.overview-card__content { display: flex; gap: 0; }
.overview-card__section { flex: 1; padding: 0 20px; }
.overview-card__section:first-child { padding-left: 0; }
.overview-card__section:last-child { padding-right: 0; }
.overview-card__divider { width: 1px; background: #e5e7eb; margin: 0 20px; }
.overview-card__section-header { font-size: 13px; color: #6b7280; margin-bottom: 12px; }
.overview-card__metrics { display: flex; gap: 24px; margin-bottom: 16px; }
.overview-card__metric { display: flex; flex-direction: column; gap: 2px; }
.overview-card__metric-label { font-size: 12px; color: #9ca3af; }
.overview-card__metric-value { font-size: 24px; font-weight: 600; color: #111827; }
.overview-card__metric-unit { font-size: 12px; font-weight: 400; color: #6b7280; margin-left: 2px; }
.overview-card__trend { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; font-weight: 500; color: #22c55e; margin-top: 4px; }
.model-section__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.model-section__toolbar { display: flex; align-items: center; gap: 24px; margin-bottom: 20px; }
.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 28px; }
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; font-size: 14px; font-weight: 500; border: 1px solid var(--border-color, #d1d5db); border-radius: 6px; background: #fff; color: var(--text-primary, #1f2937); cursor: pointer; }
.btn--primary { background: #2563eb; border-color: #2563eb; color: #fff; }
.btn--primary:hover { background: #1d4ed8; }
</style>
