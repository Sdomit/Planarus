import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // Vite's default target is safari14, but the app already hard-requires
    // Safari 15.4+ features (:focus-visible carries every focus ring,
    // <dialog>.showModal drives the modals, 100dvh sizes the shell). Declaring
    // es2022 makes the real floor explicit instead of shipping a bundle that
    // parses on browsers where the UI is visibly broken.
    // Floor: Chrome/Edge 111+, Firefox 113+, Safari 16.4+.
    target: 'es2022',
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    // Only strict when the launcher picked the port: it already proved the port
    // free and printed URLs using it, so Vite's silent +1 fallback would send
    // you to a dead address. Plain `pnpm dev` keeps the friendly fallback.
    strictPort: !!process.env.VITE_PORT,
    proxy: {
      // Overridable so a second checkout/worktree can point at its own API port.
      '/api': process.env.VITE_API_TARGET ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
