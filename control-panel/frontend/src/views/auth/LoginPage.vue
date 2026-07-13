<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { login } from '@/api/auth';
import { useAuth } from '@/composables/useAuth';

const router = useRouter();
const { storeAuth } = useAuth();

const username = ref('');
const password = ref('');
const showPassword = ref(false);
const loading = ref(false);
const errorMsg = ref('');

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = '请输入账号名和密码';
    return;
  }

  loading.value = true;
  errorMsg.value = '';

  try {
    const result = await login(username.value, password.value);
    storeAuth(result);
    router.push({ name: 'overview' });
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '登录失败，请重试';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <!-- Decorative background elements — matching Figma design -->
    <img
      class="blob blob--bg"
      src="/images/login-bg.png"
      alt=""
      aria-hidden="true"
    />
    <div class="blob blob--top" aria-hidden="true" />
    <div class="blob blob--right" aria-hidden="true" />
    <div class="blob blob--bottom" aria-hidden="true" />
    <div class="blob blob--left" aria-hidden="true" />
    <div class="blob blob--far-right" aria-hidden="true" />

    <!-- Login dialog -->
    <div class="login-dialog">
      <h1 class="login-dialog__title">AgentOS登录</h1>

      <form class="login-dialog__form" @submit.prevent="handleLogin">
        <input
          v-model="username"
          type="text"
          class="login-dialog__input"
          placeholder="账号名"
          autocomplete="username"
          :disabled="loading"
        />

        <div class="login-dialog__password-wrap">
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            class="login-dialog__input login-dialog__input--password"
            placeholder="密码"
            autocomplete="current-password"
            :disabled="loading"
          />
          <button
            type="button"
            class="login-dialog__eye"
            :aria-label="showPassword ? '隐藏密码' : '显示密码'"
            @click="showPassword = !showPassword"
          >
            <img
              v-if="!showPassword"
              src="/images/eye-close.png"
              alt="显示密码"
              width="16"
              height="16"
            />
            <svg
              v-else
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M0.67 8C2.1 4.96 4.87 3 8 3C11.13 3 13.9 4.96 15.33 8C13.9 11.04 11.13 13 8 13C4.87 13 2.1 11.04 0.67 8Z"
                stroke="#aeaeae"
                stroke-width="1.2"
              />
              <circle cx="8" cy="8" r="2.5" stroke="#aeaeae" stroke-width="1.2" />
            </svg>
          </button>
        </div>

        <p v-if="errorMsg" class="login-dialog__error" role="alert">{{ errorMsg }}</p>

        <button
          type="submit"
          class="login-dialog__submit"
          :disabled="loading"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 100vh;
  background: #ffffff;
  overflow: hidden;
}

/* ---- decorative blobs -- match Figma precisely ---- */

.blob {
  position: absolute;
  pointer-events: none;
}

.blob--bg {
  left: -125px;
  top: 69.83px;
  width: 1794.08px;
  height: 1001.35px;
  object-fit: cover;
}

.blob--top {
  left: -75px;
  top: -122.67px;
  width: 1950.19px;
  height: 322.15px;
  background-color: #f8f9fb;
  filter: blur(100px);
}

.blob--right {
  right: -360px;
  top: 465px;
  width: 1360px;
  height: 849px;
  background-color: #eaedf3;
  filter: blur(371px);
  opacity: 0.67;
}

.blob--bottom {
  left: -465.71px;
  bottom: -600px;
  width: 2670.41px;
  height: 1613.2px;
  background-color: #ffffff;
  filter: blur(371px);
}

.blob--left {
  left: -1608px;
  top: 341px;
  width: 1794.08px;
  height: 1467px;
  background-color: #ffffff;
  filter: blur(371px);
}

.blob--far-right {
  right: -200px;
  top: -47px;
  width: 619px;
  height: 1235px;
  background-color: #fbfbfc;
  filter: blur(148px);
}

/* ---- dialog ---- */

.login-dialog {
  position: relative;
  z-index: 1;
  width: 452px;
  max-width: calc(100% - 32px);
  margin-left: 0%;
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
}

/* ---- inputs ---- */

.login-dialog__input {
  width: 100%;
  padding: 11px 12px;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: #191919;
  background-color: #ffffff;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  outline: none;
  transition: border-color 0.2s;
}

.login-dialog__input::placeholder {
  color: #aeaeae;
}

.login-dialog__input:focus {
  border-color: #0067d1;
}

.login-dialog__input:disabled {
  opacity: 0.6;
}

.login-dialog__password-wrap {
  position: relative;
}

.login-dialog__input--password {
  padding-right: 40px;
}

.login-dialog__input--password::-ms-reveal,
.login-dialog__input--password::-ms-clear {
  display: none;
}

.login-dialog__eye {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  line-height: 0;
}

.login-dialog__eye:hover svg path,
.login-dialog__eye:hover svg circle,
.login-dialog__eye:hover svg line {
  stroke: #777777;
}

/* ---- error ---- */

.login-dialog__error {
  margin: 0;
  font-size: 13px;
  line-height: 20px;
  color: #e02128;
}

/* ---- submit button ---- */

.login-dialog__submit {
  width: 100%;
  padding: 12px;
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
  color: #ffffff;
  background-color: #0067d1;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.login-dialog__submit:hover:not(:disabled) {
  background-color: #0055b3;
}

.login-dialog__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
