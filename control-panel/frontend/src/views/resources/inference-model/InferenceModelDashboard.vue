<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  ElInput,
  ElMessageBox,
  ElButton,
  ElRadioGroup,
  ElRadioButton,
  ElAlert,
  ElSkeleton,
  ElEmpty,
  ElMessage,
} from 'element-plus';
import { Search } from '@element-plus/icons-vue';
import ModelCard from './ModelCard.vue';
import AddModelModal from './AddModelModal.vue';
import ModelInfoDrawer from './ModelInfoDrawer.vue';
import {
  fetchModelList,
  fetchModelDetail,
  createModel,
  updateModel,
  deleteModel,
  restartModel,
  fetchUsageOverview,
  fetchUserUsage,
} from '@/api/inference';
import type { ModelDetail } from '@/api/inference';
import { useAuth } from '@/composables/useAuth';
import {
  calculateOverviewTotals,
  calculateUserTotals,
  formatTokens,
  getDateRange,
  USAGE_ALL_TIME_START,
} from './utils/usage';

const router = useRouter();
const { isAdmin, userId } = useAuth();
const loading = ref(false);
const listError = ref('');

interface ModelCardData {
  id: string;
  name: string;
  status: 'success' | 'error' | 'warning';
  statusText: string;
  tags: string[];
  e2eP95: string;
  todayCalls: string;
  todayTokens: string;
  meta: string[];
  iconSrc: undefined;
  contextWindow?: number | null;
}

const models = ref<ModelCardData[]>([]);
const activeFilter = ref('all');
const searchQuery = ref('');
const showAddModal = ref(false);
const drawerVisible = ref(false);
const drawerMode = ref<'view' | 'edit'>('view');
const selectedModel = ref<ModelDetail | null>(null);

const filters = [{ key: 'all', label: '全部模型' }];

// 调用概览数据
const overviewData = ref({
  today: { requests: 0, tokens: 0 },
  week: { requests: 0, tokens: 0 },
  total: { requests: 0, tokens: 0 },
});
const overviewError = ref('');

async function loadOverviewData() {
  overviewError.value = '';
  try {
    if (isAdmin.value) {
      // 管理员：使用 /overview 接口获取所有用户数据
      const [todayRes, weekRes, totalRes] = await Promise.all([
        fetchUsageOverview(getDateRange(0)),
        fetchUsageOverview(getDateRange(7)),
        fetchUsageOverview(getDateRange(USAGE_ALL_TIME_START)),
      ]);

      overviewData.value = {
        today: calculateOverviewTotals(todayRes),
        week: calculateOverviewTotals(weekRes),
        total: calculateOverviewTotals(totalRes),
      };
    } else {
      // 普通用户：使用 /user 接口获取自己的数据
      const uid = userId.value;
      if (!uid) {
        overviewError.value = '无法获取用户信息';
        return;
      }

      const [todayRes, weekRes, totalRes] = await Promise.all([
        fetchUserUsage({ user_id: uid, ...getDateRange(0) }),
        fetchUserUsage({ user_id: uid, ...getDateRange(7) }),
        fetchUserUsage({ user_id: uid, ...getDateRange(USAGE_ALL_TIME_START) }),
      ]);

      overviewData.value = {
        today: calculateUserTotals(todayRes),
        week: calculateUserTotals(weekRes),
        total: calculateUserTotals(totalRes),
      };
    }
  } catch (e) {
    console.error('加载调用概览数据失败:', e);
    overviewError.value = e instanceof Error ? e.message : '加载调用概览数据失败';
  }
}

async function loadModels() {
  loading.value = true;
  listError.value = '';
  try {
    const data = await fetchModelList({ keyword: searchQuery.value });
    // 将后端数据转换为ModelCard期望的格式
    models.value =
      data?.items?.map((item) => {
        const statusMap: Record<string, { status: 'success' | 'error' | 'warning'; statusText: string }> = {
          healthy: { status: 'success', statusText: '健康' },
          unhealthy: { status: 'error', statusText: '异常' },
        };
        const { status, statusText } = statusMap[item.status ?? ''] ?? { status: 'warning', statusText: '未知' };
        return {
          id: item.id,
          name: item.model_name,
          status,
          statusText,
          tags: [],
          e2eP95: '--',
          todayCalls: '--',
          todayTokens: '--',
          meta: [item.litellm_params.model],
          iconSrc: undefined,
          contextWindow: item.model_info?.context_window,
        };
      }) ?? [];
  } catch (e) {
    models.value = [];
    listError.value = e instanceof Error ? e.message : '加载模型列表失败';
  } finally {
    loading.value = false;
  }
}

