<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { topMenus } from '@/router/menu';
import { useAuth } from '@/composables/useAuth';
import personIcon from '@/assets/icons/person-line.svg';
import helpIcon from '@/assets/icons/help.svg';
import rightArrow from '@/assets/icons/right-arrow.svg';
import arrowDownLine from '@/assets/icons/arrow-down-line.svg';
import logoutIcon from '@/assets/icons/logout.svg?raw';

const route = useRoute();
const router = useRouter();
const { isAdmin, username, userId, role, clearAuth } = useAuth();

const activeTopMenu = computed(() => route.meta.topMenu as string | undefined);

const workspace = ref<'admin' | 'user'>(localStorage.getItem('workspace') === 'user' ? 'user' : 'admin');
const workspaceOpen = ref(false);
const profileOpen = ref(false);
const helpOpen = ref(false);

const visibleTopMenus = computed(() =>
  isAdmin.value
    ? topMenus
    : topMenus.filter((m) => !m.adminOnly),
);

const workspaceLabel = computed(() => (workspace.value === 'admin' ? '管理工作台' : '个人工作台'));

function switchWorkspace(mode: 'admin' | 'user') {
  workspace.value = mode;
  workspaceOpen.value = false;
  localStorage.setItem('workspace', mode);
  router.push({ name: 'overview' });
}

function openProfile() {
  profileOpen.value = !profileOpen.value;
  if (profileOpen.value) {
    workspaceOpen.value = false;
    helpOpen.value = false;
  }
}

function goToProfile() {
  profileOpen.value = false;
  router.push({ name: 'profile' });
}

function handleLogout() {
  profileOpen.value = false;
  clearAuth();
  router.push({ name: 'login' });
}

function closeAll() {
  workspaceOpen.value = false;
  profileOpen.value = false;
  helpOpen.value = false;
}

function onDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (
    !target.closest('.workspace-switch') &&
    !target.closest('.profile-menu') &&
    !target.closest('.help-menu')
  ) {
    closeAll();
  }
}

onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));

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
    <div class="top-nav__left">
      <img src="/images/logo.png" alt="AgentOS" class="top-nav__logo" />
      <span class="top-nav__brand">AgentOS</span>
      <div v-if="isAdmin" class="workspace-switch">
        <button
          type="button"
          class="workspace-btn"
          @click.stop="workspaceOpen = !workspaceOpen"
        >
          <span>{{ workspaceLabel }}</span>
          <img :src="arrowDownLine" alt="" width="10" height="10" />
        </button>
        <div v-if="workspaceOpen" class="workspace-dropdown">
          <button
            type="button"
            :class="{ 'workspace-dropdown__item--active': workspace === 'admin' }"
            @click="switchWorkspace('admin')"
          >
            管理工作台
          </button>
          <button
            type="button"
            :class="{ 'workspace-dropdown__item--active': workspace === 'user' }"
            @click="switchWorkspace('user')"
          >
            个人工作台
          </button>
        </div>
      </div>
    </div>
    <nav class="top-nav__menu">
      <button
        v-for="menu in visibleTopMenus"
        :key="menu.key"
        type="button"
        class="top-nav__item"
        :class="{ 'top-nav__item--active': isActive(menu.key) }"
        @click="handleTopMenuClick(menu)"
      >
        {{ menu.label }}
      </button>
    </nav>
    <div class="top-nav__right">
      <div class="help-menu">
        <button class="top-nav__help" title="帮助" @click.stop="helpOpen = !helpOpen">
          <img :src="helpIcon" alt="帮助" width="20" height="20" />
        </button>
        <div v-if="helpOpen" class="help-dropdown">
          <a class="help-dropdown__item" href="/docs" target="_blank" rel="noopener" @click.prevent>
            <span class="help-dropdown__icon">📘</span>
            <span>帮助中心</span>
          </a>
          <a class="help-dropdown__item" href="/feedback" target="_blank" rel="noopener" @click.prevent>
            <span class="help-dropdown__icon">💬</span>
            <span>反馈问题</span>
          </a>
        </div>
      </div>
      <div class="profile-menu">
        <button class="top-nav__profile" title="个人中心" @click.stop="openProfile">
          <img :src="personIcon" alt="个人中心" width="20" height="20" />
        </button>
        <div v-if="profileOpen" class="profile-dropdown">
          <button type="button" class="profile-dropdown__header" @click="goToProfile">
            <img class="profile-dropdown__avatar" src="/images/profile-avatar.png" :alt="username" />
            <div class="profile-dropdown__info">
              <div class="profile-dropdown__name-row">
                <span class="profile-dropdown__name">{{ username || '用户' }}</span>
                <span v-if="role" class="role-tag" :class="`role-tag--${role}`">
                  {{ role === 'admin' ? '管理员' : '普通用户' }}
                </span>
              </div>
              <span v-if="userId" class="profile-dropdown__id">用户ID: {{ userId }}</span>
              <span v-else class="profile-dropdown__id profile-dropdown__id--muted">查看个人资料</span>
            </div>
            <img class="profile-dropdown__arrow" :src="rightArrow" alt="" aria-hidden="true" />
          </button>
          <button type="button" class="profile-dropdown__item profile-dropdown__item--danger" @click="handleLogout">
            <span class="profile-dropdown__icon" v-html="logoutIcon" />
            <span>退出登录</span>
          </button>
        </div>
      </div>
    </div>
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

