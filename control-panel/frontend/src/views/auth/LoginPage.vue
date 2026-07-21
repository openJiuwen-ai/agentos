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
import { useAuth } from '@/composables/useAuth';

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
    router.push({ name: 'overview' });
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '登录失败，请重试');
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-dialog">
      <h1 class="login-dialog__title">AgentOS登录</h1>

      <ElForm
        ref="loginFormRef"
        :model="loginForm"
        :rules="rules"
        class="login-dialog__form"
        label-position="top"
        @submit.prevent="handleLogin"
      >
        <ElFormItem prop="username">
          <ElInput
            v-model="loginForm.username"
            placeholder="账号名"
            autocomplete="username"
            :disabled="loading"
          />
        </ElFormItem>

        <ElFormItem prop="password">
          <ElInput
            v-model="loginForm.password"
            type="password"
            show-password
            placeholder="密码"
            autocomplete="current-password"
            :disabled="loading"
            @keyup.enter="handleLogin"
          />
        </ElFormItem>

        <ElButton
          type="primary"
          class="login-dialog__submit"
          :loading="loading"
          @click="handleLogin"
        >
          登录
        </ElButton>
      </ElForm>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 100%;
  min-height: 100vh;
  padding-right: 10%;
  background: #ffffff url('@/assets/images/login-bg.png') center / cover no-repeat;
  overflow: hidden;
}

.login-dialog {
  position: relative;
  z-index: 1;
  width: 452px;
  max-width: calc(100% - 32px);
  margin-right: 0;
  display: flex;
  flex-direction: column;
  gap: 40px;
  padding: 32px;
  background-color: #ffffff;
  border-radius: 8px;
  box-shadow: 0px 16px 48px 0px rgba(0, 0, 0, 0.16);
}

.login-dialog__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: #191919;
}

.login-dialog__form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  --el-input-border-color: #c9c9c9;
  --el-input-border-radius: 4px;
  --el-input-hover-border-color: #c9c9c9;
  --el-input-focus-border-color: var(--el-color-primary);
  --el-input-text-color: #191919;
  --el-input-placeholder-color: #aeaeae;
}

/* remove default form-item bottom margin to honour the 16px gap */
.login-dialog__form :deep(.el-form-item) {
  margin-bottom: 0;
}

.login-dialog__form :deep(.el-input__wrapper) {
  height: 44px;
  border-radius: 4px;
}

/* ---- submit button ---- */
.login-dialog__submit {
  width: 100%;
  height: 48px;
  margin-top: 24px;
  font-size: 16px;
  font-weight: 400;
  border-radius: 4px;
}
</style>
