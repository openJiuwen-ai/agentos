import type { RouteRecordRaw } from 'vue-router';
import applianceIcon from '@/assets/images/appliance.svg';
import inferenceModelIcon from '@/assets/images/inference-model.svg';
import agentIcon from '@/assets/images/agent.svg';
import skillStoreIcon from '@/assets/images/skill-store.svg';
import alarmIcon from '@/assets/images/alarm.svg';
import userManagementIcon from '@/assets/images/user-management.svg';
import logCenterIcon from '@/assets/images/log-center.svg';

/** 总览页面临时下线：恢复时改为 true 并去掉 hideInMenu */
export const overviewEnabled = false;

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
    hideInMenu: !overviewEnabled,
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
        path: '/resources/appliance/:node?',
        name: 'appliance',
        icon: applianceIcon,
        adminOnly: true,
        component: () => import('@/views/resources/appliance/AppliancePage.vue'),
      },
      {
        key: 'inference-model',
        label: '推理模型',
        order: 2,
        icon: inferenceModelIcon,
        defaultChildKey: 'inference-model-dashboard',
        children: [
          {
            key: 'inference-model-dashboard',
            label: '模型监控',
            order: 1,
            path: '/resources/inference-model',
            name: 'inference-model-dashboard',
            component: () => import('@/views/resources/inference-model/InferenceModelDashboard.vue'),
          },
          {
            key: 'inference-model-api-key',
            label: 'API Key',
            order: 2,
            path: '/resources/inference-model/api-key',
            name: 'inference-model-api-key',
            component: () => import('@/views/resources/inference-model/InferenceApiKeyPage.vue'),
          },
          {
            key: 'inference-model-call-analysis',
            label: '推理模型调用分析',
            order: 3,
            path: '/resources/inference-model/call-analysis',
            name: 'inference-model-call-analysis',
            component: () => import('@/views/resources/inference-model/InferenceModelCallAnalysisPage.vue'),
            hideInMenu: true,
            hideSideMenu: true,
          },
          {
            key: 'node-service',
            label: '推理服务节点',
            order: 4,
            path: '/resources/inference-model/node-service',
            name: 'node-service',
            component: () => import('@/views/resources/inference-model/NodeServicePage.vue'),
            adminOnly: true,
          },
          {
            key: 'inference-model-detail',
            label: '推理模型详情',
            order: 4,
            path: '/resources/inference-model/:id',
            name: 'inference-model-detail',
            component: () => import('@/views/resources/inference-model/InferenceModelDetail.vue'),
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
            adminOnly: true,
            component: () => import('@/views/resources/agent/AgentMonitorPage.vue'),
          },
          {
            key: 'agent-framework',
            label: '三方智能体管理',
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
      {
        key: 'alarm',
        label: '告警',
        order: 5,
        path: '/resources/alarm',
        name: 'alarm',
        icon: alarmIcon,
        component: () => import('@/views/resources/AlarmPage.vue'),
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
      {
        key: 'log-explore',
        label: '日志预览',
        order: 6,
        path: '/system/log-center/explore',
        name: 'log-explore',
        component: () => import('@/views/system/GrafanaExplorePage.vue'),
        hideInMenu: true,
        hideSideMenu: true,
        adminOnly: true,
      },
    ],
  },
  {
    key: 'task-center',
    label: '任务中心',
    order: 9,
    path: '/task-center',
    name: 'task-center',
    component: () => import('@/views/system/TaskCenterPage.vue'),
    hideInMenu: true,
    hideSideMenu: true,
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
  {
    key: 'not-found',
    label: '404',
    order: 12,
    path: '/404',
    name: 'not-found',
    component: () => import('@/views/NotFoundPage.vue'),
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

export function findFirstAccessibleSideMenuRoute(
  menus: SideMenuItem[] | undefined,
  isAdmin: boolean,
): string | undefined {
  if (!menus) {
    return undefined;
  }

  for (const item of menus) {
    if (item.adminOnly && !isAdmin) {
      continue;
    }
    if (item.routeName) {
      return item.routeName;
    }
    const nested = findFirstAccessibleSideMenuRoute(item.children, isAdmin);
    if (nested) {
      return nested;
    }
  }

  return undefined;
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

/** 登录后 / 返回首页时的默认路由（总览关闭时落到首个可访问菜单） */
export function findDefaultLandingRouteName(isAdmin: boolean): string {
  if (overviewEnabled) {
    return 'overview';
  }

  const menus = isAdmin ? topMenus : topMenus.filter((menu) => !menu.adminOnly);
  for (const menu of menus) {
    if (menu.routeName) {
      return menu.routeName;
    }

    if (menu.defaultRouteName) {
      const adminOnlyNames = findAdminOnlyRouteNames(appRouteTree);
      let target = menu.defaultRouteName;
      if (!isAdmin && adminOnlyNames.includes(target)) {
        target = findFirstAccessibleSideMenuRoute(menu.sideMenus, false) ?? target;
      }
      return target;
    }
  }

  return 'inference-model-dashboard';
}
