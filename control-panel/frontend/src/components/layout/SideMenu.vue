<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElButton, ElMenu, ElMenuItem, ElSubMenu, ElTooltip } from 'element-plus';
import { ArrowLeft } from '@element-plus/icons-vue';
import { appRouteTree, findSideMenuParentKey, type SideMenuItem } from '@/router/menu';
import { useAuth } from '@/composables/useAuth';
import collapseIcon from '@/assets/images/collapse.svg';

const props = defineProps<{
  menus: SideMenuItem[];
}>();

const route = useRoute();
const router = useRouter();
const { effectiveIsAdmin } = useAuth();

const visibleMenus = computed(() => {
  if (effectiveIsAdmin.value) {
    return props.menus
      .filter((m) => !m.userOnly)
      .map((m) => {
        const children = m.children?.filter((c) => !c.userOnly);
        return {
          ...m,
          children: children?.length ? children : undefined,
        };
      })
      .filter((m) => m.routeName || m.externalUrl || m.children?.length);
  }

  return props.menus
    .filter((m) => !m.adminOnly)
    .map((m) => {
      const children = m.children?.filter((c) => !c.adminOnly);
      return {
        ...m,
        children: children?.length ? children : undefined,
      };
    })
    .filter((m) => m.routeName || m.externalUrl || m.children?.length);
});

const openedKeys = ref<string[]>([]);
const menuKey = ref(0);
const COLLAPSED_KEY = 'side-menu-collapsed';
const collapsed = ref(localStorage.getItem(COLLAPSED_KEY) === '1');

watch(collapsed, (value) => {
  localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0');
});

const activeIndex = computed(() => {
  const name = route.name;
  if (typeof name !== 'string') return '';

  for (const item of visibleMenus.value) {
    if (item.routeName === name) return item.key;
    const child = item.children?.find((c) => c.routeName === name);
    if (child) return collapsed.value ? item.key : child.key;
  }
  return '';
});

function iconMaskStyle(icon?: string) {
  if (!icon) return undefined;
  return {
    maskImage: `url("${icon}")`,
    WebkitMaskImage: `url("${icon}")`,
    maskMode: 'alpha',
    WebkitMaskSourceType: 'alpha',
  };
}

function findItemByKey(key: string): SideMenuItem | undefined {
  for (const item of visibleMenus.value) {
    if (item.key === key) return item;
    const child = item.children?.find((c) => c.key === key);
    if (child) return child;
  }
  return undefined;
}

function handleSelect(index: string) {
  const item = findItemByKey(index);
  if (item?.externalUrl) {
    window.open(item.externalUrl, '_blank');
    return;
  }
  if (item?.routeName) {
    router.push({ name: item.routeName });
    return;
  }
  const firstChild = item?.children?.find((child) => child.routeName);
  if (firstChild?.routeName) {
    router.push({ name: firstChild.routeName });
  }
}

function collapseSidebar() {
  collapsed.value = true;
}

function expandSidebar() {
  collapsed.value = false;
}

function handleOpen(index: string) {
  if (!openedKeys.value.includes(index)) {
    openedKeys.value = [...openedKeys.value, index];
  }
}

function handleClose(index: string) {
  openedKeys.value = openedKeys.value.filter((k) => k !== index);
}

function syncOpenedKeys() {
  const parentKey = findSideMenuParentKey(appRouteTree, route.name);
  if (parentKey && !openedKeys.value.includes(parentKey)) {
    openedKeys.value = [...openedKeys.value, parentKey];
    menuKey.value += 1;
  }
}

watch(
  () => route.name,
  () => {
    syncOpenedKeys();
  },
  { immediate: true },
);

watch(
  () => props.menus,
  () => {
    syncOpenedKeys();
    menuKey.value += 1;
  },
  { immediate: true },
);
</script>

<template>
  <aside class="side-menu" :class="{ 'is-collapsed': collapsed }">
    <ElMenu
      :key="`${menuKey}-${collapsed}`"
      class="side-menu__el"
      :default-active="activeIndex"
      :default-openeds="collapsed ? [] : openedKeys"
      :unique-opened="false"
      @select="handleSelect"
      @open="handleOpen"
      @close="handleClose"
    >
      <template v-for="item in visibleMenus" :key="item.key">
        <ElMenuItem v-if="collapsed || !item.children?.length" :index="item.key">
          <ElTooltip :content="item.label" placement="right" :disabled="!collapsed" :show-after="200">
            <span class="side-menu__item">
              <span
                class="side-menu__icon"
                :class="{ 'side-menu__icon--placeholder': !item.icon }"
                :style="iconMaskStyle(item.icon)"
                aria-hidden="true"
              />
              <span class="side-menu__label">{{ item.label }}</span>
            </span>
          </ElTooltip>
        </ElMenuItem>

        <ElSubMenu v-else :index="item.key">
          <template #title>
            <span
              class="side-menu__icon"
              :class="{ 'side-menu__icon--placeholder': !item.icon }"
              :style="iconMaskStyle(item.icon)"
              aria-hidden="true"
            />
            <span class="side-menu__label">{{ item.label }}</span>
          </template>
          <ElMenuItem v-for="child in item.children" :key="child.key" :index="child.key">
            {{ child.label }}
          </ElMenuItem>
        </ElSubMenu>
      </template>
    </ElMenu>

    <ElTooltip v-if="collapsed" content="展开" placement="right" :show-after="200">
      <ElButton
        text
        class="side-menu__expand"
        aria-label="展开侧边栏"
        @click="expandSidebar"
      >
        <img :src="collapseIcon" alt="" width="20" height="20" />
      </ElButton>
    </ElTooltip>

    <ElTooltip v-else content="收起" placement="right" :offset="4" :show-after="200">
      <span class="side-menu__ear-wrap">
        <ElButton
          text
          :icon="ArrowLeft"
          class="side-menu__ear"
          aria-label="收起侧边栏"
          @click="collapseSidebar"
        />
      </span>
    </ElTooltip>
  </aside>
