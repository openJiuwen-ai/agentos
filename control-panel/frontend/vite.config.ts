import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // Proxy for local debugging — set VITE_PROXY_TARGET before running:
  //   PowerShell: $env:VITE_PROXY_TARGET="http://{HOST}:{PORT}"; npm run dev
  //   CMD:        set VITE_PROXY_TARGET=http://{HOST}:{PORT} && npm run dev
  //   Git Bash:   export VITE_PROXY_TARGET=http://{HOST}:{PORT} && npm run dev
  server: process.env.VITE_PROXY_TARGET
    ? {
        proxy: {
          '/api': {
            target: process.env.VITE_PROXY_TARGET,
            changeOrigin: true,
          },
        },
      }
    : undefined
});
