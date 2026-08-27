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
  vLoading,
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

defineOptions({
  directives: {
    loading: vLoading,
  },
});


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
      <h1 class="framework-page__title">三方智能体管理</h1>
      <ElButton type="primary" :icon="Plus" @click="openUpload">接入新智能体</ElButton>
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
        <ElButton
          text
          class="framework-page__toggle-btn"
          :class="{ 'framework-page__toggle-btn--active': viewMode === 'grid' }"
          @click="viewMode = 'grid'"
        >
          <img :src="gridViewIcon" alt="网格视图" class="framework-page__toggle-icon" />
        </ElButton>
        <ElButton
          text
          class="framework-page__toggle-btn"
          :class="{ 'framework-page__toggle-btn--active': viewMode === 'list' }"
          @click="viewMode = 'list'"
        >
          <img :src="listViewIcon" alt="列表视图" class="framework-page__toggle-icon" />
        </ElButton>
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
      <div v-else class="framework-page__empty">暂无已接入智能体</div>
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
          <ElButton text class="dialog-close" @click="showUpload = false">
            <img :src="closeDialogIcon" alt="关闭" />
          </ElButton>
        </div>
      </template>
      <div class="dialog-body">
        <p class="dialog-desc">上传三方智能体NPM安装包，系统将自动识别智能体信息并完成接入配置</p>
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
          <ElButton class="dialog-footer__btn" @click="showUpload = false">取消</ElButton>
          <ElButton type="primary" class="dialog-footer__btn" :disabled="!selectedFile" @click="startUpload">上传</ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- Parsing dialog -->
    <ElDialog v-model="showParsing" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-title">接入新智能体</span>
          <ElButton text class="dialog-close" @click="showParsing = false">
            <img :src="closeDialogIcon" alt="关闭" />
          </ElButton>
        </div>
      </template>
      <div class="dialog-body dialog-body--center">
        <p class="dialog-desc">上传三方智能体NPM安装包，系统将自动识别智能体信息并完成接入配置</p>
        <div class="parsing-content">
          <img :src="parsingIcon" alt="解析中" class="parsing-icon" />
          <span class="parsing-text">解析文件中</span>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <ElButton class="dialog-footer__btn" @click="showParsing = false">取消</ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- Confirm dialog -->
    <ElDialog v-model="showConfirm" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-title">确认智能体信息</span>
          <ElButton text class="dialog-close" @click="showConfirm = false">
            <img :src="closeDialogIcon" alt="关闭" />
          </ElButton>
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
          <ElButton class="dialog-footer__btn" @click="showConfirm = false">取消</ElButton>
          <ElButton type="primary" class="dialog-footer__btn" @click="confirmBuild">确认</ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- Create dialog -->
    <ElDialog v-model="showBuild" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <span class="dialog-title">创建智能体</span>
      </template>
      <div class="dialog-body dialog-body--center">
        <p v-if="building" class="dialog-desc">正在配置三方智能体并完成接入，请勿关闭当前页面。</p>
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
          <ElButton class="dialog-footer__btn" @click="closeBuild">关闭</ElButton>
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

/* ── Toolbar ── */
.framework-page__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
}

.framework-page__search {
  width: 296px;
}

.framework-page__toggle {
  display: flex;
  background: rgba(25, 25, 25, 0.05);
  border-radius: 6px;
  padding: 2px;
  gap: 0;
}

.framework-page__toggle-btn {
  width: 28px;
  height: 28px;
  min-height: 28px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
}

.framework-page__toggle-btn--active {
  background: #ffffff;
  box-shadow: 0px 1px 6px 0px rgba(0, 0, 0, 0.08);
}

.framework-page__toggle-icon {
  width: 16px;
  height: 16px;
  display: block;
  object-fit: contain;
}

/* ── Card area ── */
.framework-page__cards--grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-top: 20px;
}

.framework-page__cards--list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 20px;
}

.framework-page__empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--text-secondary);
  padding: 48px 0;
  font-size: 14px;
}

/* ── Pagination ── */
.framework-page__pagination {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

/* ── Shared dialog styles ── */
:deep(.el-dialog) {
  border-radius: 8px;
  box-shadow: 0px 16px 48px 0px rgba(0, 0, 0, 0.16);
}

:deep(.el-dialog__header) {
  padding: 0;
  margin: 0;
  color: var(--text-primary);
}

:deep(.el-dialog__body) {
  padding: 0;
}

:deep(.el-dialog__footer) {
  padding: 0;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px 0 24px;
}

.dialog-title {
  font-size: 20px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 28px;
}

.dialog-close {
  width: 14px;
  height: 14px;
  min-height: 14px;
  margin-top: 7px;
  padding: 0;
  border: none;
}

.dialog-close img {
  width: 14px;
  height: 14px;
  display: block;
}

.dialog-body {
  padding: 8px 24px 0 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.dialog-body--center {
  align-items: center;
}

.dialog-desc {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: 22px;
  margin: 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 24px 24px 20px 24px;
}

.dialog-footer__btn {
  width: 88px;
}

/* ── Upload dialog ── */
.upload-zone {
  background: rgba(25, 25, 25, 0.05);
  border-radius: 4px;
  border: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 0;
  cursor: pointer;
  position: relative;
}

.upload-zone__icon {
  width: 22px;
  height: 20px;
  display: block;
}

.upload-zone__text {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 22px;
}

.upload-zone__hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: 20px;
}

.upload-zone__input {
  position: absolute;
  inset: 0;
  opacity: 0;
}

.upload-zone__trigger {
  position: absolute;
  inset: 0;
}

.upload-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.upload-progress__text {
  color: #909399;
  font-size: 13px;
}

/* ── Parsing dialog ── */
.parsing-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px 0 32px 0;
}

.parsing-icon {
  width: 48px;
  height: 48px;
  display: block;
  animation: spin 1.5s linear infinite;
}

.parsing-text {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-placeholder);
  line-height: 22px;
}

/* ── Confirm dialog ── */
.confirm-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.confirm-form__row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.confirm-form__label {
  width: 80px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 22px;
  margin-top: 9px;
  flex-shrink: 0;
}

.confirm-form__input {
  width: 324px;
  height: 40px;
  background: #ffffff;
  border-radius: 4px;
  border: 1px solid var(--border);
  padding: 9px 12px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 22px;
  font-family: inherit;
}

.confirm-form__input--disabled {
  background: #f5f5f5;
  color: var(--text-primary);
}

/* ── Create dialog ── */
.create-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px 0 8px 0;
  width: 100%;
}

.create-text {
  font-size: 14px;
  font-weight: 400;
  color: var(--text-placeholder);
  line-height: 22px;
}

.create-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 0;
}

.create-result__success {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 22px;
}

.create-result__error {
  font-size: 14px;
  font-weight: 500;
  color: #f56c6c;
  line-height: 22px;
}

.create-result__image {
  font-size: 13px;
  color: #606266;
}

.create-result__detail {
  font-size: 13px;
  color: #f56c6c;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
