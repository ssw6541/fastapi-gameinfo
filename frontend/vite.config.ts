import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      port: 5173,
      // In dev the browser talks to Vite; /api is forwarded to FastAPI (no CORS needed).
      proxy: { '/api': { target: env.DEV_API_TARGET || 'http://localhost:8000', changeOrigin: true } },
    },
  }
})
