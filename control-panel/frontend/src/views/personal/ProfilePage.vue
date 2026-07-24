<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ElTabs,
  ElTabPane,
  ElButton,
  ElTag,
  ElForm,
  ElFormItem,
  ElInput,
  ElDialog,
  ElMessage,
  ElMessageBox,
  ElEmpty,
  type FormInstance,
  type FormRules,
} from 'element-plus';
import { getMe, changeMyPassword } from '@/api/users';
import { useAuth } from '@/composables/useAuth';
import profileBannerImg from '@/assets/images/bg.svg';
import profileAvatarImg from '@/assets/images/avatar.svg';

const route = useRoute();
const router = useRouter();
const { clearAuth } = useAuth();

type TabKey = 'profile' | 'cloud-account' | 'preferences';

const activeTab = ref<TabKey>((route.query.tab as TabKey) || 'profile');

watch(activeTab, (key) => {
  router.replace({ query: { tab: key } });
});

const profile = ref({
  username: '',
  user_id: '',
  role: '',
  is_active: true,
  created_at: null as string | null,
});

const showResetDialog = ref(false);
const resetLoading = ref(false);
const resetFormRef = ref<FormInstance>();
const resetForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
});

const resetRules: FormRules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码长度至少 8 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== resetForm.value.newPassword) {
          callback(new Error('两次输入的新密码不一致'));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    },
  ],
};

// ── password strength ──
const passwordChecks = computed(() => ({
  hasLower: /[a-z]/.test(resetForm.value.newPassword),
  hasUpper: /[A-Z]/.test(resetForm.value.newPassword),
  hasDigit: /[0-9]/.test(resetForm.value.newPassword),
  hasSpecial: /[^a-zA-Z0-9]/.test(resetForm.value.newPassword),
}));

const passwordCategoryCount = computed(() => {
  const c = passwordChecks.value;
  return (c.hasLower ? 1 : 0) + (c.hasUpper ? 1 : 0) +
         (c.hasDigit ? 1 : 0) + (c.hasSpecial ? 1 : 0);
});

const passwordLengthOk = computed(() =>
  resetForm.value.newPassword.length >= 8 && resetForm.value.newPassword.length <= 16
);

const passwordHasUsername = computed(() => {
  if (!resetForm.value.newPassword || !profile.value.username) return false;
  return resetForm.value.newPassword.toLowerCase().includes(profile.value.username.toLowerCase());
});

const passwordStrengthValid = computed(() =>
  passwordLengthOk.value && passwordCategoryCount.value >= 2 && !passwordHasUsername.value
);

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

function openResetDialog() {
  resetForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' };
  showResetDialog.value = true;
}

async function handleResetPassword() {
  const form = resetFormRef.value;
  if (!form) return;

  try {
    await form.validate();
  } catch {
    return;
  }

  resetLoading.value = true;
  try {
    await changeMyPassword(resetForm.value.oldPassword, resetForm.value.newPassword);
    ElMessage.success('密码修改成功，请重新登录');
    showResetDialog.value = false;
    clearAuth();
    router.push('/login');
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '密码修改失败');
  } finally {
    resetLoading.value = false;
  }
}

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    });
  } catch {
    return;
  }
  clearAuth();
  router.push('/login');
}
</script>

