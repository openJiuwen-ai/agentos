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
import profileBannerImg from '@/assets/images/bg.png';
import profileAvatarImg from '@/assets/images/avatar.svg';

const route = useRoute();
const router = useRouter();
const { clearAuth, isAdmin } = useAuth();

type TabKey = 'profile' | 'cloud-account' | 'preferences';

const activeTab = ref<TabKey>((route.query.tab as TabKey) || 'profile');

watch(activeTab, (key) => {
  router.replace({ query: { tab: key } });
});

const profile = ref({
  username: '',
  user_id: '',
  role: '',
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
    { max: 64, message: '新密码长度最多 64 位', trigger: 'blur' },
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
  return (c.hasLower ? 1 : 0) + (c.hasUpper ? 1 : 0) + (c.hasDigit ? 1 : 0) + (c.hasSpecial ? 1 : 0);
});

const passwordLengthOk = computed(
  () => resetForm.value.newPassword.length >= 8 && resetForm.value.newPassword.length <= 64,
);

const passwordHasUsername = computed(() => {
  if (!resetForm.value.newPassword || !profile.value.username) return false;
  return resetForm.value.newPassword.toLowerCase().includes(profile.value.username.toLowerCase());
});

const passwordStrengthValid = computed(
  () => passwordLengthOk.value && passwordCategoryCount.value >= 2 && !passwordHasUsername.value,
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
              effect="plain"
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
            <div class="info-section">
              <div class="info-row info-row--avatar">
                <span class="info-label">头像</span>
                <img class="info-avatar" :src="profileAvatarImg" alt="" />
              </div>

              <div class="info-row info-row--double">
                <div class="info-cell">
                  <span class="info-label">用户名</span>
                  <span class="info-value">{{ profile.username || '—' }}</span>
                </div>
                <div class="info-cell">
                  <span class="info-label">用户ID</span>
                  <span class="info-value">{{ profile.user_id || '—' }}</span>
                </div>
              </div>

              <div class="info-row">
                <div class="info-cell">
                  <span class="info-label">用户角色</span>
                  <ElTag
                    v-if="profile.role"
                    size="small"
                    effect="plain"
                    :class="[
                      profile.role === 'admin' ? 'role-tag role-tag--admin' : 'role-tag role-tag--user',
                      'role-tag--compact',
                    ]"
                  >
                    {{ roleLabel(profile.role) }}
                  </ElTag>
                  <span v-else class="info-value">—</span>
                </div>
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
            <h2 class="profile-card__title profile-card__title--solo">退出登录</h2>
            <ElButton type="danger" plain class="profile-action-btn profile-action-btn--logout" @click="handleLogout">
              退出
            </ElButton>
          </section>
        </ElTabPane>

        <ElTabPane v-if="isAdmin" label="云账户管理" name="cloud-account">
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
            placeholder="8-64 位，需包含至少两类字符"
            autocomplete="new-password"
            :disabled="resetLoading"
          />
          <div v-if="resetForm.newPassword.length > 0" class="strength-checklist">
            <div class="strength-row">
              <span class="strength-counter" :class="passwordLengthOk ? 'check-pass' : 'check-fail'">
                {{ resetForm.newPassword.length }}/64
              </span>
              <span class="strength-label">长度 8-64 位</span>
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
            <div v-if="passwordCategoryCount < 2" class="strength-msg strength-msg--warn">需至少满足两类</div>
            <div v-if="passwordHasUsername" class="strength-msg strength-msg--error">密码不能包含用户名</div>
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
  display: grid;
  grid-template-columns: 1fr;
  min-height: 100%;
  background: var(--bg-1);
}

.profile-banner {
  grid-row: 1;
  grid-column: 1;
  display: block;
  width: 100%;
  aspect-ratio: 1920 / 527;
  max-height: 527px;
  object-fit: cover;
  object-position: center;
}

.profile-content {
  grid-row: 1;
  grid-column: 1;
  z-index: 1;
  width: 100%;
  max-width: 1232px;
  margin: 0 auto;
  padding: 56px 32px 32px;
  display: flex;
  flex-direction: column;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 100px;
}

.profile-avatar {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: var(--bg-2);
  object-fit: cover;
  flex-shrink: 0;
}

.profile-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.profile-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
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
  margin-top: 68px;
}

.profile-tabs :deep(.el-tabs__header) {
  margin-bottom: 24px;
}

.profile-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: var(--border-separator);
}

.profile-tabs :deep(.el-tabs__item) {
  font-size: 16px;
  height: 32px;
  line-height: 24px;
  padding-bottom: 6px;
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
  border-radius: var(--radius-2xl, 24px);
}

.profile-card--row {
  display: flex;
  align-items: flex-start;
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
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: var(--text-primary);
}

.profile-card__title--solo {
  margin-top: 4px;
}

.profile-card__desc {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.profile-action-btn {
  flex-shrink: 0;
  min-width: 88px;
  height: 32px;
  margin: 0;
  padding: 5px 16px;
  font-size: 14px;
  font-weight: 400;
}

.profile-action-btn--logout {
  min-width: 88px;
  padding: 5px 30px;
}

.info-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}

.info-row--avatar {
  display: flex;
  align-items: center;
  gap: 16px;
}

.info-row--double {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 32px 64px;
}

.info-cell {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 24px;
}

.info-label {
  width: 80px;
  flex-shrink: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary);
}

.info-value {
  font-size: 16px;
  line-height: 24px;
  color: var(--text-primary);
}

.info-avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: var(--bg-1);
  object-fit: cover;
}

.role-tag {
  border: none !important;
}

.role-tag--admin {
  color: var(--tag-text-admin) !important;
  background: var(--tag-bg-admin) !important;
}

.role-tag--admin.el-tag--small {
  height: 28px;
  padding: 3px 8px;
  font-size: 14px;
  line-height: 22px;
}

.role-tag--admin.role-tag--compact.el-tag--small {
  height: 20px;
  padding: 0 8px;
  font-size: 12px;
  line-height: 20px;
}

.role-tag--user {
  color: var(--tag-text-info) !important;
  background: var(--tag-bg-info) !important;
}

.reset-hint {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .profile-content {
    padding: 32px 16px 24px;
  }

  .profile-tabs {
    margin-top: 32px;
  }

  .info-row--double {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .profile-card--row {
    flex-direction: column;
    align-items: stretch;
  }

  .profile-action-btn {
    align-self: flex-start;
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
</style>
