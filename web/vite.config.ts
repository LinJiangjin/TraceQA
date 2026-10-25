import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// API 走同源 /api，由 vite dev server 代理到本机的 uvicorn（8000）。
// 这样前端代码里不出现任何硬编码端口，部署时换成 nginx 反代即可。
const API_TARGET = process.env.TRACEQA_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // 显式绑 127.0.0.1：默认的 'localhost' 在这台机器上解析成 [::1]，
    // 只监听 IPv6，导致 http://127.0.0.1:5173 打不开。
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/healthz': { target: API_TARGET, changeOrigin: true },
    },
  },
})
