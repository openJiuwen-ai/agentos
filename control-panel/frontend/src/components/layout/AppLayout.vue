<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { appRouteTree, findTopMenuByKey } from '@/router/menu';
import TopNav from './TopNav.vue';
import SideMenu from './SideMenu.vue';

const route = useRoute();

const activeTopMenu = computed(() => {
  const key = route.meta.topMenu as string | undefined;
  return key ? findTopMenuByKey(appRouteTree, key) : undefined;
});

const sideMenus = computed(() => activeTopMenu.value?.sideMenus ?? []);
const showSideMenu = computed(() => !route.meta.hideSideMenu && sideMenus.value.length > 0);
</script>

<template>
  <div class="app-layout">
    <TopNav />
    <div class="app-layout__body">
      <SideMenu v-if="showSideMenu" :menus="sideMenus" />
      <main class="app-layout__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-page);
}

.app-layout__body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.app-layout__content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}
</style>
