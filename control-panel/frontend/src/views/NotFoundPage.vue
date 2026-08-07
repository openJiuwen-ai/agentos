<script setup lang="ts">
import { useRouter } from 'vue-router';
import { ElResult, ElButton } from 'element-plus';
import { findDefaultLandingRouteName } from '@/router/menu';
import { useAuth } from '@/composables/useAuth';

const router = useRouter();
const { isAdmin, isLoggedIn } = useAuth();

function goHome() {
  if (isLoggedIn.value) {
    router.push({ name: findDefaultLandingRouteName(isAdmin.value) });
    return;
  }
  router.push({ name: 'login' });
}
</script>

<template>
  <section class="page">
    <ElResult icon="error" title="404" sub-title="页面不存在">
      <template #extra>
        <ElButton type="primary" @click="goHome">{{ isLoggedIn ? '返回首页' : '去登录' }}</ElButton>
      </template>
    </ElResult>
  </section>
</template>
