// frontend-global/playwright/smoke.spec.ts — local-only smoke against `npm run dev` on :3000.
// Both pages must render with NO env vars set (the Vercel preview case): /health shows the
// "no database" state and /login shows the "auth is not configured" state.
import { test, expect } from '@playwright/test'

test('/health renders the operator surface', async ({ page }) => {
  await page.goto('/health')
  await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible()
})

test('/login renders the sign-in surface', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible()
})

test('an unauthenticated visit to / lands on /login', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
})
