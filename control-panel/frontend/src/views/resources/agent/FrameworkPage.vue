<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useAuth } from '@/composables/useAuth';
import {
  ElButton,
  ElDialog,
  ElInput,
  ElProgress,
  ElMessage,
  ElMessageBox,
  ElUpload,
  ElPagination,
  vLoading,
} from 'element-plus';
import { Plus, Search } from '@element-plus/icons-vue';
import type { UploadFile } from 'element-plus';
import {
  listCards,
  publishCard,
  getUnregistered,
  listUnregistered,
  retryUnregistered,
  deleteUnregistered,
  getCard,
  deleteCard,
  setDefaultVersion,
  type CardItem,
  type UnregisteredItem,
} from '@/api/framework';
import FrameworkCard from './FrameworkCard.vue';
import gridViewIcon from '@/assets/images/framework-page/grid-view-icon.png';
import listViewIcon from '@/assets/images/framework-page/list-view-icon.png';
import uploadIcon from '@/assets/images/framework-page/upload-icon.png';
import closeDialogIcon from '@/assets/images/framework-page/close-icon.png';

defineOptions({
  directives: {
    loading: vLoading,
  },
});

const { effectiveIsAdmin: isAdmin } = useAuth();
const frameworks = ref<CardItem[]>([]);
const unregistered = ref<UnregisteredItem[]>([]);
const total = ref(0);
const loading = ref(false);
let searchTimer: ReturnType<typeof setTimeout> | null = null;
const searchQuery = ref('');
const viewMode = ref<'grid' | 'list'>('grid');
const currentPage = ref(1);
const pageSize = ref(12);
const pageSizes = [12, 24, 36];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

async function loadFrameworks() {
  loading.value = true;
  try {
    const result = await listCards({
      framework: searchQuery.value.trim(),
      size: pageSize.value,
      page: currentPage.value,
    });
    frameworks.value = result.items;
    total.value = result.total;
    if (isAdmin.value) {
      const pending = await listUnregistered();
      unregistered.value = pending.items;
    } else {
      unregistered.value = [];
    }
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '加载失败'));
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

const showUpload = ref(false);
const uploadRef = ref<InstanceType<typeof ElUpload>>();
const selectedFile = ref<File | null>(null);
const launchCommand = ref('');
const showBuild = ref(false);
const building = ref(false);
const buildProgress = ref(0);
const buildError = ref('');
let pollTimer: ReturnType<typeof setInterval> | null = null;
const showDetail = ref(false);
const detail = ref<CardItem | null>(null);

function openUpload() {
  launchCommand.value = '';
  selectedFile.value = null;
  uploadRef.value?.clearFiles();
  showUpload.value = true;
}

function handleFileSelect(file: UploadFile) {
  const raw = file.raw;
  if (!raw) return;
  selectedFile.value = raw;
}

async function startUpload() {
  if (!selectedFile.value) return;
  const command = launchCommand.value.trim();
  if (!command) {
    ElMessage.error('请填写启动 Agent 的命令');
    return;
  }
  // TODO(spec-contract): read this limit from the backend specification API
  // once available; the backend remains the source of truth meanwhile.
  if (selectedFile.value.size > 500 * 1024 * 1024) {
    ElMessage.error('文件大小超过限制（最大 500 MB）');
    return;
  }
  showUpload.value = false;
  showBuild.value = true;
  building.value = true;
  buildProgress.value = 0;
  buildError.value = '';
  try {
    const accepted = await publishCard(selectedFile.value, command);
    startPolling(accepted.digest);
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '上架失败'));
    showBuild.value = false;
    building.value = false;
  }
}

