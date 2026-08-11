<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMenu, ElMenuItem, ElSubMenu } from 'element-plus';
import { appRouteTree, findSideMenuParentKey, type SideMenuItem } from '@/router/menu';
import { useAuth } from '@/composables/useAuth';

const props = defineProps<{
  menus: SideMenuItem[];
}>();

const route = useRoute();
const router = useRouter();
const { effectiveIsAdmin } = useAuth();

const visibleMenus = computed(() =>
  effectiveIsAdmin.value
    ? props.menus
    : props.menus
        .filter((m) => !m.adminOnly)
        .map((m) => ({
          ...m,
          children: m.children?.filter((c) => !c.adminOnly),
        })),
);

const openedKeys = ref<string[]>([]);
const menuKey = ref(0);

const activeIndex = computed(() => {
  const name = route.name;
  if (typeof name !== 'string') return '';

  for (const item of visibleMenus.value) {
    if (item.routeName === name) return item.key;
    const child = item.children?.find((c) => c.routeName === name);
    if (child) return child.key;
  }
  return '';
});

function iconMaskStyle(icon?: string) {
  if (!icon) return undefined;
  return {
    maskImage: `url(${icon})`,
    WebkitMaskImage: `url(${icon})`,
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
  if (item?.routeName) {
    router.push({ name: item.routeName });
  }
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
  <aside class="side-menu">
    <ElMenu
      :key="menuKey"
      class="side-menu__el"
      :default-active="activeIndex"
      :default-openeds="openedKeys"
      :unique-opened="false"
      @select="handleSelect"
      @open="handleOpen"
      @close="handleClose"
    >
      <template v-for="item in visibleMenus" :key="item.key">
        <ElSubMenu v-if="item.children?.length" :index="item.key">
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

        <ElMenuItem v-else :index="item.key">
          <span
            class="side-menu__icon"
            :class="{ 'side-menu__icon--placeholder': !item.icon }"
            :style="iconMaskStyle(item.icon)"
            aria-hidden="true"
          />
          <span class="side-menu__label">{{ item.label }}</span>
        </ElMenuItem>
      </template>
    </ElMenu>
  </aside>
</template>

<style scoped>
.side-menu {
  width: 216px;
  flex-shrink: 0;
  padding: 8px 0 0;
  background: var(--bg-2);
  border-right: 1px solid var(--border-separator);
  overflow-y: auto;
}

.side-menu__el {
  width: 100%;
  border-right: none;
  background: transparent;
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
</style>
