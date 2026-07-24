<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import {
  ElButton,
  ElInput,
  ElTable,
  ElTableColumn,
  ElPagination,
  ElDialog,
  ElTag,
  ElMessage,
  ElMessageBox,
  ElIcon,
} from 'element-plus';
import { Search } from '@element-plus/icons-vue';
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

const users = ref<UserItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const search = ref('');
const listLoading = ref(false);
const selectedRows = ref<UserItem[]>([]);

const showBatchModal = ref(false);
const batchInput = ref('');
const batchResults = ref<BatchCreateResult[]>([]);
const batchLoading = ref(false);

interface ResetResult {
  username: string;
  user_id: string;
  new_password: string;
}
const showResetModal = ref(false);
const resetResult = ref<ResetResult | null>(null);
const resetLoading = ref(false);

async function loadUsers() {
  listLoading.value = true;
  try {
    const data = await getUsers({
      page: page.value,
      page_size: pageSize.value,
      search: search.value || undefined,
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

function handleSearch() {
  page.value = 1;
  loadUsers();
}

function handleSelectionChange(rows: UserItem[]) {
  selectedRows.value = rows;
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

async function handleBatchCreate() {
  const names = batchInput.value
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  if (!names.length) {
    ElMessage.warning('请输入至少一个用户名');
    return;
  }

  batchLoading.value = true;
  batchResults.value = [];
  try {
    batchResults.value = await batchCreateUsers(names);
    await nextTick();
    const body = document.querySelector('.batch-dialog .el-dialog__body');
    body?.scrollTo({ top: body.scrollHeight, behavior: 'smooth' });
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '批量创建失败');
  } finally {
    batchLoading.value = false;
  }
}

function openBatchModal() {
  batchInput.value = '';
  batchResults.value = [];
  showBatchModal.value = true;
}

function downloadCsv() {
  if (!batchResults.value.length) return;

  const headers = ['username', 'user_id', 'password', 'error'];
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = batchResults.value.map((r) => headers.map((h) => escape(r[h as keyof typeof r])).join(','));
  const csv = '\uFEFF' + [headers.join(','), ...rows].join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `batch-create-results-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success('已复制到剪贴板');
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    ElMessage.success('已复制到剪贴板');
  }
}

async function handleResetPassword(user: UserItem) {
  try {
    await ElMessageBox.confirm(`确定要重置 ${user.username} 的密码吗？系统将生成一个新的随机密码。`, '重置密码', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    });
  } catch {
    return;
  }

  resetLoading.value = true;
  try {
    const r = await resetUserPassword(user.user_id);
    resetResult.value = {
      username: r.username || user.username,
      user_id: r.user_id,
      new_password: r.new_password,
    };
    showResetModal.value = true;
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败');
  } finally {
    resetLoading.value = false;
  }
}

function closeResetModal() {
  showResetModal.value = false;
  resetResult.value = null;
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
        <ElInput
          v-model="search"
          class="user-mgmt__search"
          placeholder="请输入搜索内容"
          clearable
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix>
            <ElIcon :size="14"><Search /></ElIcon>
          </template>
        </ElInput>

        <div class="user-mgmt__actions">
          <ElButton @click="ElMessage.info('批量管理功能开发中')">批量管理</ElButton>
          <ElButton type="primary" @click="openBatchModal">新增用户</ElButton>
        </div>
      </div>

      <ElTable
        v-loading="listLoading"
        :data="users"
        row-key="user_id"
        class="user-mgmt__table"
        empty-text="暂无数据"
        @selection-change="handleSelectionChange"
      >
        <ElTableColumn type="selection" width="48" />
        <ElTableColumn label="用户名" min-width="160">
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
        <ElTableColumn label="用户角色" width="120">
          <template #default="{ row }">
            <ElTag
              size="small"
              effect="light"
              :class="row.role === 'admin' ? 'role-tag role-tag--admin' : 'role-tag role-tag--user'"
            >
              {{ roleLabel(row.role) }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="登录状态" width="120">
          <template #default="{ row }">
            <span class="login-status" :class="row.is_active ? 'login-status--online' : 'login-status--offline'">
              <span class="login-status__dot" />
              {{ row.is_active ? '在线' : '离线' }}
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="最近活跃时间" min-width="170">
          <template #default>—</template>
        </ElTableColumn>
        <ElTableColumn label="创建时间" min-width="170">
          <template #default="{ row }">
            <span class="cell-muted">{{ formatDate(row.created_at) }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="128" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <ElButton link type="primary" title="复制用户ID" @click="copyToClipboard(row.user_id)">
                <img :src="docIcon" alt="" width="16" height="16" class="row-actions__icon" />
              </ElButton>
              <ElButton link type="primary" title="重置密码" :loading="resetLoading" @click="handleResetPassword(row)">
                <img :src="keyIcon" alt="" width="16" height="16" class="row-actions__icon" />
              </ElButton>
              <ElButton link type="danger" title="删除" @click="handleDelete(row)">
                <img :src="deleteIcon" alt="" width="16" height="16" class="row-actions__icon" />
              </ElButton>
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
          layout="sizes, prev, pager, next, jumper"
          background
        />
      </div>
    </div>

    <!-- 批量新建用户 -->
    <ElDialog v-model="showBatchModal" width="640px" class="batch-dialog" destroy-on-close>
      <template #header>
        <div class="batch-dialog__header">
          <span class="batch-dialog__title">批量新建用户</span>
          <ElButton v-if="batchResults.length" @click="downloadCsv">导出 CSV</ElButton>
        </div>
      </template>

      <p class="batch-dialog__desc">每行一个用户名，或用逗号分隔。密码将自动生成。</p>
      <ElInput
        v-model="batchInput"
        type="textarea"
        :rows="8"
        placeholder="user_01&#10;user_02&#10;user_03"
        :disabled="batchLoading"
      />

      <div v-if="batchResults.length" class="batch-results">
        <div class="batch-results__header">
          <h3 class="batch-results__title">创建结果</h3>
          <ElTag type="success" effect="light" size="small">
            成功 {{ batchResults.filter((r) => !r.error).length }}
          </ElTag>
          <ElTag type="danger" effect="light" size="small">
            失败 {{ batchResults.filter((r) => r.error).length }}
          </ElTag>
        </div>
        <ElTable :data="batchResults" size="small" max-height="280">
          <ElTableColumn label="状态" width="80">
            <template #default="{ row }">
              <ElTag :type="row.error ? 'danger' : 'success'" size="small" effect="light">
                {{ row.error ? '失败' : '成功' }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="用户名" min-width="100">
            <template #default="{ row }">
              <code>{{ row.username }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn label="用户ID" min-width="140">
            <template #default="{ row }">
              <span class="cell-mono">{{ row.user_id || '—' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="初始密码" min-width="140">
            <template #default="{ row }">
              <code v-if="row.password">{{ row.password }}</code>
              <span v-else>—</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="失败原因" min-width="140">
            <template #default="{ row }">
              <span v-if="row.error" class="error-text">{{ row.error }}</span>
              <span v-else>—</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="100">
            <template #default="{ row }">
              <ElButton v-if="row.password" link type="primary" @click="copyToClipboard(row.password!)">
                复制密码
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </div>

      <template #footer>
        <ElButton @click="showBatchModal = false">关闭</ElButton>
        <ElButton type="primary" :loading="batchLoading" @click="handleBatchCreate">
          {{ batchLoading ? '创建中...' : '创建' }}
        </ElButton>
      </template>
    </ElDialog>

    <!-- 密码重置结果 -->
    <ElDialog v-model="showResetModal" title="密码重置成功" width="480px" destroy-on-close @closed="resetResult = null">
      <template v-if="resetResult">
        <p class="reset-desc">
          请将以下新密码告知用户 <strong>{{ resetResult.username }}</strong
          >。该密码仅显示一次，请妥善保存。
        </p>
        <div class="reset-fields">
          <div class="reset-field">
            <span class="reset-field__label">用户名</span>
            <span class="reset-field__value">{{ resetResult.username }}</span>
          </div>
          <div class="reset-field">
            <span class="reset-field__label">用户ID</span>
            <span class="reset-field__value cell-mono">{{ resetResult.user_id }}</span>
          </div>
          <div class="reset-field reset-field--highlight">
            <span class="reset-field__label">新密码</span>
            <div class="reset-field__pwd">
              <code class="reset-field__value cell-mono">{{ resetResult.new_password }}</code>
              <ElButton link type="primary" @click="copyToClipboard(resetResult.new_password)">
                <img :src="docIcon" alt="" width="16" height="16" class="row-actions__icon" />
              </ElButton>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <ElButton @click="closeResetModal">关闭</ElButton>
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
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.user-mgmt__search {
  width: 296px;
}

.user-mgmt__actions {
  display: flex;
  gap: 8px;
}

.user-mgmt__table {
  flex: 1;
  width: 100%;
}

.user-mgmt__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  flex-shrink: 0;
}

.user-mgmt__total {
  font-size: 14px;
  color: var(--text-secondary);
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

.cell-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  color: var(--text-secondary);
}

.cell-muted {
  color: var(--text-secondary);
  font-size: 13px;
}

.role-tag {
  border: none !important;
}

.role-tag--admin {
  color: var(--tag-text-alert) !important;
  background: var(--tag-bg-alert) !important;
}

.role-tag--user {
  color: var(--tag-text-info) !important;
  background: var(--tag-bg-info) !important;
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
  background: var(--bg-mask);
}

.login-status--online .login-status__dot {
  background: var(--success);
}

.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.row-actions__icon {
  display: block;
  object-fit: contain;
}

.batch-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding-right: 24px;
}

.batch-dialog__title {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

.batch-dialog__desc {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--text-secondary);
}

.batch-results {
  margin-top: 20px;
}

.batch-results__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.batch-results__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.error-text {
  color: var(--error);
  font-size: 13px;
}

.reset-desc {
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.reset-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.reset-field {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  background: var(--bg-2);
  border-radius: 4px;
}

.reset-field--highlight {
  background: var(--bg-active);
}

.reset-field__label {
  width: 56px;
  flex-shrink: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.reset-field__value {
  font-size: 14px;
  color: var(--text-primary);
}

.reset-field__pwd {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

:deep(.user-mgmt__table .el-table__header th) {
  color: var(--text-secondary);
  font-weight: 500;
  background: var(--bg-6);
}

:deep(.user-mgmt__search .el-input__wrapper) {
  border-radius: 4px;
}
</style>
