import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  build: {
    // MapLibre is loaded after the application shell as a dedicated vendor
    // chunk. Its WebGL renderer is intentionally larger than Vite's generic
    // warning threshold.
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/tiles': 'http://localhost:8001',
    },
  },
  test: {
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
})
