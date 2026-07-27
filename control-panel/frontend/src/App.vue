<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { ElConfigProvider } from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import AppLayout from '@/components/layout/AppLayout.vue';

const route = useRoute();
// Render inside AppLayout (with TopNav) for any shell page.
// All pages except login have topMenu set via the route tree in menu.ts.
const inShell = computed(() => route.meta.topMenu !== undefined);
</script>

<template>
  <ElConfigProvider :locale="zhCn">
    <AppLayout v-if="inShell" />
    <RouterView v-else />
  </ElConfigProvider>
</template>