function goToModel(id: string) {
  router.push({ name: 'inference-model-detail', params: { id } });
}
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
async function handleEditModel(id: string) {
  try {
    selectedModel.value = await fetchModelDetail(id);
    drawerMode.value = 'edit';
    drawerVisible.value = true;
  } catch (e) {
    console.error(e);
  }
}

async function handleSaveModel(data: Partial<ModelDetail>) {
  if (!selectedModel.value) return;
  try {
    await updateModel(selectedModel.value.id, data);
    ElMessage.success('保存成功');
    drawerVisible.value = false;
    await loadModels();
  } catch (e) {
    ElMessage.error('保存失败: ' + (e instanceof Error ? e.message : '未知错误'));
  }
}

async function handleRestartModel(id: string) {
  try {
    await restartModel(id);
    await loadModels();
  } catch (e) {
    console.error(e);
  }
}

async function handleAddModel(formData: {
  name: string;
  type: string;
  contextLength: number | null;
  deployName: string;
  deployFramework: string;
  serviceIp: string;
  servicePort: number | null;
  metricsUrl: string;
  apiKey?: string;
  paramSize?: string;
  tags?: string;
  description?: string;
}) {
  // 必填项验证
  if (!formData.name?.trim()) {
    ElMessage.warning('请输入模型名称');
    return;
  }
  if (!formData.deployName?.trim()) {
    ElMessage.warning('请输入部署模型名称');
    return;
  }
  if (!formData.serviceIp?.trim()) {
    ElMessage.warning('请输入服务IP地址');
    return;
  }
  if (!formData.servicePort) {
    ElMessage.warning('请输入服务端口');
    return;
  }

  try {
    // 默认使用openai前缀
    const modelIdentifier = `openai/${formData.deployName}`;
    const serviceUrl = `http://${formData.serviceIp}:${formData.servicePort}`;

    await createModel({
      model_name: formData.name,
      litellm_params: {
        model: modelIdentifier,
        api_base: serviceUrl,
        api_key: formData.apiKey || 'sk-1234',
      },
      model_info: formData.contextLength ? { context_window: formData.contextLength } : undefined,
      instance_url: formData.metricsUrl || undefined,
      inference_engine: formData.deployFramework || undefined,
    });
    ElMessage.success('模型创建成功');
    showAddModal.value = false;
    await loadModels();
  } catch (e) {
    ElMessage.error('创建模型失败: ' + (e instanceof Error ? e.message : '未知错误'));
  }
}

watch([activeFilter, searchQuery], () => {
  loadModels();
});
onMounted(() => {
  loadModels();
  loadOverviewData();
});
</script>