<template>
  <div class="profile-page">
    <img class="profile-banner" :src="profileBannerImg" alt="" />

    <div class="profile-content">
      <div class="profile-header">
        <img class="profile-avatar" :src="profileAvatarImg" alt="" />
        <div class="profile-meta">
          <div class="profile-name-row">
            <span class="profile-name">{{ profile.username || '—' }}</span>
            <ElTag
              v-if="profile.role"
              size="small"
              effect="dark"
              :class="profile.role === 'admin' ? 'role-tag role-tag--admin' : 'role-tag role-tag--user'"
            >
              {{ roleLabel(profile.role) }}
            </ElTag>
          </div>
          <span v-if="profile.user_id" class="profile-id">用户ID: {{ profile.user_id }}</span>
        </div>
      </div>

      <ElTabs v-model="activeTab" class="profile-tabs">
        <ElTabPane label="个人信息" name="profile">
          <section class="profile-card">
            <h2 class="profile-card__title">基本信息</h2>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">头像</span>
                <img class="info-avatar" :src="profileAvatarImg" alt="" />
              </div>
              <div class="info-item">
                <span class="info-label">用户ID</span>
                <span class="info-value info-value--mono">{{ profile.user_id || '—' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">用户名</span>
                <span class="info-value">{{ profile.username || '—' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">账号状态</span>
                <span
                  class="login-status"
                  :class="profile.is_active ? 'login-status--online' : 'login-status--offline'"
                >
                  <span class="login-status__dot" />
                  {{ profile.is_active ? '正常' : '停用' }}
                </span>
              </div>
              <div class="info-item">
                <span class="info-label">用户角色</span>
                <ElTag
                  v-if="profile.role"
                  size="small"
                  effect="dark"
                  :class="profile.role === 'admin' ? 'role-tag role-tag--admin' : 'role-tag role-tag--user'"
                >
                  {{ roleLabel(profile.role) }}
                </ElTag>
                <span v-else class="info-value">—</span>
              </div>
              <div class="info-item">
                <span class="info-label">手机号</span>
                <span class="info-value">—</span>
              </div>
              <div class="info-item">
                <span class="info-label">邮箱</span>
                <span class="info-value">—</span>
              </div>
            </div>
          </section>

          <section class="profile-card profile-card--row">
            <div class="profile-card__text">
              <h2 class="profile-card__title">重置密码</h2>
              <p class="profile-card__desc">上次重置：—</p>
            </div>
            <ElButton class="profile-action-btn" @click="openResetDialog">重置密码</ElButton>
          </section>

          <section class="profile-card profile-card--row">
            <h2 class="profile-card__title">退出登录</h2>
            <ElButton type="danger" plain class="profile-action-btn" @click="handleLogout">退出</ElButton>
          </section>
        </ElTabPane>

        <ElTabPane label="云账户管理" name="cloud-account">
          <section class="profile-card">
            <ElEmpty description="功能开发中" />
          </section>
        </ElTabPane>

        <ElTabPane label="偏好设置" name="preferences">
          <section class="profile-card">
            <ElEmpty description="功能开发中" />
          </section>
        </ElTabPane>
      </ElTabs>
    </div>

    <ElDialog
      v-model="showResetDialog"
      title="重置密码"
      width="480px"
      destroy-on-close
      @closed="resetFormRef?.resetFields()"
    >
      <p class="reset-hint">修改密码后需要重新登录</p>
      <ElForm
        ref="resetFormRef"
        :model="resetForm"
        :rules="resetRules"
        label-position="top"
        @submit.prevent="handleResetPassword"
      >
        <ElFormItem label="原密码" prop="oldPassword">
          <ElInput
            v-model="resetForm.oldPassword"
            type="password"
            show-password
            autocomplete="current-password"
            :disabled="resetLoading"
          />
        </ElFormItem>
        <ElFormItem label="新密码" prop="newPassword">
          <ElInput
            v-model="resetForm.newPassword"
            type="password"
            show-password
            :class="{ 'form-input--error': resetForm.newPassword.length > 0 && !passwordStrengthValid }"
            placeholder="8-16 位，需包含至少两类字符"
            autocomplete="new-password"
            :disabled="resetLoading"
          />
          <div v-if="resetForm.newPassword.length > 0" class="strength-checklist">
            <div class="strength-row">
              <span class="strength-counter" :class="passwordLengthOk ? 'check-pass' : 'check-fail'">
                {{ resetForm.newPassword.length }}/16
              </span>
              <span class="strength-label">长度 8-16 位</span>
            </div>
            <div class="strength-row">
              <span class="check-mark" :class="passwordChecks.hasLower ? 'check-pass' : 'check-fail'">
                {{ passwordChecks.hasLower ? '✓' : '✗' }}
              </span>
              <span class="strength-label">小写字母 (a-z)</span>
            </div>
            <div class="strength-row">
              <span class="check-mark" :class="passwordChecks.hasUpper ? 'check-pass' : 'check-fail'">
                {{ passwordChecks.hasUpper ? '✓' : '✗' }}
              </span>
              <span class="strength-label">大写字母 (A-Z)</span>
            </div>
            <div class="strength-row">
              <span class="check-mark" :class="passwordChecks.hasDigit ? 'check-pass' : 'check-fail'">
                {{ passwordChecks.hasDigit ? '✓' : '✗' }}
              </span>
              <span class="strength-label">数字 (0-9)</span>
            </div>
            <div class="strength-row">
              <span class="check-mark" :class="passwordChecks.hasSpecial ? 'check-pass' : 'check-fail'">
                {{ passwordChecks.hasSpecial ? '✓' : '✗' }}
              </span>
              <span class="strength-label">特殊字符 (!@#$...)</span>
            </div>
            <div v-if="passwordCategoryCount < 2" class="strength-msg strength-msg--warn">
              需至少满足两类
            </div>
            <div v-if="passwordHasUsername" class="strength-msg strength-msg--error">
              密码不能包含用户名
            </div>
          </div>
        </ElFormItem>
        <ElFormItem label="确认新密码" prop="confirmPassword">
          <ElInput
            v-model="resetForm.confirmPassword"
            type="password"
            show-password
            autocomplete="new-password"
            :disabled="resetLoading"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showResetDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="resetLoading" @click="handleResetPassword"> 保存修改 </ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.profile-page {
  min-height: 100%;
  background: var(--bg-page);
}

.profile-banner {
  display: block;
  width: 100%;
  height: 224px;
  object-fit: cover;
}

.profile-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 32px 32px;
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
  margin-top: -56px;
  border: 4px solid #fff;
  border-radius: 50%;
  background: var(--bg-1);
  object-fit: cover;
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
  line-height: 32px;
  color: var(--text-primary);
}

.profile-id {
  font-size: 16px;
  line-height: 24px;
  color: var(--text-secondary);
}

.profile-tabs {
  margin-top: 8px;
}

.profile-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.profile-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: var(--border-separator);
}

.profile-tabs :deep(.el-tabs__item) {
  font-size: 16px;
  height: 48px;
  line-height: 48px;
  color: var(--text-secondary);
}

.profile-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-primary);
  font-weight: 400;
}

.profile-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--color-primary);
  height: 2px;
  border-radius: 1px;
}

