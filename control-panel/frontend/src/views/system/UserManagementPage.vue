<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import {
  ElTable,
  ElTableColumn,
  ElPagination,
  ElDialog,
  ElMessage,
  ElMessageBox,
  ElTooltip,
  ElNotification,
  ElIcon,
  ElPopover,
} from 'element-plus';
import { View, Hide, Filter } from '@element-plus/icons-vue';
import {
  getUsers,
  batchCreateUsers,
  resetUserPassword,
  deleteUser,
  type UserItem,
  type BatchCreateResult,
} from '@/api/users';
import userAvatar from '@/assets/images/person.svg';
import docIcon from '@/assets/images/doc.svg';
import keyIcon from '@/assets/images/key.svg';
import deleteIcon from '@/assets/images/delete.svg';
import closeIcon from '@/assets/images/close.svg';
import copyIcon from '@/assets/images/copy.svg';
import searchIcon from '@/assets/images/search.svg';
import warningIcon from '@/assets/images/warning.svg';

const users = ref<UserItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const search = ref('');
const listLoading = ref(false);
const selectedRows = ref<UserItem[]>([]);

const sortKey = ref('created_at');
const sortOrder = ref<'asc' | 'desc'>('desc');
const roleFilter = ref('');
const isActiveFilter = ref<string | null>(null); // null=all, 'true'=online, 'false'=offline
const showBatchModal = ref(false);
const batchResults = ref<BatchCreateResult[]>([]);
const batchLoading = ref(false);
const batchFileInput = ref<HTMLInputElement | null>(null);
const batchUploadError = ref('');

interface ResetResult {
  username: string;
  role: string;
  user_id: string;
  new_password: string;
}
const showResetModal = ref(false);
const resetResult = ref<ResetResult | null>(null);
const resetLoading = ref(false);
const resetTarget = ref<UserItem | null>(null);
const passwordVisible = ref(false);

const showCreateModal = ref(false);
const createUsername = ref('');
const createLoading = ref(false);
const createError = ref('');
const createdUser = ref<{ username: string; user_id: string; new_password: string } | null>(null);
const createdPasswordVisible = ref(false);

const USERNAME_RE = /^[a-z0-9_-]{3,32}$/;

function openCreateModal() {
  createUsername.value = '';
  createError.value = '';
  createdUser.value = null;
  showCreateModal.value = true;
}

function closeCreateModal() {
  showCreateModal.value = false;
  createUsername.value = '';
  createError.value = '';
  createdUser.value = null;
  createdPasswordVisible.value = false;
}

async function handleCreateUser() {
  const username = createUsername.value.trim();
  if (!USERNAME_RE.test(username)) {
    createError.value = '用户名需为 3-32 位小写字母、数字、下划线或连字符';
    return;
  }
  createError.value = '';
  createLoading.value = true;
  try {
    const results = await batchCreateUsers([username]);
    const ok = results.find((r) => !r.error);
    if (ok) {
      createdUser.value = {
        username: ok.username,
        user_id: ok.user_id ?? '',
        new_password: ok.password ?? '',
      };
    } else {
      createError.value = results[0]?.error ?? '创建失败';
    }
  } catch (e) {
    createError.value = e instanceof Error ? e.message : '创建失败';
  } finally {
    createLoading.value = false;
  }
}