function startPolling(digest: string) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const st = await getUnregistered(digest);
      buildProgress.value = st.progress ?? 0;
      if (st.last_error && !st.locked) {
        clearInterval(pollTimer!);
        building.value = false;
        buildError.value = st.last_error;
        loadFrameworks();
        return;
      }
      if (!st.locked && !st.last_error) {
        clearInterval(pollTimer!);
        building.value = false;
        showBuild.value = false;
        ElMessage.success('上架成功');
        loadFrameworks();
      }
    } catch {
      clearInterval(pollTimer!);
      building.value = false;
      showBuild.value = false;
      loadFrameworks();
    }
  }, 2000);
}

async function openDetail(card: CardItem) {
  try {
    detail.value = await getCard(card.framework, card.framework_version);
    showDetail.value = true;
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '加载详情失败'));
  }
}

async function markDefault() {
  if (!detail.value) return;
  try {
    await setDefaultVersion(detail.value.framework, detail.value.framework_version);
    ElMessage.success('已设为默认版本');
    showDetail.value = false;
    loadFrameworks();
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '设置失败'));
  }
}

function highestOtherVersion(cards: CardItem[], framework: string, version: string): string | null {
  const others = cards
    .filter((c) => c.framework === framework && c.framework_version !== version)
    .map((c) => c.framework_version);
  if (!others.length) return null;
  return others.reduce((a, b) => (compareSemanticVersions(a, b) > 0 ? a : b));
}

function compareSemanticVersions(left: string, right: string): number {
  const parse = (value: string) => {
    const match = value
      .trim()
      .match(/^[vV]?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/);
    if (!match) return null;
    return { core: match[1].split('.').map(Number), prerelease: match[2]?.split('.') ?? null };
  };
  const a = parse(left);
  const b = parse(right);
  if (!a || !b) {
    if (a) return 1;
    if (b) return -1;
    return left.localeCompare(right);
  }
  const coreLength = Math.max(a.core.length, b.core.length, 3);
  for (let index = 0; index < coreLength; index += 1) {
    const difference = (a.core[index] ?? 0) - (b.core[index] ?? 0);
    if (difference) return difference;
  }
  if (!a.prerelease && !b.prerelease) return 0;
  if (!a.prerelease) return 1;
  if (!b.prerelease) return -1;
  const prereleaseLength = Math.max(a.prerelease.length, b.prerelease.length);
  for (let index = 0; index < prereleaseLength; index += 1) {
    const aPart = a.prerelease[index];
    const bPart = b.prerelease[index];
    if (aPart == null) return -1;
    if (bPart == null) return 1;
    if (aPart === bPart) continue;
    const aNumeric = /^\d+$/.test(aPart);
    const bNumeric = /^\d+$/.test(bPart);
    if (aNumeric && bNumeric) return Number(aPart) - Number(bPart);
    if (aNumeric) return -1;
    if (bNumeric) return 1;
    return aPart.localeCompare(bPart);
  }
  return 0;
}

async function confirmDeleteDefault(framework: string, version: string): Promise<boolean> {
  let successor: string | null;
  try {
    const listed = await listCards({ framework, size: -1, page: 1 });
    successor = highestOtherVersion(listed.items, framework, version);
  } catch {
    successor = highestOtherVersion(frameworks.value, framework, version);
  }
  const message = successor
    ? `当前是默认版本。点「是」将直接删除，并把默认切换为 v${successor}（其余版本中版本号最高的）。点「否」可先手动指定默认版本再删除。`
    : '当前是默认版本，且没有其他版本。确定删除该卡片吗？';
  try {
    await ElMessageBox.confirm(message, '删除默认版本', {
      confirmButtonText: '是',
      cancelButtonText: '否',
      type: 'warning',
    });
    return true;
  } catch {
    return false;
  }
}

async function removeCard() {
  if (!detail.value) return;
  if (detail.value.is_default) {
    const ok = await confirmDeleteDefault(detail.value.framework, detail.value.framework_version);
    if (!ok) return;
  }
  try {
    await deleteCard(detail.value.framework, detail.value.framework_version);
    ElMessage.success('已拆除');
    showDetail.value = false;
    loadFrameworks();
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '删除失败'));
  }
}

