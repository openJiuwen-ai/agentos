import type { RouteRecordRaw } from 'vue-router';
import applianceIcon from '@/assets/icons/appliance.svg';
import inferenceModelIcon from '@/assets/icons/inference-model.svg';
import agentIcon from '@/assets/icons/agent.svg';
import skillStoreIcon from '@/assets/icons/skill-store.svg';
import userManagementIcon from '@/assets/icons/user-management.svg';
import logCenterIcon from '@/assets/icons/log-center.svg';

export interface AppRouteNode {
  key: string;
  label: string;
  order: number;
  path?: string;
  name?: string;
  component?: RouteRecordRaw['component'];
  icon?: string;
  defaultChildKey?: string;
  hideInMenu?: boolean;
  hideSideMenu?: boolean;
  /** When true, only admins see this item in menus and can access its route. */
  adminOnly?: boolean;
  children?: AppRouteNode[];
}

/** 路由与菜单的单一数据源：增删改路由只需维护此配置 */
export const appRouteTree: AppRouteNode[] = [
  {
    key: 'overview',
    label: '总览',
    order: 1,
    path: '/overview',
    name: 'overview',
    component: () => import('@/views/overview/OverviewPage.vue'),
  },
  {
    key: 'resources',
    label: '资源管理',
    order: 2,
    defaultChildKey: 'appliance',
    children: [
      {
        key: 'appliance',
        label: '一体机',
        order: 1,
        path: '/resources/appliance',
        name: 'appliance',
        icon: applianceIcon,
        component: () => import('@/views/resources/AppliancePage.vue'),
      },
      {
        key: 'inference-model',
        label: '推理模型',
        order: 2,
        path: '/resources/inference-model',
        name: 'inference-model',
        icon: inferenceModelIcon,
        component: () => import('@/views/resources/inference-model/InferenceModelListPage.vue'),
        children: [
          {
            key: 'inference-model-call-analysis',
            label: '推理模型调用分析',
            order: 1,
            path: '/resources/inference-model/call-analysis',
            name: 'inference-model-call-analysis',
            component: () => import('@/views/resources/inference-model/InferenceModelCallAnalysisPage.vue'),
            hideInMenu: true,
            hideSideMenu: true,
          },
          {
            key: 'inference-model-detail',
            label: '推理模型详情',
            order: 2,
            path: '/resources/inference-model/:id',
            name: 'inference-model-detail',
            component: () => import('@/views/resources/inference-model/InferenceModelDetailPage.vue'),
            hideInMenu: true,
            hideSideMenu: true,
          },
        ],
      },
      {
        key: 'agent',
        label: '智能体',
        order: 3,
        icon: agentIcon,
        children: [
          {
            key: 'agent-monitor',
            label: '智能体监控',
            order: 1,
            path: '/resources/agent/monitor',
            name: 'agent-monitor',
            component: () => import('@/views/resources/agent/AgentMonitorPage.vue'),
          },
          {
            key: 'agent-framework',
            label: '框架管理',
            order: 2,
            path: '/resources/agent/framework',
            name: 'agent-framework',
            component: () => import('@/views/resources/agent/FrameworkPage.vue'),
          },
        ],
      },
      {
        key: 'skill-store',
        label: '技能库',
        order: 4,
        path: '/resources/skill-store',
        name: 'skill-store',
        icon: skillStoreIcon,
        component: () => import('@/views/resources/SkillStorePage.vue'),
      },
    ],
  },
  {
    key: 'system',
    label: '系统设置',
    order: 3,
    defaultChildKey: 'user-management',
    adminOnly: true,
    children: [
      {
        key: 'user-management',
        label: '用户管理',
        order: 1,
        path: '/system/user-management',
        name: 'user-management',
        icon: userManagementIcon,
        adminOnly: true,
        component: () => import('@/views/system/UserManagementPage.vue'),
      },
      {
        key: 'log-center',
        label: '日志中心',
        order: 3,
        path: '/system/log-center',
        name: 'log-center',
        icon: logCenterIcon,
        component: () => import('@/views/system/LogCenterPage.vue'),
      },
    ],
  },
  {
    key: 'profile',
    label: '个人中心',
    order: 10,
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/personal/ProfilePage.vue'),
    hideInMenu: true,
  },
  {
    key: 'forbidden',
    label: '403',
    order: 11,
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/ForbiddenPage.vue'),
    hideInMenu: true,
  },
];