function downloadCredentials(
  records: Array<{
    username: string;
    user_id: string | null;
    password: string | null;
    error?: string | null;
  }>,
  filename?: string,
) {
  if (!records.length) return;
  const headers = ['username', 'user_id', 'password', 'error'];
  const escape = (v: string | null | undefined) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = records.map((r) =>
    headers.map((h) => escape((r as Record<string, string | null | undefined>)[h])).join(','),
  );
  const csv = '﻿' + [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename ?? `credentials-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  ElNotification.success('用户凭证下载成功');
}

function downloadResetCredential() {
  if (!resetResult.value) return;
  const r = resetResult.value;
  downloadCredentials(
    [{ username: r.username, user_id: r.user_id, password: r.new_password }],
    `credential-${r.username}-${Date.now()}.csv`,
  );
}

function downloadCreateCredential() {
  if (!createdUser.value) return;
  const r = createdUser.value;
  downloadCredentials(
    [{ username: r.username, user_id: r.user_id, password: r.new_password }],
    `credential-${r.username}-${Date.now()}.csv`,
  );
}

function completeCreate() {
  closeCreateModal();
  loadUsers();
}

const jumpPage = ref('');

async function loadUsers() {
  listLoading.value = true;
  try {
    const data = await getUsers({
      page: page.value,
      page_size: pageSize.value,
      search: search.value || undefined,
      sort: sortKey.value,
      order: sortOrder.value,
      role: roleFilter.value || undefined,
      is_active: isActiveFilter.value,
    });
    users.value = data.items;
    total.value = data.total;
    selectedRows.value = [];
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载用户列表失败');
  } finally {
    listLoading.value = false;
  }
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (!order) {
    sortKey.value = 'created_at';
    sortOrder.value = 'desc';
  } else {
    sortKey.value = prop;
    sortOrder.value = order === 'ascending' ? 'asc' : 'desc';
  }
  page.value = 1;
  loadUsers();
}

function handleSearch() {
  page.value = 1;
  loadUsers();
}

function handleRoleFilter() {
  page.value = 1;
  loadUsers();
}

function handleActiveFilter() {
  page.value = 1;
  loadUsers();
}

function handleSelectionChange(rows: UserItem[]) {
  selectedRows.value = rows;
}

function handleJumpPage() {
  const target = Number(jumpPage.value);
  if (!Number.isFinite(target) || target < 1) {
    ElMessage.warning('请输入有效的页码');
    return;
  }
  const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value));
  if (target > maxPage) {
    ElMessage.warning(`页码超出范围，最大为 ${maxPage}`);
    return;
  }
  page.value = target;
  jumpPage.value = '';
}

watch(page, () => loadUsers());
watch(pageSize, () => {
  if (page.value === 1) {
    loadUsers();
  } else {
    page.value = 1;
  }
});

onMounted(() => loadUsers());

function openBatchModal() {
  batchResults.value = [];
  batchUploadError.value = '';
  showBatchModal.value = true;
}

function triggerFileUpload() {
  batchFileInput.value?.click();
}

function parseCsvFile(file: File): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      const raw = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
      const lines = raw.split(/\r?\n/).filter((l) => l.trim());
      // Skip header row, extract username column, keep empty strings so API returns errors for them
      const names = lines.slice(1).map((line) => line.split(',')[0]?.trim() ?? '');
      if (!names.length) {
        reject(new Error('文件中没有找到有效的用户名'));
        return;
      }
      if (names.length > 100) {
        reject(new Error(`单次最多导入 100 个用户，当前文件包含 ${names.length} 个用户名`));
        return;
      }
      resolve(names);
    };
    reader.onerror = () => reject(new Error('读取文件失败'));
    reader.readAsText(file, 'UTF-8');
  });
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  batchUploadError.value = '';

  if (!file.name.endsWith('.csv')) {
    batchUploadError.value = '仅支持 .csv 格式的文件';
    input.value = '';
    return;
  }

  batchLoading.value = true;
  batchResults.value = [];
  try {
    const names = await parseCsvFile(file);
    batchResults.value = await batchCreateUsers(names);
  } catch (e) {
    batchUploadError.value = e instanceof Error ? e.message : '批量创建失败';
    ElMessage.error(batchUploadError.value);
  } finally {
    batchLoading.value = false;
    input.value = '';
  }
}

function handleBatchDragOver(event: DragEvent) {
  event.preventDefault();
}

function handleBatchDrop(event: DragEvent) {
  event.preventDefault();
  const file = event.dataTransfer?.files?.[0];
  if (!file) return;

  batchUploadError.value = '';

  if (!file.name.endsWith('.csv')) {
    batchUploadError.value = '仅支持 .csv 格式的文件';
    return;
  }

  batchLoading.value = true;
  batchResults.value = [];
  parseCsvFile(file)
    .then((names) => batchCreateUsers(names))
    .then((results) => {
      batchResults.value = results;
    })
    .catch((e) => {
      batchUploadError.value = e instanceof Error ? e.message : '批量创建失败';
      ElMessage.error(batchUploadError.value);
    })
    .finally(() => {
      batchLoading.value = false;
    });
}

function downloadTemplate() {
  const csv = '用户名,\nexample_user,\n';
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'user-import-template.csv';
  a.click();
  URL.revokeObjectURL(url);
  ElNotification.success('用户导入模板下载成功');
}

function downloadCsv() {
  if (!batchResults.value.length) return;
  downloadCredentials(
    batchResults.value.map((r) => ({
      username: r.username,
      user_id: r.user_id,
      password: r.password,
      error: r.error,
    })),
    `batch-create-results-${Date.now()}.csv`,
  );
}

async function copyToClipboard(text: string, label = '已复制到剪贴板') {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success(label);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    ElMessage.success(label);
  }
}

function confirmResetPassword(user: UserItem) {
  resetTarget.value = user;
}

async function handleConfirmReset() {
  if (!resetTarget.value) return;

  const target = resetTarget.value;
  resetLoading.value = true;
  try {
    const r = await resetUserPassword(target.user_id);
    resetResult.value = {
      username: r.username || target.username,
      role: target.role,
      user_id: r.user_id,
      new_password: r.new_password,
    };
    resetTarget.value = null;
    showResetModal.value = true;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败');
    resetTarget.value = null;
  } finally {
    resetLoading.value = false;
  }
}

function closeResetConfirm() {
  resetTarget.value = null;
}

function closeResetResult() {
  showResetModal.value = false;
  resetResult.value = null;
  passwordVisible.value = false;
}

async function handleDelete(user: UserItem) {
  try {
    await ElMessageBox.confirm(`确定要删除用户 ${user.username} 吗？此操作不可撤销。`, '删除用户', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
  } catch {
    return;
  }

  try {
    await deleteUser(user.user_id);
    ElMessage.success('删除成功');
    loadUsers();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败');
  }
}

function roleLabel(role: string) {
  return role === 'admin' ? '管理员' : '普通用户';
}

function formatDate(iso: string | null) {
  if (!iso) return '—';
  return iso.slice(0, 19).replace('T', ' ');
}
</script>

<template>
  <section class="page user-mgmt">
    <h1 class="page-title user-mgmt__title">用户管理</h1>

    <div class="user-mgmt__card">
      <div class="user-mgmt__toolbar">
        <div class="user-mgmt__search">
          <img :src="searchIcon" alt="" class="user-mgmt__search-icon" />
          <input
            v-model="search"
            type="text"
            class="user-mgmt__search-input"
            placeholder="请输入搜索内容"
            @keyup.enter="handleSearch"
          />
        </div>

        <div class="user-mgmt__actions">
          <button class="user-mgmt__btn user-mgmt__btn--secondary" @click="openBatchModal">批量导入</button>
          <button class="user-mgmt__btn user-mgmt__btn--primary" @click="openCreateModal">创建用户</button>
        </div>
      </div>

      <div class="user-mgmt__table-area">
        <div v-if="listLoading" class="table-loading-overlay">
          <span class="table-loading-spinner" />
        </div>
        <ElTable
          :data="users"
          row-key="user_id"
          class="user-mgmt__table"
          empty-text="暂无数据"
          @selection-change="handleSelectionChange"
          @sort-change="handleSortChange"
        >
          <ElTableColumn type="selection" width="48" />
          <ElTableColumn label="用户名" min-width="180" prop="username" sortable="custom">
            <template #default="{ row }">
              <div class="user-cell">
                <img :src="userAvatar" :alt="row.username" class="user-cell__avatar" />
                <span>{{ row.username }}</span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="user_id" label="用户ID" min-width="180">
            <template #default="{ row }">
              <span class="cell-mono">{{ row.user_id }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn min-width="160">
            <template #header>
              <div class="role-header">
                <span>用户角色</span>
                <ElPopover placement="bottom" :width="120" trigger="click">
                  <template #reference>
                    <ElIcon :size="14" :class="{ 'role-filter-icon--active': roleFilter }" class="role-filter-icon"><Filter /></ElIcon>
                  </template>
                  <div class="role-filter-popover">
                    <div class="role-filter-option" :class="{ 'role-filter-option--active': !roleFilter }" @click="roleFilter = ''; handleRoleFilter()">全部角色</div>
                    <div class="role-filter-option" :class="{ 'role-filter-option--active': roleFilter === 'admin' }" @click="roleFilter = 'admin'; handleRoleFilter()">管理员</div>
                    <div class="role-filter-option" :class="{ 'role-filter-option--active': roleFilter === 'user' }" @click="roleFilter = 'user'; handleRoleFilter()">普通用户</div>
                  </div>
                </ElPopover>
              </div>
            </template>
            <template #default="{ row }">
              <span class="role-tag" :class="row.role === 'admin' ? 'role-tag--admin' : 'role-tag--user'">
                {{ roleLabel(row.role) }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn min-width="140">
            <template #header>
              <div class="role-header">
                <span>登录状态</span>
                <ElPopover placement="bottom" :width="120" trigger="click">
                  <template #reference>
                    <ElIcon :size="14" :class="{ 'role-filter-icon--active': isActiveFilter !== null }" class="role-filter-icon"><Filter /></ElIcon>
                  </template>
                  <div class="role-filter-popover">
                    <div class="role-filter-option" :class="{ 'role-filter-option--active': isActiveFilter === null }" @click="isActiveFilter = null; handleActiveFilter()">全部</div>
                    <div class="role-filter-option" :class="{ 'role-filter-option--active': isActiveFilter === 'true' }" @click="isActiveFilter = 'true'; handleActiveFilter()">在线</div>
                    <div class="role-filter-option" :class="{ 'role-filter-option--active': isActiveFilter === 'false' }" @click="isActiveFilter = 'false'; handleActiveFilter()">离线</div>
                  </div>
                </ElPopover>
              </div>
            </template>
            <template #default="{ row }">
              <span class="login-status" :class="row.is_active ? 'login-status--online' : 'login-status--offline'">
                <span class="login-status__dot" />
                {{ row.is_active ? '在线' : '离线' }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="最近活跃时间" min-width="180">
            <template #default>—</template>
          </ElTableColumn>
          <ElTableColumn label="创建时间" min-width="180" prop="created_at" sortable="custom">
            <template #default="{ row }">
              <span class="cell-muted">{{ formatDate(row.created_at) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <ElTooltip content="查看详情" placement="top">
                  <button class="row-actions__btn" title="查看详情" @click="ElMessage.info('查看详情功能开发中')">
                    <img :src="docIcon" alt="" width="14" height="14" />
                  </button>
                </ElTooltip>
                <ElTooltip content="重置密码" placement="top">
                  <button class="row-actions__btn" title="重置密码" @click="confirmResetPassword(row)">
                    <img :src="keyIcon" alt="" width="14" height="14" />
                  </button>
                </ElTooltip>
                <ElTooltip content="删除" placement="top">
                  <button class="row-actions__btn" title="删除" @click="handleDelete(row)">
                    <img :src="deleteIcon" alt="" width="14" height="14" />
                  </button>
                </ElTooltip>
              </div>
            </template>
          </ElTableColumn>
        </ElTable>

        <div class="user-mgmt__pagination">
          <span class="user-mgmt__total">总计：{{ total }}</span>

          <ElPagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="sizes, prev, pager, next"
            background
            class="user-mgmt__pager"
          />

          <div class="user-mgmt__jump">
            <span class="user-mgmt__jump-label">跳转</span>
            <input
              v-model="jumpPage"
              type="text"
              class="user-mgmt__jump-input"
              placeholder="1"
              @keyup.enter="handleJumpPage"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 批量导入用户 -->
    <ElDialog v-model="showBatchModal" width="700px" class="batch-dialog" :show-close="false" destroy-on-close>
      <template #header="{ close }">
        <div class="batch-dialog__header">
          <span class="batch-dialog__title">批量创建用户</span>
          <button class="batch-dialog__close" @click="close">
            <img :src="closeIcon" alt="关闭" width="14" height="14" />
          </button>
        </div>
      </template>

      <p class="batch-dialog__desc">
        <a class="batch-dialog__link" @click="downloadTemplate">下载模板</a>
        并填写用户信息，上传后系统将自动校验并生成用户 ID 和初始密码。
      </p>

      <input
        ref="batchFileInput"
        type="file"
        accept=".csv"
        class="batch-dialog__file-input"
        @change="handleFileChange"
      />

      <div
        v-if="!batchLoading && !batchResults.length"
        class="batch-dialog__upload"
        @click="triggerFileUpload"
        @dragover="handleBatchDragOver"
        @drop="handleBatchDrop"
      >
        <span class="batch-dialog__upload-plus">+</span>
        <p class="batch-dialog__upload-text">将文件拖到此处或单击上传</p>
        <p class="batch-dialog__upload-hint">支持 csv，单次最多导入 100 个用户</p>
        <p v-if="batchUploadError" class="create-dialog__error">{{ batchUploadError }}</p>
      </div>

      <div v-if="batchLoading" class="batch-dialog__loading">
        <span class="table-loading-spinner" />
        <p class="batch-dialog__loading-text">批量创建用户中...</p>
      </div>

      <div v-if="batchResults.length" class="batch-results">
        <h3 class="batch-results__title">创建结果</h3>
        <ElTable :data="batchResults" size="small" max-height="220">
          <ElTableColumn label="用户名" min-width="90">
            <template #default="{ row }">
              <code>{{ row.username }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn label="用户ID" min-width="130">
            <template #default="{ row }">
              <span class="cell-mono">{{ row.user_id || '—' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="初始密码" min-width="130">
            <template #default="{ row }">
              <code v-if="row.password">{{ row.password }}</code>
              <span v-else>—</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="70">
            <template #default="{ row }">
              <span class="batch-status" :class="row.error ? 'batch-status--fail' : 'batch-status--ok'">
                {{ row.error ? '失败' : '成功' }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="失败原因" min-width="120">
            <template #default="{ row }">
              <span v-if="row.error" class="error-text">{{ row.error }}</span>
              <span v-else>—</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </div>

      <template #footer>
        <div class="batch-dialog__footer">
          <button
            class="user-mgmt__btn user-mgmt__btn--secondary"
            @click="
              showBatchModal = false;
              if (batchResults.length) loadUsers();
            "
          >
            {{ batchResults.length ? '关闭' : '取消' }}
          </button>
          <button v-if="batchResults.length" class="user-mgmt__btn user-mgmt__btn--secondary" @click="downloadCsv">
            下载用户凭证
          </button>
        </div>
      </template>
    </ElDialog>

    <!-- 重置密码 - 确认 -->
    <ElDialog
      :model-value="!!resetTarget"
      width="560px"
      class="reset-confirm-dialog"
      :show-close="false"
      @update:model-value="(v) => !v && closeResetConfirm()"
    >
      <template #header="{ close }">
        <div class="reset-confirm__header">
          <img :src="warningIcon" alt="" width="20" height="20" class="reset-confirm__warning" />
          <div class="reset-confirm__header-text">
            <p class="reset-confirm__title">确认重置密码？</p>
            <p class="reset-confirm__subtitle">
              重置后，当前密码将立即失效，系统会生成新的临时密码。<br />
              用户需使用新临时密码登录，并在首次登录后修改密码。
            </p>
          </div>
          <button class="batch-dialog__close" @click="close">
            <img :src="closeIcon" alt="关闭" width="14" height="14" />
          </button>
        </div>
      </template>

      <p class="reset-confirm__prompt">确认要重置该用户的密码？</p>

      <div v-if="resetTarget" class="reset-confirm__card">
        <div class="reset-confirm__row">
          <span class="reset-confirm__label">用户名</span>
          <span class="reset-confirm__value">{{ resetTarget.username }}</span>
        </div>
        <div class="reset-confirm__row">
          <span class="reset-confirm__label">用户角色</span>
          <span class="role-tag" :class="resetTarget.role === 'admin' ? 'role-tag--admin' : 'role-tag--user'">
            {{ roleLabel(resetTarget.role) }}
          </span>
        </div>
        <div class="reset-confirm__row">
          <span class="reset-confirm__label">用户 ID</span>
          <div class="reset-confirm__value-wrap">
            <span class="reset-confirm__value">{{ resetTarget.user_id }}</span>
            <button class="row-actions__btn" title="复制" @click="copyToClipboard(resetTarget.user_id)">
              <img :src="copyIcon" alt="" width="14" height="14" />
            </button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="reset-confirm__footer">
          <button class="user-mgmt__btn user-mgmt__btn--secondary" @click="closeResetConfirm">取消</button>
          <button class="user-mgmt__btn user-mgmt__btn--primary" :disabled="resetLoading" @click="handleConfirmReset">
            {{ resetLoading ? '重置中...' : '确定' }}
          </button>
        </div>
      </template>
    </ElDialog>

    <!-- 重置密码 - 结果 -->
    <ElDialog
      v-model="showResetModal"
      width="560px"
      class="reset-result-dialog"
      :show-close="false"
      @closed="resetResult = null"
    >
      <template #header="{ close }">
        <div class="reset-result__header">
          <span class="reset-result__title">密码重置成功</span>
          <button class="batch-dialog__close" @click="close">
            <img :src="closeIcon" alt="关闭" width="14" height="14" />
          </button>
        </div>
      </template>

      <template v-if="resetResult">
        <p class="reset-result__subtitle">新的临时密码仅展示一次，请及时复制或下载并发送给用户。</p>
        <div class="reset-result__card">
          <div class="reset-result__row">
            <span class="reset-result__label">用户名</span>
            <span class="reset-result__value">{{ resetResult.username }}</span>
          </div>
          <div class="reset-result__row">
            <span class="reset-result__label">用户角色</span>
            <span class="role-tag" :class="resetResult.role === 'admin' ? 'role-tag--admin' : 'role-tag--user'">
              {{ roleLabel(resetResult.role) }}
            </span>
          </div>
          <div class="reset-result__row">
            <span class="reset-result__label">用户 ID</span>
            <div class="reset-result__value-wrap">
              <span class="reset-result__value">{{ resetResult.user_id }}</span>
              <button class="row-actions__btn" title="复制" @click="copyToClipboard(resetResult.user_id)">
                <img :src="copyIcon" alt="" width="14" height="14" />
              </button>
            </div>
          </div>
          <div class="reset-result__row reset-result__row--highlight">
            <span class="reset-result__label">初始密码</span>
            <div class="reset-result__value-wrap">
              <span class="reset-result__value reset-result__password">
                {{ passwordVisible ? resetResult.new_password : '••••••••••' }}
              </span>
              <button
                class="row-actions__btn"
                :title="passwordVisible ? '隐藏密码' : '显示密码'"
                @click="passwordVisible = !passwordVisible"
              >
                <ElIcon :size="14">
                  <View v-if="passwordVisible" />
                  <Hide v-else />
                </ElIcon>
              </button>
              <button class="row-actions__btn" title="复制" @click="copyToClipboard(resetResult.new_password)">
                <img :src="copyIcon" alt="" width="14" height="14" />
              </button>
            </div>
          </div>
        </div>
      </template>

      <template #footer>
        <div class="reset-result__footer">
          <button class="user-mgmt__btn user-mgmt__btn--secondary" @click="downloadResetCredential">下载凭证</button>
          <button class="user-mgmt__btn user-mgmt__btn--primary" @click="closeResetResult">完成</button>
        </div>
      </template>
    </ElDialog>

    <!-- 创建用户 - 输入用户名 -->
    <ElDialog
      v-model="showCreateModal"
      width="452px"
      class="create-dialog"
      :show-close="false"
      @closed="closeCreateModal"
    >
      <template #header="{ close }">
        <div class="create-dialog__header">
          <span class="create-dialog__title">创建用户</span>
          <button class="create-dialog__close" @click="close">
            <img :src="closeIcon" alt="关闭" width="14" height="14" />
          </button>
        </div>
      </template>

      <template v-if="!createdUser">
        <p class="create-dialog__desc">请输入用户名，提交后系统将生成用户 ID 和初始密码。</p>

        <div class="create-dialog__field">
          <label class="create-dialog__label">用户名</label>
          <input
            v-model="createUsername"
            type="text"
            class="create-dialog__input"
            placeholder="请输入用户名"
            :disabled="createLoading"
            maxlength="32"
            @keyup.enter="handleCreateUser"
            @input="createError = ''"
          />
          <p class="create-dialog__hint">3-32 位小写字母、数字、下划线或连字符</p>
          <p v-if="createError" class="create-dialog__error">{{ createError }}</p>
        </div>
      </template>

      <template v-else>
        <p class="create-success__subtitle">用户已创建成功，初始密码仅展示一次，请及时复制或下载并发送给用户。</p>
        <div class="create-success__card">
          <div class="create-success__row">
            <span class="create-success__label">用户名</span>
            <span class="create-success__value">{{ createdUser.username }}</span>
          </div>
          <div class="create-success__row">
            <span class="create-success__label">用户 ID</span>
            <div class="create-success__value-wrap">
              <span class="create-success__value">{{ createdUser.user_id }}</span>
              <button class="row-actions__btn" title="复制" @click="copyToClipboard(createdUser.user_id)">
                <img :src="copyIcon" alt="" width="14" height="14" />
              </button>
            </div>
          </div>
          <div class="create-success__row create-success__row--highlight">
            <span class="create-success__label">初始密码</span>
            <div class="create-success__value-wrap">
              <span class="create-success__value create-success__password">
                {{ createdPasswordVisible ? createdUser.new_password : '••••••••••' }}
              </span>
              <button
                class="row-actions__btn"
                :title="createdPasswordVisible ? '隐藏密码' : '显示密码'"
                @click="createdPasswordVisible = !createdPasswordVisible"
              >
                <ElIcon :size="14">
                  <View v-if="createdPasswordVisible" />
                  <Hide v-else />
                </ElIcon>
              </button>
              <button class="row-actions__btn" title="复制" @click="copyToClipboard(createdUser.new_password)">
                <img :src="copyIcon" alt="" width="14" height="14" />
              </button>
            </div>
          </div>
        </div>
      </template>

      <template v-if="!createdUser" #footer>
        <div class="create-dialog__footer">
          <button class="user-mgmt__btn user-mgmt__btn--secondary" @click="closeCreateModal">取消</button>
          <button class="user-mgmt__btn user-mgmt__btn--primary" :disabled="createLoading" @click="handleCreateUser">
            {{ createLoading ? '创建中...' : '确定' }}
          </button>
        </div>
      </template>

      <template v-else #footer>
        <div class="create-success__footer">
          <button class="user-mgmt__btn user-mgmt__btn--secondary" @click="downloadCreateCredential">下载凭证</button>
          <button class="user-mgmt__btn user-mgmt__btn--primary" @click="completeCreate">完成</button>
        </div>
      </template>
    </ElDialog>
  </section>
</template>

<style scoped>
.user-mgmt {
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.user-mgmt__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.user-mgmt__card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 20px 24px;
  background: var(--bg-2);
  border-radius: 8px;
}

.user-mgmt__toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
  margin-bottom: 20px;
}

.user-mgmt__search {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: 296px;
  height: 32px;
  padding: 0 12px;
  background: var(--bg-2);
  border: 1px solid var(--border-separator);
  border-radius: 4px;
  box-sizing: border-box;
}

.user-mgmt__search:focus-within,
.user-mgmt__jump-input:focus,
.create-dialog__input:focus {
  border-color: var(--color-primary);
  outline: none;
}

.user-mgmt__search-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  opacity: 0.65;
}

.user-mgmt__search-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
  font-family: inherit;
}

.user-mgmt__search-input::placeholder {
  color: var(--text-placeholder);
}

.user-mgmt__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.user-mgmt__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 5px 16px;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
  background: transparent;
  font-family: inherit;
  transition: all 0.15s ease;
  box-sizing: border-box;
}

.user-mgmt__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.user-mgmt__btn--secondary {
  background: var(--bg-2);
  border-color: var(--border-separator);
  color: var(--text-primary);
}

.user-mgmt__btn--secondary:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.user-mgmt__btn--primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-inverse);
}

.user-mgmt__btn--primary:hover:not(:disabled) {
  background: #0058b0;
  border-color: #0058b0;
}

.user-mgmt__table-area {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.table-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 8px;
}

.table-loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #e8e8e8;
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: table-spin 0.8s linear infinite;
}

@keyframes table-spin {
  to { transform: rotate(360deg); }
}

.user-mgmt__table {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
  background: transparent;
}

/* ── role filter ── */
.role-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.role-filter-icon {
  color: var(--text-placeholder);
  cursor: pointer;
  transition: color 0.2s;
}

.role-filter-icon:hover,
.role-filter-icon--active {
  color: var(--color-primary);
}

.role-filter-popover {
  display: flex;
  flex-direction: column;
}

.role-filter-option {
  padding: 6px 12px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  border-radius: 4px;
}

.role-filter-option:hover {
  background: var(--bg-1);
}

.role-filter-option--active {
  color: var(--color-primary);
  background: var(--bg-active);
}

.user-mgmt__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  flex-shrink: 0;
  gap: 16px;
}

.user-mgmt__total {
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
  flex-shrink: 0;
}

.user-mgmt__pager {
  flex: 1;
  justify-content: center;
}

.user-mgmt__jump {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.user-mgmt__jump-label {
  font-size: 14px;
  color: var(--text-primary);
}

.user-mgmt__jump-input {
  width: 96px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border-separator);
  border-radius: 4px;
  font-size: 14px;
  color: var(--text-primary);
  background: var(--bg-2);
  font-family: inherit;
  box-sizing: border-box;
  text-align: center;
}

.user-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.user-cell__avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1px solid rgb(0 0 0 / 10%);
  object-fit: cover;
}

.cell-mono,
.cell-muted {
  font-size: 13px;
  color: var(--text-secondary);
}

.cell-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.role-tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
  font-weight: 400;
}

.role-tag--admin {
  color: var(--tag-text-alert);
  background: var(--tag-bg-alert);
}

.role-tag--user {
  color: var(--tag-text-info);
  background: var(--tag-bg-info);
}

.login-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-primary);
}

.login-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-placeholder);
  flex-shrink: 0;
}

.login-status--online .login-status__dot {
  background: var(--success);
}

.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 16px;
}

.row-actions__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s ease;
}

.row-actions__btn:hover {
  background: rgba(0, 0, 0, 0.04);
}

.row-actions__btn img {
  display: block;
  object-fit: contain;
}

.error-text {
  color: var(--color-error);
  font-size: 13px;
}

/* ── Batch dialog ── */
.batch-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}

.batch-dialog__title {
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.batch-dialog__close,
.create-dialog__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 4px;
}

.batch-dialog__close:hover,
.create-dialog__close:hover {
  background: rgba(0, 0, 0, 0.04);
}

.batch-dialog__desc {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.batch-dialog__link {
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: none;
}

.batch-dialog__link:hover {
  text-decoration: underline;
}

.batch-dialog__upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  background: rgba(25, 25, 25, 0.05);
  border: 1px dashed var(--border-separator);
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.batch-dialog__upload:hover {
  border-color: var(--color-primary);
}

.batch-dialog__upload-text {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.batch-dialog__upload-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.batch-dialog__file-input {
  display: none;
}

.batch-dialog__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  gap: 16px;
}

.batch-dialog__loading-text {
  margin: 0;
  font-size: 14px;
  color: var(--text-placeholder);
}

.batch-results {
  margin-top: 20px;
}

.batch-results__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.batch-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 400;
}

.batch-status--ok {
  color: var(--success);
  background: rgba(9, 170, 113, 0.1);
}

.batch-status--fail {
  color: var(--color-error);
  background: rgba(224, 33, 40, 0.08);
}

.batch-dialog__footer,
.reset-confirm__footer,
.reset-result__footer,
.create-dialog__footer,
.create-success__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

/* ── Reset confirm dialog ── */
.reset-confirm__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding-right: 8px;
}

.reset-confirm__warning {
  flex-shrink: 0;
  margin-top: 2px;
  color: #fcc800;
}

.reset-confirm__header-text {
  flex: 1;
}

.reset-confirm__title {
  margin: 0;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-primary);
}

.reset-confirm__subtitle {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.reset-confirm__prompt {
  margin: 16px 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
}

.reset-confirm__card,
.reset-result__card,
.create-success__card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--border-separator);
  border-radius: 8px;
}

.reset-confirm__row {
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 24px;
}

.reset-confirm__label,
.create-success__label {
  width: 96px;
  flex-shrink: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.reset-result__label {
  width: 80px;
  flex-shrink: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.reset-confirm__value,
.reset-result__value,
.create-success__value {
  font-size: 14px;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.reset-confirm__value-wrap,
.reset-result__value-wrap,
.create-success__value-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

/* ── Reset result dialog ── */
.reset-result__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}

.reset-result__title {
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.reset-result__subtitle {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.reset-result__row {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 24px;
}

.reset-result__row--highlight,
.create-success__row--highlight {
  background: rgba(208, 216, 253, 0.18);
  border-radius: 4px;
  padding: 4px 6px;
  margin: 4px -6px -4px;
}

.reset-result__password,
.create-success__password {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* ── Element Plus overrides for table ── */
:deep(.user-mgmt__table .el-table__header th) {
  color: var(--text-primary);
  font-weight: 500;
  background: rgba(25, 25, 25, 0.05);
  border-bottom: 1px solid var(--border-separator);
}

:deep(.user-mgmt__table .el-table__row td) {
  border-bottom: 1px solid var(--border-separator-subtle);
  color: var(--text-primary);
  font-size: 14px;
}

:deep(.user-mgmt__table .el-table__row:last-child td) {
  border-bottom: none;
}

:deep(.user-mgmt__table .el-table__cell) {
  padding: 9px 8px;
}

:deep(.user-mgmt__table .el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

:deep(.user-mgmt__pager .el-pager li.is-active) {
  background: var(--bg-active);
  color: var(--color-primary);
  border-radius: 4px;
}

:deep(.user-mgmt__pager .el-pagination__sizes .el-select__wrapper) {
  border-radius: 4px;
  height: 32px;
  background: var(--bg-2);
}

/* ── Dialog overrides ── */
:deep(.batch-dialog .el-dialog__header),
:deep(.reset-confirm-dialog .el-dialog__header),
:deep(.reset-result-dialog .el-dialog__header),
:deep(.create-dialog .el-dialog__header) {
  padding: 20px 24px 8px;
  margin-right: 0;
}

:deep(.batch-dialog .el-dialog__body),
:deep(.reset-confirm-dialog .el-dialog__body),
:deep(.reset-result-dialog .el-dialog__body),
:deep(.create-dialog .el-dialog__body) {
  padding: 8px 24px 20px;
}

:deep(.batch-dialog .el-dialog__footer),
:deep(.reset-confirm-dialog .el-dialog__footer),
:deep(.reset-result-dialog .el-dialog__footer),
:deep(.create-dialog .el-dialog__footer) {
  padding: 0 24px 20px;
}

:deep(.batch-dialog .el-dialog),
:deep(.reset-confirm-dialog .el-dialog),
:deep(.reset-result-dialog .el-dialog),
:deep(.create-dialog .el-dialog) {
  border-radius: 8px;
  box-shadow: 0px 16px 48px 0px rgba(0, 0, 0, 0.16);
}

:deep(.batch-results .el-table) {
  font-size: 13px;
}

/* ── Create user dialog ── */
.create-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}

.create-dialog__title {
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.create-dialog__desc {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.create-dialog__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.create-dialog__label {
  font-size: 14px;
  color: var(--text-primary);
}

.create-dialog__input {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border-separator);
  border-radius: 4px;
  font-size: 14px;
  color: var(--text-primary);
  background: var(--bg-2);
  font-family: inherit;
  box-sizing: border-box;
  outline: none;
}

.create-dialog__input::placeholder {
  color: var(--text-placeholder);
}

.create-dialog__input:disabled {
  background: #fafafa;
  cursor: not-allowed;
}

.create-dialog__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.create-dialog__error {
  margin: 0;
  font-size: 12px;
  color: var(--color-error);
}

/* ── Create success card (mirrors reset-result) ── */
.create-success__subtitle {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.create-success__row {
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 24px;
}

</style>
