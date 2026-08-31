import { createRouter, createWebHistory } from 'vue-router';
import {
  appRouteTree,
  buildRouterRoutes,
  findAdminOnlyRouteNames,
  findUserOnlyRouteNames,
  findDefaultLandingRouteName,
  overviewEnabled,
} from './menu';

const adminOnlyNames = new Set(findAdminOnlyRouteNames(appRouteTree));
const userOnlyNames = new Set(findUserOnlyRouteNames(appRouteTree));

const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...buildRouterRoutes(appRouteTree),
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/auth/LoginPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/oauth/authorize',
      name: 'oauth-authorize',
      component: () => import('@/views/auth/LoginPage.vue'),
      meta: { guest: true, mode: 'oauth' },
    },
    {
      path: '/oauth/error',
      name: 'oauth-error',
      component: () => import('@/views/auth/OAuthErrorPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: { name: 'not-found' },
    },
  ],
});

router.beforeEach((to) => {
  const accessToken = localStorage.getItem('access_token');
  const role = localStorage.getItem('role');
  const isLoggedIn = !!accessToken;
  const isAdmin = role === 'admin';
  const wsIsUser = localStorage.getItem('workspace') === 'user';
  const effectiveIsAdmin = isAdmin && !wsIsUser;

  // guest-only pages (login): redirect to default landing if already logged in
  // Exception: /oauth/authorize must remain accessible when logged in (shows consent page)
  if (to.meta.guest && isLoggedIn && to.name !== 'oauth-authorize') {
    return { name: findDefaultLandingRouteName(effectiveIsAdmin) };
  }

  // overview temporarily disabled
  if (!overviewEnabled && to.name === 'overview') {
    return { name: findDefaultLandingRouteName(effectiveIsAdmin) };
  }

  // shell pages (have topMenu) require auth — redirect to login
  if (to.meta.topMenu !== undefined && !isLoggedIn) {
    return { name: 'login' };
  }

  // admin-only routes: require management workspace (admin role + not personal workspace)
  if (to.name && adminOnlyNames.has(to.name as string) && isLoggedIn && !effectiveIsAdmin) {
    return { name: 'forbidden' };
  }

  // personal-workspace-only routes: redirect when in admin workspace
  if (to.name && userOnlyNames.has(to.name as string) && isLoggedIn && effectiveIsAdmin) {
    return { name: 'forbidden' };
  }

  // admin-only routes (by meta): require management workspace
  if (to.meta.admin && isLoggedIn && !effectiveIsAdmin) {
    return { name: 'forbidden' };
  }
});

export default router;
