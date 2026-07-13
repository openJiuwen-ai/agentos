import { createRouter, createWebHistory } from 'vue-router';
import { appRouteTree, buildRouterRoutes, findAdminOnlyRouteNames } from './menu';

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
  ],
});

router.beforeEach((to) => {
  const accessToken = localStorage.getItem('access_token');
  const role = localStorage.getItem('role');
  const isLoggedIn = !!accessToken;
  const isAdmin = role === 'admin';

  // guest-only pages (login): redirect to overview if already logged in
  if (to.meta.guest && isLoggedIn) {
    return { name: 'overview' };
  }

  // shell pages (have topMenu) require auth — redirect to login
  if (to.meta.topMenu !== undefined && !isLoggedIn) {
    return { name: 'login' };
  }

  // admin-only routes (by route name): redirect to 403
  if (to.name && adminOnlyNames.has(to.name) && isLoggedIn && !isAdmin) {
    return { name: 'forbidden' };
  }

  // admin-only routes (by meta): redirect to 403
  if (to.meta.admin && isLoggedIn && !isAdmin) {
    return { name: 'forbidden' };
  }
});

export default router;
