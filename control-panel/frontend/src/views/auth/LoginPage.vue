<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElForm, ElFormItem, ElInput, ElButton, ElCheckbox, type FormInstance, type FormRules } from 'element-plus';
import { findDefaultLandingRouteName } from '@/router/menu';
import { useAuth } from '@/composables/useAuth';
import { login, submitOAuthDecision, getPermissions } from '@/api/auth';
import loginLogo from '@/assets/images/login-logo.png';

const route = useRoute();
const router = useRouter();
const { storeAuth } = useAuth();

const isOAuthMode = route.meta.mode === 'oauth';

const loginFormRef = ref<FormInstance>();
const loginForm = ref({ username: '', password: '' });
const loading = ref(false);
const errorMessage = ref('');

// ── OAuth: params from URL query
const oauthParams = ref({
  client_id: '',
  redirect_uri: '',
  state: '',
  // 客户端展示名称，由后端 oauth2_authorize 注入（环境变量 OAUTH2_CLIENT_NAME）
  client_name: '',
});

// ── OAuth: which step to show
const oauthStep = ref<'login' | 'consent'>('login');
const oauthRemember = ref(false);

const OAUTH_CONSENT_PREFIX = 'oauth_consent:';

const rules: FormRules = {
  username: [{ required: true, message: '请输入账号名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

onMounted(async () => {
  if (!isOAuthMode) return;

  // Read OAuth params from URL query (passed by backend redirect)
  const q = route.query;
  if (q.client_id) oauthParams.value.client_id = String(q.client_id);
  if (q.redirect_uri) oauthParams.value.redirect_uri = String(q.redirect_uri);
  if (q.state) oauthParams.value.state = String(q.state);
  if (q.client_name) oauthParams.value.client_name = String(q.client_name);

  if (!oauthParams.value.client_id || !oauthParams.value.redirect_uri) {
    errorMessage.value = 'OAuth 参数缺失，授权请求无效';
    return;
  }

  // If already logged into CP, verify token then show consent (or auto-authorize)
  const storedUsername = localStorage.getItem('username');
  const accessToken = localStorage.getItem('access_token');
  if (storedUsername && accessToken) {
    try {
      await getPermissions();
      // Token valid — 先填充用户名，供同意页展示与自动授权时回写 consent 记录
      loginForm.value.username = storedUsername;
      // check if user previously chose "remember" for this client
      const consentKey = OAUTH_CONSENT_PREFIX + oauthParams.value.client_id;
      const consentRemembered = localStorage.getItem(consentKey) === storedUsername;
      // 复用已有 oauth_consent:* 记录为 oauthRemember 复选框赋初值
      oauthRemember.value = consentRemembered;
      if (consentRemembered) {
        // Auto-authorize — skip consent page
        handleOAuthDecision('allow');
        return;
      }
      oauthStep.value = 'consent';
      return;
    } catch {
      // token invalid or network error — fall through to clear stale data
    }
    // Token invalid, clear stale data
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    localStorage.removeItem('user_id');
  }
});

async function handleLogin() {
  const form = loginFormRef.value;
  if (!form) return;
  try {
    await form.validate();
  } catch {
    return;
  }

  loading.value = true;
  errorMessage.value = '';
  try {
    const result = await login(loginForm.value.username, loginForm.value.password);

    if (isOAuthMode) {
      storeAuth(result);
      loginForm.value.username = result.username;
      // 未登录场景下登录后必须显示同意页，确保用户有机会取消"记住授权"
      // 仅用历史记录预填复选框，不自动跳过同意步骤
      const consentKey = OAUTH_CONSENT_PREFIX + oauthParams.value.client_id;
      oauthRemember.value = localStorage.getItem(consentKey) === result.username;
      oauthStep.value = 'consent';
    } else {
      storeAuth(result);
      router.push({ name: findDefaultLandingRouteName(result.role === 'admin') });
    }
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '登录失败，请重试';
  } finally {
    loading.value = false;
  }
}

async function handleOAuthDecision(action: 'allow' | 'deny') {
  if (action === 'deny') {
    loading.value = true;
    errorMessage.value = '';
    try {
      const result = await submitOAuthDecision({
        action: 'deny',
        client_id: oauthParams.value.client_id,
        redirect_uri: oauthParams.value.redirect_uri,
        state: oauthParams.value.state,
      });
      window.location.href = result.redirect_uri;
    } catch (e) {
      errorMessage.value = e instanceof Error ? e.message : '操作失败，请重试';
      loading.value = false;
    }
    return;
  }

  // Allow: store consent preference before proceeding
  if (oauthRemember.value) {
    const consentKey = OAUTH_CONSENT_PREFIX + oauthParams.value.client_id;
    localStorage.setItem(consentKey, loginForm.value.username);
  }

  loading.value = true;
  errorMessage.value = '';
  try {
    const result = await submitOAuthDecision({
      action: 'allow',
      client_id: oauthParams.value.client_id,
      redirect_uri: oauthParams.value.redirect_uri,
      state: oauthParams.value.state,
    });
    window.location.href = result.redirect_uri;
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '操作失败，请重试';
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
        <!-- ── OAuth: 同意步骤 ── -->
        <template v-if="isOAuthMode && oauthStep === 'consent'">
          <h1 class="login-dialog__title">授权确认</h1>
          <p style="color: var(--text-secondary); margin: 4px 0 20px; line-height: 1.6">
            <strong>{{ oauthParams.client_name }}</strong>
            想要访问您的账户（{{ loginForm.username }}）
          </p>

          <div v-if="errorMessage" class="oauth-error">{{ errorMessage }}</div>

          <ElCheckbox v-model="oauthRemember" style="margin-bottom: 12px"> 记住授权，下次自动登录 </ElCheckbox>

          <div style="display: flex; gap: 12px">
            <ElButton
              native-type="button"
              type="default"
              style="flex: 1; height: 48px"
              :loading="loading"
              @click="handleOAuthDecision('deny')"
            >
              拒绝
            </ElButton>
            <ElButton
              native-type="button"
              type="primary"
              style="flex: 1; height: 48px"
              :loading="loading"
              @click="handleOAuthDecision('allow')"
            >
              允许
            </ElButton>
          </div>
        </template>

        <!-- ── 默认 / OAuth 登录步骤 ── -->
        <template v-else>
          <p v-if="isOAuthMode" style="color: var(--text-secondary); margin: -16px 0 8px; font-size: 13px">
            <strong>{{ oauthParams.client_name }}</strong> 请求访问您的账户
          </p>

          <div v-if="errorMessage" class="oauth-error">{{ errorMessage }}</div>

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
        </template>
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

.oauth-error {
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  font-size: 13px;
}
</style>
