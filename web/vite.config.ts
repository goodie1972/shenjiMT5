import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'url'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    Components({
      resolvers: [NaiveUiResolver()],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.ALGOFORGE_DASHBOARD_PORT ? `http://127.0.0.1:${process.env.ALGOFORGE_DASHBOARD_PORT}` : 'http://127.0.0.1:1783',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.ALGOFORGE_DASHBOARD_PORT ? `http://127.0.0.1:${process.env.ALGOFORGE_DASHBOARD_PORT}` : 'http://127.0.0.1:1783',
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // ⚠️ 不要用函数式 manualChunks 按 views 拆包：会把共享 store/组件与视图拆成
        // 独立 chunk，产生循环引用初始化顺序问题（页面白屏 "Cannot access 'bt' before initialization"）。
        // 只做安全的 vendor 拆分（2026-09-28 白屏事故教训）。
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-charts': ['lightweight-charts'],
          'vendor-i18n': ['vue-i18n'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
    minify: 'esbuild',
  },
})
