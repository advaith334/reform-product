import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxying /api keeps the frontend origin-agnostic: no base URL in the code, and no
// CORS preflight in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
