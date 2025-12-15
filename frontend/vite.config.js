import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      // ⭐ 配置 API 代理：/api/* 請求會轉發到 analysis_agent
      '/api': {
        target: process.env.VITE_ANALYSIS_AGENT_URL || 'http://analysis_agent:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // 開發時使用 localhost
        ...(process.env.NODE_ENV === 'development' && {
          target: 'http://localhost:8002'
        })
      }
    }
  }
})