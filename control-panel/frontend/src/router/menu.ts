import type { RouteRecordRaw } from 'vue-router';
import applianceIcon from '@/assets/icons/appliance.svg';
import inferenceModelIcon from '@/assets/icons/inference-model.svg';
import agentIcon from '@/assets/icons/agent.svg';
import skillStoreIcon from '@/assets/icons/skill-store.svg';

export interface AppRouteNode {
  key: string;
  label: string;
  order: number;
  path?: string;
  name?: string;
  component?: RouteRecordRaw['component'];
  icon?: string;
  defaultChildKey?: string;
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
        component: () => import('@/views/resources/InferenceModelPage.vue'),
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
    key: 'settings',
    label: '系统设置',
    order: 3,
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/settings/SettingsPage.vue'),
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
  const routes: RouteRecordRaw[] = [{ path: '/', redirect: '/overview' }];

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
  children?: SideMenuItem[];
}

export interface TopMenuItem {
  key: string;
  label: string;
  routeName?: string;
  defaultRouteName?: string;
  sideMenus?: SideMenuItem[];
}

function buildSideMenus(nodes: AppRouteNode[]): SideMenuItem[] {
  return sortNodes(nodes).map((node) => ({
    key: node.key,
    label: node.label,
    icon: node.icon,
    routeName: node.name,
    children: node.children ? buildSideMenus(node.children) : undefined,
  }));
}

export function buildTopMenus(tree: AppRouteNode[]): TopMenuItem[] {
  return sortNodes(tree).map((node) => ({
    key: node.key,
    label: node.label,
    routeName: node.name,
    defaultRouteName: node.defaultChildKey ? findRouteNameByKey(node.children ?? [], node.defaultChildKey) : undefined,
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
export const topMenus = buildTopMenus(appRouteTree);

