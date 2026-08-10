<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import {
  ElButton,
  ElDialog,
  ElInput,
  ElProgress,
  ElMessage,
  ElUpload,
  ElPagination,
} from 'element-plus';
import { Plus, Search } from '@element-plus/icons-vue';
import type { UploadFile } from 'element-plus';
import {
  listFrameworks,
  uploadPackage,
  triggerBuild,
  getBuildStatus,
  type FrameworkItem,
  type BuildTaskStatus,
} from '@/api/framework';
import FrameworkCard from './FrameworkCard.vue';
import gridViewIcon from '@/assets/images/framework-page/grid-view-icon.png';
import listViewIcon from '@/assets/images/framework-page/list-view-icon.png';
import uploadIcon from '@/assets/images/framework-page/upload-icon.png';
import closeDialogIcon from '@/assets/images/framework-page/close-icon.png';
import parsingIcon from '@/assets/images/framework-page/parsing-icon.png';


// ── framework list ──
const frameworks = ref<FrameworkItem[]>([]);
const total = ref(0);
const loading = ref(false);

let searchTimer: ReturnType<typeof setTimeout> | null = null;

async function loadFrameworks() {
  loading.value = true;
  try {
    const result = await listFrameworks({
      framework: searchQuery.value.trim(),
      size: pageSize.value,
      page: currentPage.value,
    });
    frameworks.value = result.items;
    total.value = result.total;
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage.value = 1;
    loadFrameworks();
  }, 300);
}

function onPageChange(page: number) {
  currentPage.value = page;
  loadFrameworks();
}

function onPageSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  loadFrameworks();
}

// ── search ──
const searchQuery = ref('');

// ── view mode ──
const viewMode = ref<'grid' | 'list'>('grid');

// ── pagination ──
const currentPage = ref(1);
const pageSize = ref(12);
const pageSizes = [12, 24, 36];

// ── step 1: upload dialog ──
const showUpload = ref(false);
const uploading = ref(false);
const uploadPercent = ref(0);
const uploadedMeta = ref<FrameworkItem | null>(null);
const uploadRef = ref<InstanceType<typeof ElUpload>>();
const selectedFile = ref<File | null>(null);

// ── parsing dialog ──
const showParsing = ref(false);


function openUpload() {
  uploadedMeta.value = null;
  uploadPercent.value = 0;
  selectedFile.value = null;
  uploadRef.value?.clearFiles();
  showUpload.value = true;
}

function handleFileSelect(file: UploadFile) {
  const raw = file.raw;
  if (raw) {
    selectedFile.value = raw;
  }
}

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;  // 500 MiB, matches backend THIRDPARTY_AGENT_INSTALLER_MAX_BYTES

async function startUpload() {
  if (!selectedFile.value) return;
  if (selectedFile.value.size > MAX_UPLOAD_BYTES) {
    ElMessage.error(`文件大小超过限制（最大 500 MB）`);
    return;
  }
  uploading.value = true;
  uploadPercent.value = 0;
  showUpload.value = false;
  showParsing.value = true;
  try {
    uploadPercent.value = 30;
    uploadedMeta.value = await uploadPackage(selectedFile.value);
    uploadPercent.value = 100;
    showParsing.value = false;
    showConfirm.value = true;
    form.value.agent_name = uploadedMeta.value.agent_name;
    form.value.version = uploadedMeta.value.version;
    form.value.display_name = uploadedMeta.value.display_name;
    form.value.entrypoint = uploadedMeta.value.entrypoint;
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败');
    uploadRef.value?.clearFiles();
    selectedFile.value = null;
    showParsing.value = false;
    await loadFrameworks();
  } finally {
    uploading.value = false;
  }
}

// ── step 2: confirm dialog ──
const showConfirm = ref(false);
const form = ref({ agent_name: '', version: '', display_name: '', entrypoint: '' });

// ── step 3: create (build) dialog ──
const showBuild = ref(false);
const building = ref(false);
const buildTaskId = ref('');
const buildStatus = ref<BuildTaskStatus | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;

