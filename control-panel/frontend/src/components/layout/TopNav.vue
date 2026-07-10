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
  height: 48px;
  padding: 0 18px;
  background: var(--bg-top-nav);
  border-bottom: 1px solid var(--border-color);
}

.top-nav__brand {
  justify-self: start;
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: #000;
  white-space: nowrap;
}

.top-nav__menu {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 48px;
}

.top-nav__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  padding: 12px 0 0;
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
  cursor: pointer;
  transition: color 0.2s;
}

.top-nav__item:hover {
  color: var(--text-primary);
  background: transparent;
}

.top-nav__item--active {
  padding-bottom: 2px;
  color: var(--color-primary);
  font-weight: 400;
  background: transparent;
}

.top-nav__item--active::after {
  content: '';
  width: 100%;
  height: 2px;
  border-radius: 1px;
  background: var(--color-primary);
}
</style>
