<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  ElMenu,
  ElMenuItem,
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
} from 'element-plus';
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

const activeTopMenu = computed(() => (route.meta.topMenu as string | undefined) ?? '');

const workspace = ref<'admin' | 'user'>(localStorage.getItem('workspace') === 'user' ? 'user' : 'admin');

const visibleTopMenus = computed(() =>
  isAdmin.value ? topMenus : topMenus.filter((m) => !m.adminOnly),
);

const workspaceLabel = computed(() => (workspace.value === 'admin' ? '管理工作台' : '个人工作台'));

function switchWorkspace(mode: 'admin' | 'user') {
  workspace.value = mode;
  localStorage.setItem('workspace', mode);
  router.push({ name: 'overview' });
}

function goToProfile() {
  router.push({ name: 'profile' });
}

function handleLogout() {
  clearAuth();
  router.push({ name: 'login' });
}

function handleTopMenuSelect(key: string) {
  const menu = visibleTopMenus.value.find((m) => m.key === key);
  if (!menu) return;

  if (menu.routeName) {
    router.push({ name: menu.routeName });
    return;
  }

  if (menu.defaultRouteName) {
    router.push({ name: menu.defaultRouteName });
  }
}

function handleWorkspaceCommand(command: string | number | object) {
  if (command === 'admin' || command === 'user') {
    switchWorkspace(command);
  }
}

function handleProfileCommand(command: string | number | object) {
  if (command === 'profile') goToProfile();
  if (command === 'logout') handleLogout();
}
</script>

<template>
  <header class="top-nav">
    <div class="top-nav__left">
      <img src="/images/logo.png" alt="AgentOS" class="top-nav__logo" />
      <span class="top-nav__brand">AgentOS</span>
      <ElDropdown v-if="isAdmin" trigger="click" @command="handleWorkspaceCommand">
        <button type="button" class="workspace-btn">
          <span>{{ workspaceLabel }}</span>
          <img :src="arrowDownLine" alt="" width="10" height="10" />
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="admin" :class="{ 'is-workspace-active': workspace === 'admin' }">
              管理工作台
            </ElDropdownItem>
            <ElDropdownItem command="user" :class="{ 'is-workspace-active': workspace === 'user' }">
              个人工作台
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
    </div>

    <ElMenu
      :key="activeTopMenu"
      class="top-nav__menu"
      mode="horizontal"
      :ellipsis="false"
      :default-active="activeTopMenu"
      @select="handleTopMenuSelect"
    >
      <ElMenuItem v-for="menu in visibleTopMenus" :key="menu.key" :index="menu.key">
        {{ menu.label }}
      </ElMenuItem>
    </ElMenu>

    <div class="top-nav__right">
      <ElDropdown trigger="click" placement="bottom-end">
        <button type="button" class="top-nav__icon-btn" title="帮助">
          <img :src="helpIcon" alt="帮助" width="20" height="20" />
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem>
              <span class="help-item">
                <span class="help-item__icon">📘</span>
                <span>帮助中心</span>
              </span>
            </ElDropdownItem>
            <ElDropdownItem>
              <span class="help-item">
                <span class="help-item__icon">💬</span>
                <span>反馈问题</span>
              </span>
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <ElDropdown trigger="click" placement="bottom-end" @command="handleProfileCommand">
        <button type="button" class="top-nav__icon-btn" title="个人中心">
          <img :src="personIcon" alt="个人中心" width="20" height="20" />
        </button>
        <template #dropdown>
          <ElDropdownMenu class="profile-dropdown-menu">
            <ElDropdownItem command="profile" class="profile-dropdown-header">
              <div class="profile-header">
                <img class="profile-header__avatar" src="/images/profile-avatar.png" :alt="username" />
                <div class="profile-header__info">
                  <div class="profile-header__name-row">
                    <span class="profile-header__name">{{ username || '用户' }}</span>
                    <span v-if="role" class="role-tag" :class="`role-tag--${role}`">
                      {{ role === 'admin' ? '管理员' : '普通用户' }}
                    </span>
                  </div>
                  <span v-if="userId" class="profile-header__id">用户ID: {{ userId }}</span>
                  <span v-else class="profile-header__id profile-header__id--muted">查看个人资料</span>
                </div>
                <img class="profile-header__arrow" :src="rightArrow" alt="" aria-hidden="true" />
              </div>
            </ElDropdownItem>
            <ElDropdownItem command="logout" divided class="profile-logout">
              <span class="profile-logout__icon" v-html="logoutIcon" />
              <span>退出登录</span>
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
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

.workspace-btn {
  display: inline-flex;
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
  border-color: var(--color-primary);
}

.top-nav__right {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  justify-self: end;
}

.top-nav__icon-btn {
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
  outline: none;
}

.top-nav__icon-btn:hover {
  background: var(--bg-hover);
}

.top-nav__menu {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 48px;
  border-bottom: none;
  background: transparent;
}

.top-nav__menu :deep(.el-menu-item) {
  height: 48px;
  margin: 0 24px;
  padding: 12px 0 0;
  border-bottom: 2px solid transparent !important;
  color: var(--text-secondary);
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
}

.top-nav__menu :deep(.el-menu-item:hover),
.top-nav__menu :deep(.el-menu-item:focus) {
  background: transparent !important;
  color: var(--text-primary);
}

.top-nav__menu :deep(.el-menu-item.is-active) {
  background: transparent !important;
  color: var(--color-primary) !important;
  border-bottom-color: var(--color-primary) !important;
  font-weight: 400;
}

.help-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.help-item__icon {
  width: 20px;
  text-align: center;
  opacity: 0.7;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 248px;
  padding: 4px 0;
}

.profile-header__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f3f3f3;
  flex-shrink: 0;
}

.profile-header__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.profile-header__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-header__name {
  font-size: 15px;
  font-weight: 500;
  color: #191919;
}

.profile-header__id {
  font-size: 12px;
  color: #777777;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-header__id--muted {
  font-style: italic;
}

.profile-header__arrow {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  opacity: 0.5;
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

.profile-logout {
  color: #e02128 !important;
}

.profile-logout__icon {
  display: inline-flex;
  align-items: center;
  margin-right: 8px;
}
</style>

<style>
.is-workspace-active {
  color: var(--color-primary) !important;
  font-weight: 500;
}

.profile-dropdown-menu {
  width: 280px;
  padding: 4px 0 !important;
}

.profile-dropdown-menu .profile-dropdown-header {
  padding: 8px 14px !important;
  height: auto !important;
  line-height: normal !important;
}
</style>
