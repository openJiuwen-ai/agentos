<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();
const errorMessage = computed(() => {
  const msg = route.query.oauth_error;
  if (Array.isArray(msg)) return msg[0] || '授权请求失败';
  return (msg as string) || '授权请求失败';
});
</script>

<template>
  <div class="login-page">
    <div class="login-dialog">
      <h1 class="login-dialog__title">授权失败</h1>
      <p style="color: var(--text-secondary); margin: 8px 0 24px">{{ errorMessage }}</p>
      <a href="/" class="login-dialog__link">返回首页</a>
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
  background: var(--bg-2) url('@/assets/images/login-background.png') center / cover no-repeat;
}

.login-dialog {
  position: relative;
  z-index: 1;
  width: 452px;
  max-width: calc(100% - 32px);
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 32px;
  background-color: var(--bg-2);
  border-radius: 8px;
  box-shadow: 0px 16px 48px 0px rgba(0, 0, 0, 0.16);
  text-align: center;
}

.login-dialog__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: var(--text-primary);
}

.login-dialog__link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-size: 14px;
}
</style>
