// frontend/playwright/daily-brief.spec.ts
// Smoke tests for the SP05 daily-brief route and a regression check that
// the sectors page still renders after wiring mv_sector_rotation_state.
import { test, expect } from '@playwright/test'

const PASSWORD = process.env.ATLAS_PASSWORD ?? 'test123'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByPlaceholder('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL('/')
}

test.describe('Daily brief page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('renders eyebrow and returns 200', async ({ page }) => {
    const response = await page.goto('/intelligence/daily-brief')
    expect(response?.status()).toBeLessThan(400)
    // Eyebrow text appears in both the empty state and the loaded state.
    await expect(page.getByText(/Atlas · Daily Brief/i)).toBeVisible()
  })

  test('renders either a brief headline or the empty state', async ({ page }) => {
    await page.goto('/intelligence/daily-brief')
    // Either DD-MMM-YYYY headline (loaded) or "No brief generated yet" (empty).
    const loaded = page.locator('h1').first()
    await expect(loaded).toBeVisible()
    const text = (await loaded.textContent()) ?? ''
    expect(text.length).toBeGreaterThan(0)
  })
})

test.describe('Sectors page regression', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('sectors page still loads after mv_sector_rotation_state wiring', async ({ page }) => {
    const response = await page.goto('/sectors')
    expect(response?.status()).toBeLessThan(400)
    // Header band is the load-bearing element added by SectorViews.
    await expect(
      page.getByRole('heading', { name: /Sector Regime/i, level: 1 }),
    ).toBeVisible()
  })
})
