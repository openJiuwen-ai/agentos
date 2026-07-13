<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getMe } from '@/api/users';
import { useAuth } from '@/composables/useAuth';

const route = useRoute();
const router = useRouter();
const { clearAuth } = useAuth();

type TabKey = 'profile' | 'cloud-account' | 'preferences';
const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'profile', label: '个人信息' },
  { key: 'cloud-account', label: '云账户管理' },
  { key: 'preferences', label: '偏好设置' },
];

const activeTab = ref<TabKey>(
  (route.query.tab as TabKey) || 'profile',
);

function selectTab(key: TabKey) {
  activeTab.value = key;
  router.replace({ query: { tab: key } });
}

const profile = ref({
  username: '',
  user_id: '',
  role: '',
  is_active: true,
});

const oldPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const loading = ref(false);
const errorMsg = ref('');
const showResetForm = ref(false);

async function loadProfile() {
  try {
    const data = await getMe();
    profile.value = data;
  } catch {
    // silent
  }
}

onMounted(() => loadProfile());

function roleLabel(role: string) {
  return role === 'admin' ? '管理员' : '普通用户';
}

async function handleResetPassword() {
  errorMsg.value = '';

  if (!oldPassword.value || !newPassword.value || !confirmPassword.value) {
    errorMsg.value = '请填写所有密码字段';
    return;
  }
  if (newPassword.value.length < 8) {
    errorMsg.value = '新密码长度至少 8 位';
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMsg.value = '两次输入的新密码不一致';
    return;
  }

  loading.value = true;
  try {
    const { changeMyPassword } = await import('@/api/users');
    await changeMyPassword(oldPassword.value, newPassword.value);
    clearAuth();
    router.push('/login');
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '密码修改失败';
  } finally {
    loading.value = false;
  }
}

function handleLogout() {
  if (!confirm('确定要退出登录吗？')) return;
  clearAuth();
  router.push('/login');
}
</script>