async function confirmBuild() {
  buildStatus.value = null;
  showConfirm.value = false;
  showBuild.value = true;
  building.value = true;
  try {
    const { task_id } = await triggerBuild({
      ...form.value,
      display_name: uploadedMeta.value?.display_name || form.value.display_name,
    });
    buildTaskId.value = task_id;
    startPolling(task_id);
  } catch (e: any) {
    ElMessage.error(e.message || '构建失败');
    showBuild.value = false;
    building.value = false;
    await loadFrameworks();
  }
}

function startPolling(taskId: string) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      buildStatus.value = await getBuildStatus(taskId);
      if (buildStatus.value.status !== 'done' && buildStatus.value.status !== 'failed') {
        return;
      }
      clearInterval(pollTimer!);
      building.value = false;
      loadFrameworks();
    } catch {
      // retry on next tick
    }
  }, 2000);
}

function closeBuild() {
  if (pollTimer) clearInterval(pollTimer);
  showBuild.value = false;
  building.value = false;
  buildStatus.value = null;
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (searchTimer) clearTimeout(searchTimer);
});

onMounted(loadFrameworks);
</script>

<template>
  <section class="framework-page">
    <div class="framework-page__header">
      <h1 class="framework-page__title">三方Agent管理</h1>
      <ElButton type="primary" :icon="Plus" @click="openUpload">接入新框架</ElButton>
    </div>

    <!-- Toolbar: search + view toggle -->
    <div class="framework-page__toolbar">
      <ElInput
        v-model="searchQuery"
        placeholder="请输入搜索内容"
        :prefix-icon="Search"
        class="framework-page__search"
        @input="onSearchInput"
      />
      <div class="framework-page__toggle">
        <button
          class="framework-page__toggle-btn"
          :class="{ 'framework-page__toggle-btn--active': viewMode === 'grid' }"
          @click="viewMode = 'grid'"
        >
          <img :src="gridViewIcon" alt="网格视图" class="framework-page__toggle-icon" />
        </button>
        <button
          class="framework-page__toggle-btn"
          :class="{ 'framework-page__toggle-btn--active': viewMode === 'list' }"
          @click="viewMode = 'list'"
        >
          <img :src="listViewIcon" alt="列表视图" class="framework-page__toggle-icon" />
        </button>
      </div>
    </div>

    <!-- Card area -->
    <div v-loading="loading" class="framework-page__cards" :class="`framework-page__cards--${viewMode}`">
      <template v-if="frameworks.length > 0">
        <FrameworkCard
          v-for="item in frameworks"
          :key="item.agent_name"
          :framework="item"
          :mode="viewMode"
        />
      </template>
      <div v-else class="framework-page__empty">暂无已接入框架</div>
    </div>

    <!-- Pagination -->
    <div v-if="total > pageSize" class="framework-page__pagination">
      <ElPagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="pageSizes"
        :total="total"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="onPageChange"
        @size-change="onPageSizeChange"
      />
    </div>

    <!-- Upload dialog -->
    <ElDialog v-model="showUpload" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-title">接入新智能体</span>
          <button class="dialog-close" @click="showUpload = false">
            <img :src="closeDialogIcon" alt="关闭" />
          </button>
        </div>
      </template>
      <div class="dialog-body">
        <p class="dialog-desc">上传第三方智能体NPM安装包，系统将自动识别智能体信息并完成接入配置</p>
        <div class="upload-zone">
          <img :src="uploadIcon" alt="上传" class="upload-zone__icon" />
          <span class="upload-zone__text">
            {{ selectedFile ? selectedFile.name : '将文件拖到此处或单击上传' }}
          </span>
          <span class="upload-zone__hint">支持tar.gz、tgz</span>
          <ElUpload
            ref="uploadRef"
            :auto-upload="false"
            :on-change="handleFileSelect"
            accept=".tgz,.tar.gz"
            :limit="1"
            :show-file-list="false"
            class="upload-zone__input"
          >
            <span class="upload-zone__trigger"></span>
          </ElUpload>
        </div>
        <div v-if="uploading" class="upload-progress">
          <ElProgress :percentage="uploadPercent" :show-text="uploadPercent > 0" />
          <span class="upload-progress__text">正在上传并解析框架包…</span>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <button class="btn-cancel" @click="showUpload = false">取消</button>
          <button class="btn-primary" :disabled="!selectedFile" @click="startUpload">上传</button>
        </div>
      </template>
    </ElDialog>

    <!-- Parsing dialog -->
    <ElDialog v-model="showParsing" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-title">接入新智能体</span>
          <button class="dialog-close" @click="showParsing = false">
            <img :src="closeDialogIcon" alt="关闭" />
          </button>
        </div>
      </template>
      <div class="dialog-body dialog-body--center">
        <p class="dialog-desc">上传第三方智能体NPM安装包，系统将自动识别智能体信息并完成接入配置</p>
        <div class="parsing-content">
          <img :src="parsingIcon" alt="解析中" class="parsing-icon" />
          <span class="parsing-text">解析文件中</span>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <button class="btn-cancel" @click="showParsing = false">取消</button>
        </div>
      </template>
    </ElDialog>

    <!-- Confirm dialog -->
    <ElDialog v-model="showConfirm" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-title">确认智能体信息</span>
          <button class="dialog-close" @click="showConfirm = false">
            <img :src="closeDialogIcon" alt="关闭" />
          </button>
        </div>
      </template>
      <div class="dialog-body">
        <p class="dialog-desc">已成功识别以下智能体信息，请确认后创建。</p>
        <div class="confirm-form">
          <div class="confirm-form__row">
            <label class="confirm-form__label">智能体名称</label>
            <div class="confirm-form__input confirm-form__input--disabled">{{ form.display_name }}</div>
          </div>
          <div class="confirm-form__row">
            <label class="confirm-form__label">版本</label>
            <div class="confirm-form__input confirm-form__input--disabled">v{{ form.version }}</div>
          </div>
          <div class="confirm-form__row">
            <label class="confirm-form__label">启动命令</label>
            <input
              v-model="form.entrypoint"
              class="confirm-form__input"
              :class="{ 'confirm-form__input--disabled': uploadedMeta?.entrypoint }"
              :disabled="!!uploadedMeta?.entrypoint"
            />
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <button class="btn-cancel" @click="showConfirm = false">取消</button>
          <button class="btn-primary" @click="confirmBuild">确认</button>
        </div>
      </template>
    </ElDialog>

    <!-- Create dialog -->
    <ElDialog v-model="showBuild" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <span class="dialog-title">创建智能体</span>
      </template>
      <div class="dialog-body dialog-body--center">
        <p v-if="building" class="dialog-desc">正在配置第三方智能体并完成接入，请勿关闭当前页面。</p>
        <div v-if="building" class="create-content">
          <ElProgress :percentage="buildStatus?.progress ?? 0" style="width: 60%" />
          <span class="create-text">正在创建智能体……</span>
        </div>
        <div v-else-if="buildStatus" class="create-result">
          <template v-if="buildStatus.status === 'done'">
            <span class="create-result__success">创建成功</span>
            <span v-if="buildStatus.image" class="create-result__image">镜像: {{ buildStatus.image }}</span>
          </template>
          <template v-else-if="buildStatus.status === 'failed'">
            <span class="create-result__error">创建失败</span>
            <span v-if="buildStatus.error_message" class="create-result__detail">{{ buildStatus.error_message }}</span>
          </template>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer" v-if="!building">
          <button class="btn-cancel" @click="closeBuild">关闭</button>
        </div>
      </template>
    </ElDialog>
  </section>
</template>

<style scoped>
.framework-page {
  margin: 32px 24px;
}

.framework-page__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.framework-page__title {
  font-size: 20px;
  font-weight: 500;
  margin: 0;
  color: var(--text-primary);
}

</style>