<template>
  <section class="page inference-dashboard">
    <h1 class="page-title">推理模型</h1>

    <!-- Overview Card -->
    <div class="overview-card">
      <div class="overview-card__header">
        <div class="overview-card__title"><span>调用概览</span></div>
        <ElButton
          class="overview-card__detail"
          link
          type="primary"
          @click="router.push({ name: 'inference-model-call-analysis' })"
        >
          查看详情
        </ElButton>
      </div>
      <ElAlert v-if="overviewError" :title="`加载失败: ${overviewError}`" type="error" show-icon :closable="false" />
      <div v-else class="overview-card__content">
        <div class="overview-card__section">
          <div class="overview-card__section-header"><span>调用次数</span></div>
          <div class="overview-card__metrics">
            <div class="overview-card__metric">
              <span class="overview-card__metric-label">今日</span
              ><span class="overview-card__metric-value"
                >{{ overviewData.today.requests.toLocaleString()
                }}<span class="overview-card__metric-unit">次</span></span
              >
            </div>
            <div class="overview-card__metric">
              <span class="overview-card__metric-label">本周</span
              ><span class="overview-card__metric-value"
                >{{ overviewData.week.requests.toLocaleString()
                }}<span class="overview-card__metric-unit">次</span></span
              >
            </div>
            <div class="overview-card__metric">
              <span class="overview-card__metric-label">累计</span
              ><span class="overview-card__metric-value"
                >{{ overviewData.total.requests.toLocaleString()
                }}<span class="overview-card__metric-unit">次</span></span
              >
            </div>
          </div>
        </div>
        <div class="overview-card__divider"></div>
        <div class="overview-card__section">
          <div class="overview-card__section-header"><span>Token数</span></div>
          <div class="overview-card__metrics">
            <div class="overview-card__metric">
              <span class="overview-card__metric-label">今日</span
              ><span class="overview-card__metric-value">{{ formatTokens(overviewData.today.tokens) }}</span>
            </div>
            <div class="overview-card__metric">
              <span class="overview-card__metric-label">本周</span
              ><span class="overview-card__metric-value">{{ formatTokens(overviewData.week.tokens) }}</span>
            </div>
            <div class="overview-card__metric">
              <span class="overview-card__metric-label">累计</span
              ><span class="overview-card__metric-value">{{ formatTokens(overviewData.total.tokens) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Model Cards -->
    <div class="card model-list-card">
      <div class="model-section__header">
        <h2 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary)">可用推理模型</h2>
        <ElButton type="primary" @click="showAddModal = true">添加模型</ElButton>
      </div>
      <div class="model-section__toolbar">
        <ElRadioGroup v-model="activeFilter">
          <ElRadioButton v-for="f in filters" :key="f.key" :value="f.key">{{ f.label }}</ElRadioButton>
        </ElRadioGroup>
        <ElInput
          v-model="searchQuery"
          placeholder="请输入搜索内容"
          :prefix-icon="Search"
          clearable
          style="width: 240px"
        />
      </div>
      <div v-if="loading" class="model-list-state">
        <ElSkeleton :rows="6" animated />
      </div>
      <ElAlert v-else-if="listError" :title="listError" type="error" show-icon :closable="false" />
      <div v-else-if="!models.length" class="model-list-state">
        <ElEmpty description="暂无推理模型" :image-size="80" />
      </div>
      <div v-else class="model-grid">
        <ModelCard
          v-for="model in models"
          :key="model.id"
          v-bind="model"
          :icon-src="model.iconSrc"
          :is-admin="isAdmin"
          @click="goToModel(model.id)"
          @delete="handleDeleteModel(model.id)"
          @edit="handleEditModel(model.id)"
          @restart="handleRestartModel(model.id)"
        />
      </div>
    </div>

    <AddModelModal :visible="showAddModal" @close="showAddModal = false" @save="handleAddModel" />
    <ModelInfoDrawer
      :visible="drawerVisible"
      :mode="drawerMode"
      :model="selectedModel"
      @close="drawerVisible = false"
      @edit="drawerMode = 'edit'"
      @save="handleSaveModel"
      @export="() => {}"
    />
  </section>
</template>

<style scoped>
.inference-dashboard {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  box-sizing: border-box;
}

.overview-card {
  background: var(--bg-2);
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
  flex-shrink: 0;
}
.overview-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.overview-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.overview-card__detail {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  height: auto;
  padding: 0;
}
.overview-card__content {
  display: flex;
  gap: 0;
}
.overview-card__section {
  flex: 1;
  padding: 0 20px;
}
.overview-card__section:first-child {
  padding-left: 0;
}
.overview-card__section:last-child {
  padding-right: 0;
}
.overview-card__divider {
  width: 1px;
  background: var(--border);
  margin: 0 20px;
}
.overview-card__section-header {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}
.overview-card__metrics {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
}
.overview-card__metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.overview-card__metric-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.overview-card__metric-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}
.overview-card__metric-unit {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
  margin-left: 2px;
}

.model-list-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-top: 24px;
}

.model-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.model-section__toolbar {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 20px;
  flex-shrink: 0;
}
.model-list-state {
  flex: 1;
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
}
.model-grid {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
  gap: 28px;
  align-content: start;
}
</style>
