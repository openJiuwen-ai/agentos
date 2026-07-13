<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue';
import {
  getUsers,
  batchCreateUsers,
  resetUserPassword,
  deleteUser,
  type UserItem,
  type BatchCreateResult,
} from '@/api/users';
import copyIcon from '@/assets/icons/copy.svg';
import keyIcon from '@/assets/icons/key.svg';
import trashIcon from '@/assets/icons/trash.svg';
import userAvatar from '@/assets/icons/person.svg';
import closeIcon from '@/assets/icons/close.svg';

// ── list state ──
const users = ref<UserItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const search = ref('');
const listLoading = ref(false);
const selectedIds = ref<Set<string>>(new Set());

// ── batch create modal ──
const showBatchModal = ref(false);
const batchInput = ref('');
const batchResults = ref<BatchCreateResult[]>([]);
const batchLoading = ref(false);

// ── reset password popup ──
interface ResetResult {
  username: string;
  user_id: string;
  new_password: string;
}
const showResetModal = ref(false);
const resetResult = ref<ResetResult | null>(null);
const resetLoading = ref(false);

const allSelected = computed(() => {
  return users.value.length > 0 && users.value.every((u) => selectedIds.value.has(u.user_id));
});

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
    selectedIds.value.clear();
  } catch {
    // error shown inline
  } finally {
    listLoading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadUsers();
}

function changePageSize() {
  page.value = 1;
  loadUsers();
}

watch(page, () => loadUsers());

onMounted(() => loadUsers());

// ── selection ──
function toggleAll() {
  if (allSelected.value) {
    users.value.forEach((u) => selectedIds.value.delete(u.user_id));
  } else {
    users.value.forEach((u) => selectedIds.value.add(u.user_id));
  }
}

function toggleOne(id: string) {
  if (selectedIds.value.has(id)) {
    selectedIds.value.delete(id);
  } else {
    selectedIds.value.add(id);
  }
}

// ── batch create ──
const modalEl = ref<HTMLElement | null>(null);
const resultsAnchor = ref<HTMLElement | null>(null);

async function handleBatchCreate() {
  const names = batchInput.value
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  if (!names.length) return;

  batchLoading.value = true;
  batchResults.value = [];
  try {
    batchResults.value = await batchCreateUsers(names);
    await nextTick();
    // Modal has its own scroll context — scroll inside it, not the page
    if (resultsAnchor.value && modalEl.value) {
      const anchorTop = resultsAnchor.value.offsetTop;
      modalEl.value.scrollTo({ top: anchorTop, behavior: 'smooth' });
    }
  } finally {
    batchLoading.value = false;
  }
}

function openBatchModal() {
  batchInput.value = '';
  batchResults.value = [];
  showBatchModal.value = true;
}

