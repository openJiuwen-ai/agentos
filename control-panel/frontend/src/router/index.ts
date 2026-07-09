import { createRouter, createWebHistory } from 'vue-router';
import { appRouteTree, buildRouterRoutes } from './menu';

const router = createRouter({
  history: createWebHistory(),
  routes: buildRouterRoutes(appRouteTree),
});

export default router;
