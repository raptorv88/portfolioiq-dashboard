import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth':     { target: 'http://localhost:8000', changeOrigin: true },
      '/analysis': { target: 'http://localhost:8000', changeOrigin: true },
      '/history':  { target: 'http://localhost:8000', changeOrigin: true },
      '/health':   { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
