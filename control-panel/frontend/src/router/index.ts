import { createRouter, createWebHistory } from 'vue-router';
import { appRouteTree, buildRouterRoutes, findAdminOnlyRouteNames, findDefaultLandingRouteName, overviewEnabled } from './menu';

const adminOnlyNames = new Set(findAdminOnlyRouteNames(appRouteTree));

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

  // guest-only pages (login): redirect to default landing if already logged in
  if (to.meta.guest && isLoggedIn) {
    return { name: findDefaultLandingRouteName(isAdmin) };
  }

  // overview temporarily disabled
  if (!overviewEnabled && to.name === 'overview') {
    return { name: findDefaultLandingRouteName(isAdmin) };
  }

  // shell pages (have topMenu) require auth — redirect to login
  if (to.meta.topMenu !== undefined && !isLoggedIn) {
    return { name: 'login' };
  }

  // admin-only routes (by route name): redirect to 403
  if (to.name && adminOnlyNames.has(to.name as string) && isLoggedIn && !isAdmin) {
    return { name: 'forbidden' };
  }

  // admin-only routes (by meta): redirect to 403
  if (to.meta.admin && isLoggedIn && !isAdmin) {
    return { name: 'forbidden' };
  }
});

export default router;