.profile-tabs :deep(.el-tab-pane) {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.profile-card {
  padding: 20px 24px 24px;
  background: var(--bg-2);
  border-radius: 12px;
}

.profile-card--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 20px;
}

.profile-card__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.profile-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: var(--text-primary);
}

.profile-card__desc {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.profile-action-btn {
  width: 96px;
  height: 32px;
  margin: 0;
  padding: 5px 16px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 400;
}

.profile-action-btn.el-button {
  --el-button-bg-color: var(--bg-2);
  --el-button-text-color: var(--text-primary);
  --el-button-border-color: var(--border);
  --el-button-hover-bg-color: var(--bg-mask);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-hover-border-color: var(--border);
  --el-button-active-bg-color: var(--bg-mask);
  --el-button-active-text-color: var(--text-primary);
  --el-button-active-border-color: var(--border);
}

.profile-action-btn.el-button--danger.is-plain {
  --el-button-bg-color: var(--bg-2);
  --el-button-text-color: var(--error);
  --el-button-border-color: var(--error);
  --el-button-hover-bg-color: var(--error-subtler);
  --el-button-hover-text-color: var(--error);
  --el-button-hover-border-color: var(--error);
  --el-button-active-bg-color: var(--error-subtle);
  --el-button-active-text-color: var(--error);
  --el-button-active-border-color: var(--error);
}

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
  flex-shrink: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.info-value {
  font-size: 16px;
  color: var(--text-primary);
}

.info-value--mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 14px;
}

.info-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--bg-1);
  object-fit: cover;
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

.reset-hint {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .info-grid {
    grid-template-columns: 1fr;
  }

  .profile-content {
    padding: 0 16px 24px;
  }
}

.form-input::placeholder {
  color: #aeaeae;
}

.form-input--error {
  border-color: #e02128;
}

.strength-checklist {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.strength-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.check-mark {
  width: 16px;
  text-align: center;
  font-weight: 600;
}

.check-pass {
  color: #09aa71;
}

.check-fail {
  color: #aeaeae;
}

.strength-counter {
  font-weight: 600;
  font-family: ui-monospace, monospace;
  white-space: nowrap;
}

.strength-label {
  color: #777777;
}

.strength-msg {
  margin-top: 4px;
  font-size: 13px;
}

.strength-msg--warn {
  color: #ec6f1a;
}

.strength-msg--error {
  color: #e02128;
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
