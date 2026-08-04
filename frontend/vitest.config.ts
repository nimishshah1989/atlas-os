import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    exclude: ['node_modules', '.next', 'playwright'],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
      // src/lib/db.ts imports 'server-only', which throws outside a React Server Component.
      // Vitest is neither; point it at the package's own no-op so query modules are testable.
      // Resolved by path, not specifier — the package's exports field hides ./empty.
      'server-only': resolve(__dirname, 'node_modules/server-only/empty.js'),
    },
  },
})
