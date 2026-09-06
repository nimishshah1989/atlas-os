// Local-only browser smoke. Not run in CI (CI runs tsc + vitest). One dev server on :3000 serves
// both suites; the suites decide from the environment what they can assert:
//
//   playwright/   the no-env case (a Vercel preview): /health and /login render, / redirects.
//   e2e/          the board on a real database — needs a signed-in user, so it runs only when
//                 ATLAS_GLOBAL_DB_URL and ATLAS_E2E_BYPASS are set, and skips itself otherwise.
//
// ATLAS_E2E_BYPASS=<email> makes `next dev` treat every request as that address WITHOUT a
// Supabase session (src/lib/e2e.ts). The allowlist is still consulted: e2e/global-setup.ts
// inserts the address into atlas_global.app_user of the database the smoke runs against (role
// analyst). It is honoured only when NODE_ENV is not 'production' — `next build` inlines
// NODE_ENV='production' into every bundle, so a built deployment cannot honour it at all; that
// is why the board suite runs on `next dev`, and why the redirect test below is skipped under it.
//
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
//   ATLAS_GLOBAL_DB_URL=postgresql://postgres:postgres@localhost:5432/atlas_p1g \
//   ATLAS_E2E_BYPASS=smoke@localhost npm run test:e2e
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: ['playwright/**/*.spec.ts', 'e2e/**/*.spec.ts'],
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000/health',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
