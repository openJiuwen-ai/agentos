<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  ElForm,
  ElFormItem,
  ElInput,
  ElButton,
  ElMessage,
  type FormInstance,
  type FormRules,
} from 'element-plus';
import { login } from '@/api/auth';
import { findDefaultLandingRouteName } from '@/router/menu';
import { useAuth } from '@/composables/useAuth';
import loginLogo from '@/assets/images/login-logo.png';

const router = useRouter();
const { storeAuth } = useAuth();

const loginFormRef = ref<FormInstance>();
const loginForm = ref({
  username: '',
  password: '',
});
const loading = ref(false);

const rules: FormRules = {
  username: [{ required: true, message: '请输入账号名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

async function handleLogin() {
  const form = loginFormRef.value;
  if (!form) return;

  try {
    await form.validate();
  } catch {
    return;
  }

  loading.value = true;
  try {
    const result = await login(loginForm.value.username, loginForm.value.password);
    storeAuth(result);
    router.push({ name: findDefaultLandingRouteName(result.role === 'admin') });
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '登录失败，请重试');
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-page__left">
      <div class="login-panel">
        <header class="login-panel__intro">
          <img :src="loginLogo" alt="" class="login-panel__logo" width="64" height="64" />
          <div class="login-panel__copy">
            <h1 class="login-panel__title">欢迎使用华为智能体一体机</h1>
            <p class="login-panel__desc">通过本地部署的 AI 能力，协助你处理日常工作、编写代码并完成复杂任务。</p>
          </div>
        </header>

        <ElForm
          ref="loginFormRef"
          :model="loginForm"
          :rules="rules"
          class="login-panel__form"
          label-position="top"
          hide-required-asterisk
          size="large"
          @submit.prevent="handleLogin"
        >
          <div class="login-panel__fields">
            <ElFormItem label="账号名" prop="username">
              <ElInput
                v-model="loginForm.username"
                placeholder="请输入账号名"
                autocomplete="username"
                :disabled="loading"
              />
            </ElFormItem>

            <ElFormItem label="密码" prop="password">
              <ElInput
                v-model="loginForm.password"
                type="password"
                show-password
                placeholder="请输入密码"
                autocomplete="current-password"
                :disabled="loading"
                @keyup.enter="handleLogin"
              />
            </ElFormItem>
          </div>

          <div class="login-panel__actions">
            <ElButton
              type="primary"
              size="large"
              native-type="button"
              class="login-panel__submit"
              :loading="loading"
              @click="handleLogin"
            >
              登录
            </ElButton>
            <p class="login-panel__hint">暂无账号？请联系系统管理员</p>
          </div>
        </ElForm>
      </div>
    </section>

    <aside class="login-page__right" aria-hidden="true" />
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  width: 100%;
  min-height: 100vh;
  background: var(--bg-1);
  overflow: hidden;
}

.login-page__left,
.login-page__right {
  flex: 1 1 50%;
  min-width: 0;
}

.login-page__left {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.login-page__right {
  min-height: 100vh;
  background: var(--bg-1) url('@/assets/images/login-background.png') center / cover no-repeat;
}

.login-panel {
  width: 432px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 64px;
}

.login-panel__intro {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-panel__logo {
  display: block;
  width: 64px;
  height: 64px;
  object-fit: cover;
}

.login-panel__copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.login-panel__title {
  margin: 0;
  font-size: 36px;
  font-weight: 500;
  line-height: 52px;
  color: var(--text-primary);
}

.login-panel__desc {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  line-height: 24px;
  color: var(--text-secondary);
  text-align: justify;
}

.login-panel__form {
  display: flex;
  flex-direction: column;
  gap: 32px;
  width: 100%;
  --el-input-border-color: var(--border);
  --el-input-hover-border-color: var(--border-hover);
  --el-input-focus-border-color: var(--border-focus);
  --el-input-text-color: var(--text-primary);
  --el-input-placeholder-color: var(--text-placeholder);
  --el-border-radius-base: 4px;
}

.login-panel__fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.login-panel__form :deep(.el-form-item) {
  margin-bottom: 0;
}

.login-panel__form :deep(.el-form-item__label) {
  margin-bottom: 8px;
  padding: 0;
  height: 22px;
  line-height: 22px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-primary);
}

.login-panel__form :deep(.el-input__wrapper) {
  height: 40px;
  padding: 5px 12px;
  border-radius: 4px;
  box-shadow: 0 0 0 1px var(--el-input-border-color) inset;
}

.login-panel__form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--el-input-hover-border-color) inset;
}

.login-panel__form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-input-focus-border-color) inset;
}

.login-panel__form :deep(.el-input__inner) {
  height: 22px;
  font-size: 14px;
  line-height: 22px;
}

.login-panel__actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
}

.login-panel__submit {
  width: 100%;
  height: 40px;
  margin: 0;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  border-radius: 4px;
}

.login-panel__hint {
  margin: 0;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-placeholder);
}

@media (max-width: 960px) {
  .login-page__right {
    display: none;
  }

  .login-page__left {
    flex-basis: 100%;
    padding: 24px 32px;
  }
}
</style>
