import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Overridable so a second checkout/worktree can point at its own API port.
      '/api': process.env.VITE_API_TARGET ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