function sortNodes(nodes: AppRouteNode[]) {
  return [...nodes].sort((a, b) => a.order - b.order);
}

function findRouteNameByKey(nodes: AppRouteNode[], key: string): string | undefined {
  for (const node of nodes) {
    if (node.key === key) {
      return node.name;
    }

    if (node.children) {
      const matched = findRouteNameByKey(node.children, key);
      if (matched) {
        return matched;
      }
    }
  }

  return undefined;
}

export function buildRouterRoutes(tree: AppRouteNode[]): RouteRecordRaw[] {
  const routes: RouteRecordRaw[] = [{ path: '/', redirect: '/login' }];

  function walk(nodes: AppRouteNode[], topMenuKey: string) {
    for (const node of nodes) {
      if (node.component && node.path && node.name) {
        routes.push({
          path: node.path,
          name: node.name,
          component: node.component,
          meta: {
            title: node.label,
            topMenu: topMenuKey,
            hideSideMenu: node.hideSideMenu,
          },
        });
      }

      if (node.children) {
        walk(node.children, topMenuKey);
      }
    }
  }

  for (const topNode of sortNodes(tree)) {
    if (topNode.component && topNode.path && topNode.name) {
      routes.push({
        path: topNode.path,
        name: topNode.name,
        component: topNode.component,
        meta: {
          title: topNode.label,
          topMenu: topNode.key,
          hideSideMenu: topNode.hideSideMenu,
        },
      });
    }

    if (topNode.children) {
      walk(topNode.children, topNode.key);
    }
  }

  return routes;
}

export interface SideMenuItem {
  key: string;
  label: string;
  icon?: string;
  routeName?: string;
  adminOnly?: boolean;
  children?: SideMenuItem[];
}

export interface TopMenuItem {
  key: string;
  label: string;
  routeName?: string;
  defaultRouteName?: string;
  adminOnly?: boolean;
  sideMenus?: SideMenuItem[];
}

function buildSideMenus(nodes: AppRouteNode[]): SideMenuItem[] {
  return sortNodes(nodes)
    .filter((node) => !node.hideInMenu)
    .map((node) => {
      const menuChildren = node.children?.filter((child) => !child.hideInMenu);
      return {
        key: node.key,
        label: node.label,
        icon: node.icon,
        routeName: node.name,
        adminOnly: node.adminOnly,
        children: menuChildren?.length ? buildSideMenus(menuChildren) : undefined,
      };
    });
}

export function buildTopMenus(tree: AppRouteNode[]): TopMenuItem[] {
  return sortNodes(tree)
    .filter((node) => !node.hideInMenu)
    .map((node) => ({
    key: node.key,
    label: node.label,
    routeName: node.name,
    defaultRouteName: node.defaultChildKey ? findRouteNameByKey(node.children ?? [], node.defaultChildKey) : undefined,
    adminOnly: node.adminOnly,
    sideMenus: node.children ? buildSideMenus(node.children) : undefined,
  }));
}

export function findTopMenuByKey(tree: AppRouteNode[], key: string) {
  return buildTopMenus(tree).find((menu) => menu.key === key);
}

export function findSideMenuParentKey(tree: AppRouteNode[], routeName: string | symbol | null | undefined) {
  if (!routeName || typeof routeName !== 'string') {
    return null;
  }

  function walk(nodes: AppRouteNode[], parentKey: string | null): string | null {
    for (const node of nodes) {
      if (node.name === routeName) {
        return parentKey;
      }

      if (node.children) {
        const nextParentKey = node.name ? parentKey : node.key;
        const matched = walk(node.children, nextParentKey);
        if (matched) {
          return matched;
        }
      }
    }

    return null;
  }

  for (const topNode of tree) {
    if (topNode.children) {
      const matched = walk(topNode.children, null);
      if (matched) {
        return matched;
      }
    }
  }

  return null;
}

export function findAdminOnlyRouteNames(tree: AppRouteNode[]): string[] {
  const names: string[] = [];

  function walk(nodes: AppRouteNode[]) {
    for (const node of nodes) {
      if (node.adminOnly && node.name) {
        names.push(node.name);
      }
      if (node.children) {
        walk(node.children);
      }
    }
  }

  walk(tree);
  return names;
}

export const topMenus = buildTopMenus(appRouteTree);