.top-nav__left {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-self: start;
}

.top-nav__logo {
  width: 32px;
  height: 26px;
  object-fit: contain;
}

.top-nav__brand {
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: #000;
  white-space: nowrap;
}

/* workspace switcher */
.workspace-switch {
  position: relative;
}

.workspace-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 14px;
  line-height: 22px;
  color: #191919;
  background: #ffffff;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
}

.workspace-btn:hover {
  border-color: #0067d1;
}

.workspace-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 100;
  min-width: 118px;
  padding: 4px 0;
  background: #ffffff;
  border: 1px solid #c9c9c9;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.workspace-dropdown button {
  display: block;
  width: 100%;
  padding: 6px 16px;
  border: none;
  background: transparent;
  color: #191919;
  font-size: 14px;
  line-height: 22px;
  text-align: left;
  cursor: pointer;
}

.workspace-dropdown button:hover {
  background: var(--bg-hover);
}

.workspace-dropdown__item--active {
  color: var(--color-primary);
  font-weight: 500;
}

/* right column */
.top-nav__right {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  justify-self: end;
}

/* help menu (top right) */
.help-menu {
  position: relative;
}

.top-nav__help {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.2s;
}

.top-nav__help:hover {
  background: var(--bg-hover);
}

.help-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 100;
  min-width: 160px;
  padding: 4px 0;
  background: #ffffff;
  border: 1px solid #dfdfdf;
  border-radius: 6px;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}

.help-dropdown__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  color: #191919;
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 0.15s;
}

.help-dropdown__item:hover {
  background: var(--bg-hover);
}

.help-dropdown__icon {
  width: 20px;
  text-align: center;
  opacity: 0.7;
}

/* profile menu (top right) */
.profile-menu {
  position: relative;
}

.top-nav__profile {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.2s;
}

.top-nav__profile:hover {
  background: var(--bg-hover);
}

.profile-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 100;
  width: 280px;
  padding: 4px 0;
  background: #ffffff;
  border: 1px solid #dfdfdf;
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.profile-dropdown__header {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s;
}

.profile-dropdown__header:hover {
  background: var(--bg-hover);
}

.profile-dropdown__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f3f3f3;
  flex-shrink: 0;
}

.profile-dropdown__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.profile-dropdown__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-dropdown__name {
  font-size: 15px;
  font-weight: 500;
  color: #191919;
}

.profile-dropdown__id {
  font-size: 12px;
  color: #777777;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-dropdown__id--muted {
  font-style: italic;
}

.profile-dropdown__arrow {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  opacity: 0.5;
}

.profile-dropdown__icon {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.role-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 16px;
  flex-shrink: 0;
}

.role-tag--admin {
  color: #ffffff;
  background: #ec6f1a;
}

.role-tag--user {
  color: #ffffff;
  background: #1f55b5;
}

.profile-dropdown__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 14px;
  border: none;
  background: transparent;
  color: #191919;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s;
  border-top: 1px solid #f3f3f3;
}

.profile-dropdown__item:hover {
  background: var(--bg-hover);
}

.profile-dropdown__item--danger {
  color: #e02128;
}

.profile-dropdown__item--danger:hover {
  background: #fff5f5;
}

/* menus */
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
