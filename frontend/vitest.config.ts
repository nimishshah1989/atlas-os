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
      // Stub 'server-only' so pure functions from server modules can be
      // imported in the test environment without Next.js throwing.
      'server-only': resolve(__dirname, './src/__mocks__/server-only.ts'),
    },
  },
})