<template>
  <div class="profile-page">
    <img class="profile-banner" src="/images/profile-banner.png" alt="" />
    <div class="profile-content">
      <div class="profile-header">
        <img class="profile-avatar" src="/images/profile-avatar.png" alt="" />
        <div class="profile-meta">
          <div class="profile-name-row">
            <span class="profile-name">{{ profile.username }}</span>
            <span v-if="profile.role" class="role-tag" :class="`role-tag--${profile.role}`">
              {{ roleLabel(profile.role) }}
            </span>
          </div>
          <span v-if="profile.user_id" class="profile-id">用户ID: {{ profile.user_id }}</span>
        </div>
      </div>

      <nav class="profile-tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          class="profile-tabs__item"
          :class="{ 'profile-tabs__item--active': activeTab === t.key }"
          @click="selectTab(t.key)"
        >
          {{ t.label }}
        </button>
      </nav>

      <template v-if="activeTab === 'profile'">
      <section class="profile-section">
        <h2 class="section-title">基本信息</h2>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">头像</span>
            <img class="info-avatar" src="/images/profile-avatar.png" alt="" />
          </div>
          <div class="info-item">
            <span class="info-label">用户名</span>
            <span class="info-value">{{ profile.username }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">用户ID</span>
            <span class="info-value info-value--mono">{{ profile.user_id }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">用户角色</span>
            <span v-if="profile.role" class="role-tag" :class="`role-tag--${profile.role}`">
              {{ roleLabel(profile.role) }}
            </span>
          </div>
          <div class="info-item">
            <span class="info-label">账号状态</span>
            <span class="status-tag status-tag--active">正常</span>
          </div>
        </div>
      </section>

    <section class="profile-section">
      <div class="section-row">
        <div class="section-row-text">
          <h2 class="section-title">重置密码</h2>
          <p class="section-desc">修改密码后需要重新登录</p>
        </div>
        <button v-if="!showResetForm" class="btn btn--primary" @click="showResetForm = true">
          重置密码
        </button>
      </div>

      <form v-if="showResetForm" class="reset-form" @submit.prevent="handleResetPassword">
        <div class="form-group">
          <label class="form-label" for="old-password">原密码</label>
          <input
            id="old-password"
            v-model="oldPassword"
            type="password"
            class="form-input"
            autocomplete="current-password"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label class="form-label" for="new-password">新密码</label>
          <input
            id="new-password"
            v-model="newPassword"
            type="password"
            class="form-input"
            placeholder="至少 8 位字符"
            autocomplete="new-password"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label class="form-label" for="confirm-password">确认新密码</label>
          <input
            id="confirm-password"
            v-model="confirmPassword"
            type="password"
            class="form-input"
            autocomplete="new-password"
            :disabled="loading"
          />
        </div>
        <p v-if="errorMsg" class="msg msg--error" role="alert">{{ errorMsg }}</p>
        <div class="form-actions">
          <button type="button" class="btn btn--secondary" @click="showResetForm = false">取消</button>
          <button type="submit" class="btn btn--primary" :disabled="loading">
            {{ loading ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </form>
    </section>

    <section class="profile-section">
      <div class="section-row">
        <h2 class="section-title">退出登录</h2>
        <button class="btn btn--danger" @click="handleLogout">退出</button>
      </div>
    </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.profile-page {
  /* full-bleed banner; inner content constrained */
}

.profile-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 32px 32px;
}

/* tab menubar */
.profile-tabs {
  display: flex;
  gap: 32px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 24px;
}

.profile-tabs__item {
  padding: 12px 0 10px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  line-height: 24px;
  cursor: pointer;
  transition: color 0.2s;
}

.profile-tabs__item:hover {
  color: var(--text-primary);
}

.profile-tabs__item--active {
  color: var(--color-primary);
  position: relative;
}

.profile-tabs__item--active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  background: var(--color-primary);
  border-radius: 1px;
}

/* placeholder for unfinished tabs (kept empty — tabs render blank) */

.profile-banner {
  display: block;
  width: 100%;
  height: 224px;
  object-fit: cover;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 24px 0 16px;
}

.profile-avatar {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: #f3f3f3;
  margin-top: -56px;
  border: 4px solid #ffffff;
}

.profile-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.profile-name-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-name {
  font-size: 24px;
  font-weight: 500;
  color: #191919;
  line-height: 32px;
}

.profile-id {
  font-size: 16px;
  color: #777777;
  line-height: 24px;
}

/* ── sections ── */
.profile-section {
  margin-top: 24px;
  padding: 20px 24px;
  background: #ffffff;
  border-radius: 12px;
}

.section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  color: #191919;
  line-height: 26px;
}

.section-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: #777777;
}

.section-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.section-row-text {
  display: flex;
  flex-direction: column;
}

/* ── info grid ── */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px 32px;
  margin-top: 20px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 40px;
}

.info-label {
  width: 80px;
  font-size: 14px;
  color: #777777;
}

.info-value {
  font-size: 16px;
  color: #191919;
}

.info-value--mono {
  font-family: ui-monospace, monospace;
  font-size: 14px;
}

.info-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #f3f3f3;
}

/* ── tags ── */
.role-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
}

.role-tag--admin {
  color: #ffffff;
  background: #ec6f1a;
}

.role-tag--user {
  color: #ffffff;
  background: #1f55b5;
}

.status-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
  background: #dff4cc;
  color: #316614;
}

/* ── reset form ── */
.reset-form {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 480px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 14px;
  color: #191919;
}

.form-input {
  padding: 11px 12px;
  font-size: 14px;
  color: #191919;
  background: #ffffff;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  outline: none;
  transition: border-color 0.2s;
}

.form-input:focus {
  border-color: #0067d1;
}

.form-input::placeholder {
  color: #aeaeae;
}

.form-actions {
  display: flex;
  gap: 12px;
}

.msg {
  margin: 0;
  font-size: 13px;
}

.msg--error {
  color: #e02128;
}

/* ── buttons ── */
.btn {
  padding: 5px 20px;
  font-size: 14px;
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
  background: #f3f3f3;
}

.btn--secondary:hover {
  background: #e8e8e8;
}

.btn--danger {
  color: #ffffff;
  background: #e02128;
  padding: 5px 34px;
}

.btn--danger:hover {
  background: #c01c22;
}
</style>