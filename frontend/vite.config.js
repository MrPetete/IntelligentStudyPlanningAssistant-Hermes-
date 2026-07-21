import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev server runs on 127.0.0.1:5173 to match backend CORS_ORIGINS.
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true
  }
})
