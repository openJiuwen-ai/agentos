<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { topMenus } from '@/router/menu';

const route = useRoute();
const router = useRouter();

const activeTopMenu = computed(() => route.meta.topMenu as string | undefined);

function isActive(key: string) {
  return activeTopMenu.value === key;
}

function handleTopMenuClick(menu: (typeof topMenus)[number]) {
  if (menu.routeName) {
    router.push({ name: menu.routeName });
    return;
  }

  if (menu.defaultRouteName) {
    router.push({ name: menu.defaultRouteName });
  }
}
</script>

<template>
  <header class="top-nav">
    <div class="top-nav__brand">AgentOS</div>
    <nav class="top-nav__menu">
      <button
        v-for="menu in topMenus"
        :key="menu.key"
        type="button"
        class="top-nav__item"
        :class="{ 'top-nav__item--active': isActive(menu.key) }"
        @click="handleTopMenuClick(menu)"
      >
        {{ menu.label }}
      </button>
    </nav>
    <div class="top-nav__spacer" aria-hidden="true" />
  </header>
</template>

<style scoped>
.top-nav {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  height: 56px;
  padding: 0 24px;
  background: var(--bg-top-nav);
  border-bottom: 1px solid var(--border-color);
}

.top-nav__brand {
  justify-self: start;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.top-nav__menu {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.top-nav__item {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s;
}

.top-nav__item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.top-nav__item--active {
  background: var(--bg-active);
  color: var(--color-primary);
  font-weight: 600;
}
</style>