async function retryPending(item: UnregisteredItem) {
  try {
    const { value } = await ElMessageBox.prompt('失败包不会保存启动命令，请重新填写启动 Agent 的命令。', '重新构建', {
      confirmButtonText: '重新构建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如 opencode',
      inputValidator: (value) => Boolean(value.trim()) || '启动命令不能为空',
    });
    const accepted = await retryUnregistered(item.digest, value.trim());
    showBuild.value = true;
    building.value = true;
    startPolling(accepted.digest);
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '重试失败'));
  }
}

async function dropPending(item: UnregisteredItem) {
  try {
    await deleteUnregistered(item.digest);
    ElMessage.success('已删除未注册包');
    loadFrameworks();
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '删除失败'));
  }
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
      <h1 class="title-l1">三方智能体管理</h1>
      <ElButton v-if="isAdmin" type="primary" :icon="Plus" @click="openUpload">接入新智能体</ElButton>
    </div>
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
    <div v-loading="loading" class="framework-page__cards" :class="`framework-page__cards--${viewMode}`">
      <template v-if="frameworks.length > 0">
        <FrameworkCard
          v-for="item in frameworks"
          :key="item.framework + item.framework_version"
          :card="item"
          :mode="viewMode"
          :clickable="isAdmin"
          @click="isAdmin && openDetail(item)"
        />
      </template>
      <div v-else class="framework-page__empty">暂无已接入智能体</div>
    </div>
    <div v-if="total > pageSize" class="framework-page__pagination">
      <ElPagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="pageSizes"
        :total="total"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="
          (p: number) => {
            currentPage = p;
            loadFrameworks();
          }
        "
        @size-change="
          (s: number) => {
            pageSize = s;
            currentPage = 1;
            loadFrameworks();
          }
        "
      />
    </div>

    <section v-if="isAdmin" class="pending-box">
      <h2 class="pending-box__title">未注册包</h2>
      <div v-if="unregistered.length" class="pending-list">
        <div v-for="item in unregistered" :key="item.digest" class="pending-row">
          <span class="pending-row__digest" :title="item.digest">{{ item.original_filename }}</span>
          <span class="pending-row__status">{{ item.last_error || (item.locked ? '构建中' : '待处理') }}</span>
          <span class="pending-row__actions">
            <ElButton size="small" :disabled="item.locked" @click="retryPending(item)">重新构建</ElButton>
            <ElButton size="small" :disabled="item.locked" @click="dropPending(item)">删除</ElButton>
          </span>
        </div>
      </div>
      <div v-else class="pending-box__empty">暂无未注册包</div>
    </section>

    <ElDialog v-model="showUpload" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-title">接入新智能体</span>
          <button class="dialog-close" @click="showUpload = false"><img :src="closeDialogIcon" alt="关闭" /></button>
        </div>
      </template>
      <div class="dialog-body">
        <p class="dialog-desc">上传三方智能体 npm 二进制包，并填写启动 Agent 的命令。</p>
        <ElInput v-model="launchCommand" placeholder="启动命令（必填），例如 opencode" maxlength="512" />
        <p class="dialog-desc">当前启动命令同时作为框架名，请确认与实际可执行命令一致。</p>
        <ElUpload
          ref="uploadRef"
          class="upload-zone"
          drag
          :auto-upload="false"
          :show-file-list="false"
          :on-change="handleFileSelect"
        >
          <img :src="uploadIcon" alt="上传" class="upload-zone__icon" />
          <span class="upload-zone__text">{{ selectedFile ? selectedFile.name : '将文件拖到此处或单击上传' }}</span>
          <span class="upload-zone__hint">上传制品；当前构建 Recipe 支持 npm tgz</span>
        </ElUpload>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <ElButton class="dialog-footer__btn" @click="showUpload = false">取消</ElButton>
          <ElButton
            type="primary"
            class="dialog-footer__btn"
            :disabled="!selectedFile || !launchCommand.trim()"
            @click="startUpload"
          >
            上架
          </ElButton>
        </div>
      </template>
    </ElDialog>

    <ElDialog v-model="showBuild" width="452px" :close-on-click-modal="false" :show-close="false">
      <template #header><span class="dialog-title">上架智能体</span></template>
      <div class="dialog-body dialog-body--center">
        <div v-if="building" class="create-content">
          <ElProgress :percentage="buildProgress" style="width: 60%" />
          <span class="create-text">正在构建并注册……</span>
        </div>
        <div v-else-if="buildError" class="create-result">
          <span class="create-result__error">上架失败</span>
          <span class="create-result__detail">{{ buildError }}</span>
        </div>
      </div>
      <template #footer>
        <div v-if="!building" class="dialog-footer">
          <button class="btn-cancel" @click="showBuild = false">关闭</button>
        </div>
      </template>
    </ElDialog>

    <ElDialog v-model="showDetail" width="520px" :show-close="true">
      <template #header><span class="dialog-title">卡片详情</span></template>
      <div v-if="detail" class="dialog-body">
        <p>{{ detail.framework }} · v{{ detail.framework_version }}{{ detail.is_default ? ' · 默认版本' : '' }}</p>
        <p v-if="isAdmin">实例总数 {{ detail.total_instances ?? 0 }} · 运行中 {{ detail.running_instances ?? 0 }}</p>
        <p v-if="isAdmin && detail.package_path">包路径：{{ detail.package_path }}</p>
      </div>
      <template #footer>
        <div v-if="isAdmin" class="dialog-footer">
          <button class="btn-cancel" @click="removeCard">删除卡片</button>
          <button v-if="!detail?.is_default" class="btn-cancel" @click="markDefault">设为默认</button>
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
}
.framework-page__toggle-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  background: transparent;
  padding: 0;
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
.framework-page__pagination {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
.pending-box {
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}
.pending-box__title {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 12px;
  color: var(--text-primary);
}
.pending-box__empty {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 16px 0;
}
.pending-list {
  display: flex;
  flex-direction: column;
}
.pending-row {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.pending-row__digest {
  flex: 0 0 120px;
  font-family: monospace;
  color: var(--text-primary);
}
.pending-row__status {
  flex: 1;
  color: var(--text-secondary);
  word-break: break-all;
}
.pending-row__actions {
  flex-shrink: 0;
}
:deep(.el-dialog) {
  border-radius: 8px;
}
:deep(.el-dialog__header),
:deep(.el-dialog__body),
:deep(.el-dialog__footer) {
  padding: 0;
  margin: 0;
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
}
.dialog-close {
  width: 14px;
  height: 14px;
  border: none;
  background: none;
  cursor: pointer;
  padding: 0;
}
.dialog-close img {
  width: 14px;
  height: 14px;
}
.dialog-body {
  padding: 8px 24px 0 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dialog-body--center {
  align-items: center;
}
.dialog-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 24px;
  flex-wrap: wrap;
}
.btn-cancel,
.btn-primary {
  min-width: 88px;
  height: 32px;
  padding: 0 12px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}
.btn-cancel {
  background: #fff;
  border: 1px solid var(--border);
}
.btn-primary {
  background: var(--color-primary);
  border: none;
  color: #fff;
}
.upload-zone {
  width: 100%;
}
.upload-zone :deep(.el-upload) {
  width: 100%;
}
.upload-zone :deep(.el-upload-dragger) {
  width: 100%;
  height: auto;
  padding: 40px 0;
  background: rgba(25, 25, 25, 0.05);
  border-radius: 4px;
  border: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.upload-zone__icon {
  width: 22px;
  height: 20px;
}
.upload-zone__text {
  font-size: 14px;
  color: var(--text-primary);
}
.upload-zone__hint {
  font-size: 12px;
  color: var(--text-secondary);
}
.create-content,
.create-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 0;
  width: 100%;
}
.create-result__error,
.create-result__detail {
  color: #f56c6c;
}
</style>
