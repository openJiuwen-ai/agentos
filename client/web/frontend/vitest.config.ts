import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/**
 * Vitest 配置 — Phase 0 引入测试基建。
 * 复用 vite 的 @/ 别名与 react 插件(为后续 .tsx 组件测试预留);
 * environment=node 覆盖纯逻辑测试(cronExpr / cronStore actions),无需 DOM。
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': new URL('./src', import.meta.url).pathname,
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
});