</template>

<style scoped>
.side-menu {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 216px;
  flex-shrink: 0;
  padding: 8px 0 0;
  background: var(--bg-2);
  border-right: 1px solid var(--border-separator);
  overflow: visible;
  transition: width 0.2s ease;
}

.side-menu.is-collapsed {
  width: 48px;
  padding: 8px 0 12px;
}

.side-menu__el {
  flex: 1;
  width: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  border-right: none;
  background: transparent;
}

.side-menu__item {
  display: flex;
  align-items: center;
  min-width: 0;
  width: 100%;
}

.side-menu__el :deep(.el-tooltip__trigger) {
  display: flex;
  width: 100%;
}

.side-menu__icon {
  display: inline-block;
  width: 16px;
  height: 16px;
  margin-right: 12px;
  flex-shrink: 0;
  background-color: var(--text-primary);
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-position: center;
  transition: background-color 0.2s;
}

.side-menu__icon--placeholder {
  border-radius: 0;
  background-color: var(--border-separator);
  mask-image: none;
  -webkit-mask-image: none;
}

.side-menu__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.side-menu :deep(.el-menu-item),
.side-menu :deep(.el-sub-menu__title) {
  height: 48px;
  line-height: 22px;
  padding: 13px 16px !important;
  margin: 0;
  border-radius: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 400;
}

.side-menu :deep(.el-menu-item:hover),
.side-menu :deep(.el-sub-menu__title:hover) {
  background: var(--bg-6);
  color: var(--text-primary);
}

.side-menu :deep(.el-menu-item.is-active) {
  background-color: var(--bg-active) !important;
}

/* 选中二级菜单：文字与 icon 变蓝 */
.side-menu :deep(.side-menu__el > .el-menu-item.is-active) {
  color: var(--color-primary) !important;
}

.side-menu :deep(.el-menu-item.is-active .side-menu__icon) {
  background-color: var(--color-primary);
}

/* 选中三级菜单：父级文字与 icon 变蓝；三级文字保持深色 */
.side-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: var(--color-primary);
}

.side-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title .side-menu__icon) {
  background-color: var(--color-primary);
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  color: var(--text-primary) !important;
}

.side-menu :deep(.el-sub-menu .el-menu) {
  background: var(--bg-1);
}

.side-menu :deep(.el-sub-menu .el-menu-item) {
  padding-left: 44px !important;
  min-width: 0;
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  background-color: var(--bg-active) !important;
}

.side-menu :deep(.el-sub-menu__icon-arrow) {
  right: 16px;
  margin-top: -5px;
  font-size: 12px;
  color: var(--text-placeholder);
}

.side-menu.is-collapsed :deep(.el-menu-item) {
  justify-content: center;
  padding: 13px 0 !important;
}

.side-menu.is-collapsed .side-menu__icon {
  margin-right: 0;
}

.side-menu.is-collapsed .side-menu__label {
  display: none;
}

.side-menu.is-collapsed .side-menu__item {
  justify-content: center;
}

.side-menu__ear-wrap {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 2;
  display: block;
  width: 16px;
  height: 48px;
  transform: translate(100%, -50%);
}

.side-menu__ear {
  width: 16px;
  height: 48px;
  min-height: 48px;
  padding: 0;
  margin: 0;
  border: 1px solid var(--border-separator);
  border-left: none;
  border-radius: 0 8px 8px 0;
  background: var(--bg-2);
}

.side-menu__ear:hover {
  background: var(--bg-6);
}

.side-menu__ear :deep(.el-icon) {
  width: 10px;
  height: 10px;
  font-size: 10px;
  color: var(--text-primary);
}

.side-menu__expand {
  width: 100%;
  height: 40px;
  min-height: 40px;
  margin-top: auto;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.side-menu__expand:hover {
  background: var(--bg-6);
}
</style>
