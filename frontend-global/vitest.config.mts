// ESM on purpose (.mts): Vite's native config loader would otherwise warn about ESM syntax in a
// file it loads as CommonJS.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

const here = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Globals are on for @testing-library/react's automatic cleanup (it looks for afterEach);
    // test files still import describe/it/expect from 'vitest' explicitly for typing.
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['node_modules', '.next', 'playwright'],
  },
  resolve: {
    alias: {
      '@': `${here}src`,
      // src/lib/db.ts imports 'server-only', which throws outside a React Server Component.
      // Point vitest at the package's own no-op so query modules stay importable in tests.
      'server-only': `${here}node_modules/server-only/empty.js`,
    },
  },
})
