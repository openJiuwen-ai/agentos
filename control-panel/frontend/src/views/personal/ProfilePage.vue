<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
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
import profileBannerImg from '@/assets/images/profile-banner.png';
import profileAvatarImg from '@/assets/images/profile-avatar.png';

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
                <ElTag
                  size="small"
                  effect="light"
                  class="status-tag"
                  :class="profile.is_active ? 'status-tag--active' : 'status-tag--inactive'"
                >
                  {{ profile.is_active ? '正常' : '停用' }}
                </ElTag>
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
            placeholder="至少 8 位字符"
            autocomplete="new-password"
            :disabled="resetLoading"
          />
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
        <ElButton type="primary" :loading="resetLoading" @click="handleResetPassword">
          保存修改
        </ElButton>
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
  background: #f3f3f3;
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
  background-color: var(--border-color);
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
  background: #fff;
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
  --el-button-bg-color: #fff;
  --el-button-text-color: rgba(25, 25, 25, 1);
  --el-button-border-color: rgba(201, 201, 201, 1);
  --el-button-hover-bg-color: var(--bg-hover);
  --el-button-hover-text-color: rgba(25, 25, 25, 1);
  --el-button-hover-border-color: rgba(201, 201, 201, 1);
  --el-button-active-bg-color: var(--bg-hover);
  --el-button-active-text-color: rgba(25, 25, 25, 1);
  --el-button-active-border-color: rgba(201, 201, 201, 1);
}

.profile-action-btn.el-button--danger.is-plain {
  --el-button-bg-color: #fff;
  --el-button-text-color: rgba(224, 33, 40, 1);
  --el-button-border-color: rgba(224, 33, 40, 1);
  --el-button-hover-bg-color: rgba(224, 33, 40, 0.05);
  --el-button-hover-text-color: rgba(224, 33, 40, 1);
  --el-button-hover-border-color: rgba(224, 33, 40, 1);
  --el-button-active-bg-color: rgba(224, 33, 40, 0.05);
  --el-button-active-text-color: rgba(224, 33, 40, 1);
  --el-button-active-border-color: rgba(224, 33, 40, 1);
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
  background: #f3f3f3;
  object-fit: cover;
}

.role-tag {
  border: none !important;
}

.role-tag--admin {
  color: #fff !important;
  background: #ec6f1a !important;
}

.role-tag--user {
  color: #fff !important;
  background: #1f55b5 !important;
}

.status-tag {
  border: none !important;
}

.status-tag--active {
  color: #316614 !important;
  background: #dff4cc !important;
}

.status-tag--inactive {
  color: #777 !important;
  background: #f3f3f3 !important;
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
</style>