// ── csv export ──
function downloadCsv() {
  if (!batchResults.value.length) return;

  const headers = ['username', 'user_id', 'password', 'error'];
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = batchResults.value.map((r) =>
    headers.map((h) => escape(r[h as keyof typeof r])).join(','),
  );
  const csv = '﻿' + [headers.join(','), ...rows].join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `batch-create-results-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function statusOf(r: BatchCreateResult) {
  return r.error ? 'fail' : 'success';
}

// ── row actions ──
async function copyUserId(user: UserItem) {
  await copyToClipboard(user.user_id);
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // fallback for non-secure contexts
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}

async function handleResetPassword(user: UserItem) {
  if (!confirm(`确定要重置 ${user.username} 的密码吗？\n\n系统将生成一个新的随机密码。`)) return;
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
    alert(e instanceof Error ? e.message : '操作失败');
  } finally {
    resetLoading.value = false;
  }
}

function closeResetModal() {
  showResetModal.value = false;
  resetResult.value = null;
}

async function handleDelete(user: UserItem) {
  if (!confirm(`确定要删除用户 ${user.username} 吗？此操作不可撤销。`)) return;
  try {
    await deleteUser(user.user_id);
    loadUsers();
  } catch (e) {
    alert(e instanceof Error ? e.message : '操作失败');
  }
}

// ── helpers ──
function roleLabel(role: string) {
  return role === 'admin' ? '管理员' : '普通用户';
}

function roleTagClass(role: string) {
  return role === 'admin' ? 'tag tag--admin' : 'tag tag--user';
}

function statusLabel(isActive: boolean) {
  return isActive ? '在线' : '离线';
}

function statusClass(isActive: boolean) {
  return isActive ? 'status status--online' : 'status status--offline';
}

function formatDate(iso: string | null) {
  if (!iso) return '-';
  return iso.slice(0, 19).replace('T', ' ');
}

// pagination
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const visiblePages = computed(() => {
  const t = totalPages.value;
  const p = page.value;
  if (t <= 5) return Array.from({ length: t }, (_, i) => i + 1);
  if (p <= 3) return [1, 2, 3, 4, 5];
  if (p >= t - 2) return [t - 4, t - 3, t - 2, t - 1, t];
  return [p - 2, p - 1, p, p + 1, p + 2];
});

const jumpTo = ref('');
function handleJump() {
  const n = parseInt(jumpTo.value, 10);
  if (n >= 1 && n <= totalPages.value) {
    page.value = n;
    jumpTo.value = '';
  }
}
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1 class="page-title">用户管理</h1>
      <div class="page-actions">
        <button class="btn btn--secondary" @click="alert('批量管理功能开发中')">批量管理</button>
        <button class="btn btn--primary" @click="openBatchModal">新增用户</button>
      </div>
    </div>

    <div class="toolbar">
      <div class="search-box">
        <img :src="userAvatar" alt="" width="14" height="14" style="opacity: 0.5" />
        <input
          v-model="search"
          type="text"
          class="search-input"
          placeholder="请输入搜索内容"
          @keyup.enter="handleSearch"
        />
      </div>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th class="cell-checkbox">
              <input
                type="checkbox"
                :checked="allSelected"
                @change="toggleAll"
              />
            </th>
            <th>
              <span>用户名</span>
              <span class="sort-icon">↕</span>
            </th>
            <th>
              <span>用户ID</span>
              <span class="sort-icon">▼</span>
            </th>
            <th>
              <span>用户角色</span>
              <span class="sort-icon">▼</span>
            </th>
            <th>
              <span>登录状态</span>
              <span class="sort-icon">▼</span>
            </th>
            <th>
              <span>最近活跃时间</span>
              <span class="sort-icon">↕</span>
            </th>
            <th>
              <span>创建时间</span>
              <span class="sort-icon">↕</span>
            </th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="listLoading">
            <td colspan="8" class="table-empty">加载中...</td>
          </tr>
          <tr v-else-if="!users.length">
            <td colspan="8" class="table-empty">暂无数据</td>
          </tr>
          <tr v-for="u in users" :key="u.user_id">
            <td class="cell-checkbox">
              <input
                type="checkbox"
                :checked="selectedIds.has(u.user_id)"
                @change="toggleOne(u.user_id)"
              />
            </td>
            <td>
              <div class="user-cell">
                <img :src="userAvatar" :alt="u.username" class="avatar" />
                <span>{{ u.username }}</span>
              </div>
            </td>
            <td class="cell-mono">{{ u.user_id }}</td>
            <td><span :class="roleTagClass(u.role)">{{ roleLabel(u.role) }}</span></td>
            <td>
              <span :class="statusClass(u.is_active)">
                <span class="dot" :class="u.is_active ? 'dot--green' : 'dot--gray'" />
                {{ statusLabel(u.is_active) }}
              </span>
            </td>
            <td class="cell-muted">—</td>
            <td class="cell-muted">{{ formatDate(u.created_at) }}</td>
            <td class="cell-actions">
              <button class="icon-btn" title="复制用户ID" @click="copyUserId(u)">
                <img :src="copyIcon" alt="copy" width="16" height="16" />
              </button>
              <button class="icon-btn" title="重置密码" @click="handleResetPassword(u)">
                <img :src="keyIcon" alt="key" width="16" height="16" />
              </button>
              <button class="icon-btn icon-btn--danger" title="删除" @click="handleDelete(u)">
                <img :src="trashIcon" alt="delete" width="16" height="16" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- pagination -->
    <div class="pagination">
      <span class="pagination-total">总计：{{ total }}</span>
      <div class="pagination-right">
        <div class="page-size">
          <select v-model="pageSize" class="page-size-select" @change="changePageSize">
            <option :value="10">10条/页</option>
            <option :value="20">20条/页</option>
            <option :value="50">50条/页</option>
          </select>
        </div>
        <button class="page-btn" :disabled="page <= 1" @click="page--">‹</button>
        <button
          v-for="n in visiblePages"
          :key="n"
          class="page-btn"
          :class="{ 'page-btn--active': n === page }"
          @click="page = n"
        >
          {{ n }}
        </button>
        <span v-if="totalPages > 5" class="page-ellipsis">…</span>
        <button class="page-btn" :disabled="page >= totalPages" @click="page++">›</button>
        <span v-if="totalPages > 5" class="page-jump">
          <input v-model="jumpTo" type="number" min="1" :max="totalPages" class="page-jump-input" />
          <button class="page-btn page-btn--text" @click="handleJump">跳转</button>
        </span>
      </div>
    </div>

    <!-- batch create modal -->
    <Teleport to="body">
      <div v-if="showBatchModal" class="modal-overlay" @click.self="showBatchModal = false">
        <div ref="modalEl" class="modal">
          <div class="modal-header">
            <h2 class="modal-title">批量新建用户</h2>
            <button
              v-if="batchResults.length"
              class="btn btn--secondary"
              @click="downloadCsv"
            >
              导出 CSV
            </button>
          </div>
          <p class="modal-desc">每行一个用户名，或用逗号分隔。密码将自动生成。</p>
          <textarea
            v-model="batchInput"
            class="modal-textarea"
            rows="8"
            placeholder="user_01&#10;user_02&#10;user_03"
            :disabled="batchLoading"
          />
          <div class="modal-actions">
            <button class="btn btn--secondary" @click="showBatchModal = false">关闭</button>
            <button class="btn btn--primary" :disabled="batchLoading" @click="handleBatchCreate">
              {{ batchLoading ? '创建中...' : '创建' }}
            </button>
          </div>

          <div v-if="batchResults.length" ref="resultsAnchor" class="results-section">
            <div class="results-header">
              <h3 class="results-title">
                创建结果
                <span class="results-summary">
                  <span class="summary-pill summary-pill--success">
                    成功 {{ batchResults.filter((r) => !r.error).length }}
                  </span>
                  <span class="summary-pill summary-pill--fail">
                    失败 {{ batchResults.filter((r) => r.error).length }}
                  </span>
                </span>
              </h3>
            </div>
            <div class="results-table-wrap">
              <table class="results-table">
                <thead>
                  <tr>
                    <th>状态</th>
                    <th>用户名</th>
                    <th>用户ID</th>
                    <th>初始密码</th>
                    <th>失败原因</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="r in batchResults"
                    :key="r.username + (r.user_id ?? 'fail')"
                    :class="`results-row results-row--${statusOf(r)}`"
                  >
                    <td>
                      <span v-if="r.error" class="status-cell status-cell--fail">失败</span>
                      <span v-else class="status-cell status-cell--success">成功</span>
                    </td>
                    <td><code>{{ r.username }}</code></td>
                    <td class="cell-mono">{{ r.user_id || '—' }}</td>
                    <td class="cell-mono">
                      <template v-if="r.password">
                        <code>{{ r.password }}</code>
                      </template>
                      <span v-else>—</span>
                    </td>
                    <td>
                      <span v-if="r.error" class="error-text">{{ r.error }}</span>
                      <span v-else>—</span>
                    </td>
                    <td>
                      <button
                        v-if="r.password"
                        class="link-btn"
                        @click="copyToClipboard(r.password!)"
                      >
                        复制密码
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- reset password result modal -->
    <Teleport to="body">
      <div v-if="showResetModal && resetResult" class="modal-overlay" @click.self="closeResetModal">
        <div class="modal modal--small">
          <div class="modal-header">
            <h2 class="modal-title">密码重置成功</h2>
            <button class="modal-close" title="关闭" @click="closeResetModal">
              <img :src="closeIcon" alt="关闭" width="14" height="14" />
            </button>
          </div>
          <p class="modal-desc">
            请将以下新密码告知用户 <strong>{{ resetResult.username }}</strong>。该密码仅显示一次，请妥善保存。
          </p>

          <div class="reset-fields">
            <div class="reset-field">
              <span class="reset-field__label">用户名</span>
              <span class="reset-field__value">{{ resetResult.username }}</span>
            </div>
            <div class="reset-field">
              <span class="reset-field__label">用户ID</span>
              <span class="reset-field__value reset-field__value--mono">{{ resetResult.user_id }}</span>
            </div>
            <div class="reset-field reset-field--highlight">
              <span class="reset-field__label">新密码</span>
              <div class="reset-field__pwd">
                <code class="reset-field__value reset-field__value--mono reset-field__value--pwd">
                  {{ resetResult.new_password }}
                </code>
                <button class="icon-btn" title="复制密码" @click="copyToClipboard(resetResult.new_password)">
                  <img :src="copyIcon" alt="copy" width="16" height="16" />
                </button>
              </div>
            </div>
          </div>

          <div class="modal-actions">
            <button class="btn btn--secondary" @click="closeResetModal">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
/* ── header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.page-actions {
  display: flex;
  gap: 8px;
}

/* ── toolbar ── */
.toolbar {
  margin-top: 20px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 296px;
  padding: 5px 12px;
  background: #ffffff;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  line-height: 22px;
  color: #191919;
  background: transparent;
}

.search-input::placeholder {
  color: #aeaeae;
}

/* ── table ── */
.table-wrap {
  margin-top: 16px;
  background: #ffffff;
  border-radius: 8px;
  overflow: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.table th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 500;
  color: #777777;
  background: #fafafa;
  border-bottom: 1px solid #dfdfdf;
  white-space: nowrap;
}

.table th .sort-icon {
  margin-left: 6px;
  color: #aeaeae;
  font-size: 12px;
}

.table td {
  padding: 12px 16px;
  color: #191919;
  border-bottom: 1px solid #f3f3f3;
  vertical-align: middle;
}

.table tr:last-child td {
  border-bottom: none;
}

.table tr:hover td {
  background: #fafafa;
}

.table-empty {
  text-align: center;
  color: #aeaeae;
  padding: 40px 16px !important;
}

.cell-checkbox {
  width: 40px;
}

.cell-checkbox input {
  cursor: pointer;
}

.cell-muted {
  color: #777777;
  font-size: 13px;
}

.cell-mono {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  color: #777777;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #f3f3f3;
}

/* ── tags & status ── */
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
}

.tag--admin {
  color: #ffffff;
  background: #ec6f1a;
}

.tag--user {
  color: #1f55b5;
  background: rgba(208, 216, 253, 0.5);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.status--online {
  color: #191919;
}

.status--offline {
  color: #777777;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot--green {
  background: #09aa71;
}

.dot--gray {
  background: #aeaeae;
}

/* ── buttons ── */
.btn {
  padding: 5px 20px;
  font-size: 14px;
  line-height: 22px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn--primary {
  color: #ffffff;
  background: #0067d1;
}

.btn--primary:hover:not(:disabled) {
  background: #0055b3;
}

.btn--primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn--secondary {
  color: #191919;
  background: #ffffff;
  border: 1px solid #c9c9c9;
}

.btn--secondary:hover {
  background: #f5f5f5;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.icon-btn:hover {
  background: #f3f3f3;
}

.icon-btn--danger:hover {
  background: #fff5f5;
}

.icon-btn--danger:hover img {
  filter: hue-rotate(-30deg) saturate(3);
}

.cell-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.link-btn {
  padding: 0;
  border: none;
  background: transparent;
  color: #0067d1;
  font-size: 13px;
  cursor: pointer;
}

.link-btn:hover {
  text-decoration: underline;
}

/* ── pagination ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  font-size: 14px;
  color: #777777;
}

.pagination-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-size-select {
  padding: 4px 8px;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  background: #ffffff;
  color: #191919;
  font-size: 13px;
  cursor: pointer;
}

.page-btn {
  min-width: 28px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: #191919;
  font-size: 13px;
  cursor: pointer;
}

.page-btn:hover:not(:disabled) {
  border-color: #c9c9c9;
}

.page-btn:disabled {
  color: #c9c9c9;
  cursor: not-allowed;
}

.page-btn--active {
  color: #0067d1;
  border-color: #0067d1;
  background: #ffffff;
}

.page-ellipsis {
  color: #aeaeae;
  padding: 0 4px;
}

.page-jump {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
}

.page-jump-input {
  width: 50px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  font-size: 13px;
  color: #191919;
}

.page-btn--text {
  border: none;
}

/* ── modal ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
}

.modal {
  width: 880px;
  max-width: calc(100% - 32px);
  max-height: 85vh;
  overflow-y: auto;
  padding: 24px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.16);
}

.modal-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 500;
  color: #191919;
}

.modal-desc {
  margin: 0 0 16px;
  font-size: 14px;
  color: #777777;
}

.modal-textarea {
  width: 100%;
  padding: 11px 12px;
  font-size: 14px;
  line-height: 22px;
  color: #191919;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  outline: none;
  resize: vertical;
  font-family: inherit;
}

.modal-textarea:focus {
  border-color: #0067d1;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.batch-results {
  margin-top: 12px;
  border: 1px solid #dfdfdf;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.batch-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 13px;
  border-bottom: 1px solid #f3f3f3;
}

.batch-row:last-child {
  border-bottom: none;
}

.batch-row--error {
  background: #fff5f5;
}

.batch-error {
  color: #e02128;
}

.batch-pwd {
  color: #09aa71;
  font-family: monospace;
}

/* ── batch results spreadsheet ── */
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.results-section {
  margin-top: 20px;
  border-top: 1px solid #dfdfdf;
  padding-top: 16px;
}

.results-header {
  margin-bottom: 12px;
}

.results-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: #191919;
}

.results-summary {
  display: inline-flex;
  gap: 8px;
  margin-left: 8px;
}

.summary-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 18px;
}

.summary-pill--success {
  background: #dff4cc;
  color: #316614;
}

.summary-pill--fail {
  background: #ffe2e2;
  color: #b21e1e;
}

.results-table-wrap {
  max-height: 360px;
  overflow: auto;
  border: 1px solid #dfdfdf;
  border-radius: 4px;
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.results-table th {
  position: sticky;
  top: 0;
  padding: 10px 12px;
  text-align: left;
  font-weight: 500;
  color: #777777;
  background: #fafafa;
  border-bottom: 1px solid #dfdfdf;
  white-space: nowrap;
}

.results-table td {
  padding: 10px 12px;
  color: #191919;
  border-bottom: 1px solid #f3f3f3;
  vertical-align: middle;
}

.results-table tr:last-child td {
  border-bottom: none;
}

.results-row--success td {
  background: #fafff5;
}

.results-row--fail td {
  background: #fff5f5;
}

.status-cell {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
}

.status-cell--success {
  background: #dff4cc;
  color: #316614;
}

.status-cell--fail {
  background: #ffe2e2;
  color: #b21e1e;
}

.cell-truncate {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-text {
  color: #e02128;
  font-size: 12px;
}

/* ── reset password modal ── */
.modal--small {
  width: 480px;
}

.modal-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
}

.modal-close:hover {
  background: #f3f3f3;
}

.reset-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 16px 0 0;
}

.reset-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 4px;
}

.reset-field--highlight {
  background: #e8f4fd;
}

.reset-field__label {
  font-size: 13px;
  color: #777777;
  flex-shrink: 0;
}

.reset-field__value {
  font-size: 14px;
  color: #191919;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.reset-field__value--mono {
  font-family: ui-monospace, monospace;
  font-size: 13px;
}

.reset-field__value--pwd {
  font-size: 15px;
  font-weight: 500;
  color: #0067d1;
  flex: 1;
}

.reset-field__pwd {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  justify-content: flex-end;
}
</style>