<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import AppLayout from '@/components/layout/AppLayout.vue';

const route = useRoute();
// Render inside AppLayout (with TopNav) for any shell page.
// All pages except login have topMenu set via the route tree in menu.ts.
const inShell = computed(() => route.meta.topMenu !== undefined);
</script>

<template>
  <AppLayout v-if="inShell" />
  <RouterView v-else />
</template>
