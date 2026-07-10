<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { appRouteTree, findSideMenuParentKey, type SideMenuItem } from '@/router/menu';

const props = defineProps<{
  menus: SideMenuItem[];
}>();

const route = useRoute();
const router = useRouter();

const expandedKeys = ref<string[]>([]);

const activeRouteName = computed(() => route.name);

function isExpanded(key: string) {
  return expandedKeys.value.includes(key);
}

function isActiveRoute(routeName: SideMenuItem['routeName']) {
  return routeName != null && activeRouteName.value === routeName;
}

function isGroupActive(item: SideMenuItem) {
  if (item.routeName && isActiveRoute(item.routeName)) {
    return true;
  }

  return item.children?.some((child) => isActiveRoute(child.routeName)) ?? false;
}

function toggleExpand(key: string) {
  if (isExpanded(key)) {
    expandedKeys.value = expandedKeys.value.filter((item) => item !== key);
    return;
  }

  expandedKeys.value = [...expandedKeys.value, key];
}

function navigateTo(routeName: SideMenuItem['routeName']) {
  if (routeName == null) return;
  router.push({ name: routeName });
}

function handleLevel2Click(item: SideMenuItem) {
  if (item.children?.length) {
    toggleExpand(item.key);
    return;
  }

  if (item.routeName) {
    navigateTo(item.routeName);
  }
}

function syncExpandedKeys() {
  const parentKey = findSideMenuParentKey(appRouteTree, route.name);
  if (parentKey && !expandedKeys.value.includes(parentKey)) {
    expandedKeys.value = [...expandedKeys.value, parentKey];
  }
}

watch(
  () => route.name,
  () => {
    syncExpandedKeys();
  },
  { immediate: true },
);

watch(
  () => props.menus,
  () => {
    syncExpandedKeys();
  },
  { immediate: true },
);
</script>

<template>
  <aside class="side-menu">
    <ul class="side-menu__list">
      <li v-for="item in menus" :key="item.key" class="side-menu__item">
        <button
          type="button"
          class="side-menu__level2"
          :class="{ 'side-menu__level2--active': isGroupActive(item) }"
          @click="handleLevel2Click(item)"
        >
          <span class="side-menu__icon">
            <img v-if="item.icon" :src="item.icon" :alt="item.label" />
            <span v-else class="side-menu__icon-placeholder" />
          </span>
          <span class="side-menu__label">{{ item.label }}</span>
          <span
            v-if="item.children?.length"
            class="side-menu__arrow"
            :class="{ 'side-menu__arrow--expanded': isExpanded(item.key) }"
          >
            ›
          </span>
        </button>

        <ul v-if="item.children?.length && isExpanded(item.key)" class="side-menu__sublist">
          <li v-for="child in item.children" :key="child.key">
            <button
              type="button"
              class="side-menu__level3"
              :class="{ 'side-menu__level3--active': isActiveRoute(child.routeName) }"
              @click="navigateTo(child.routeName)"
            >
              {{ child.label }}
            </button>
          </li>
        </ul>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.side-menu {
  width: 216px;
  flex-shrink: 0;
  padding: 8px 0 0;
  background: var(--bg-side-nav);
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
}

.side-menu__list,
.side-menu__sublist {
  margin: 0;
  padding: 0;
  list-style: none;
}

.side-menu__item + .side-menu__item {
  margin-top: 0;
}

.side-menu__level2,
.side-menu__level3 {
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition:
    background-color 0.2s,
    color 0.2s;
}

.side-menu__level2 {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 16px;
  border-radius: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.side-menu__level2:hover,
.side-menu__level3:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.side-menu__level2--active,
.side-menu__level3--active {
  background: var(--bg-active);
  color: var(--color-primary);
  font-weight: 400;
}

.side-menu__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.side-menu__icon img {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

.side-menu__icon-placeholder {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 0;
  background: var(--border-color);
}

.side-menu__label {
  flex: 1;
}

.side-menu__arrow {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1;
  transform: rotate(0deg);
  transition: transform 0.2s;
}

.side-menu__arrow--expanded {
  transform: rotate(90deg);
}

.side-menu__sublist {
  margin-top: 0;
  padding-left: 44px;
}

.side-menu__level3 {
  padding: 10px 16px;
  border-radius: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}
</style>
