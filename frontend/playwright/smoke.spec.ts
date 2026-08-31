// frontend/playwright/smoke.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Regime page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('renders regime state headline', async ({ page }) => {
    // One of the four regime states should be visible
    const regimeStates = ['Risk-On', 'Constructive', 'Cautious', 'Risk-Off']
    const found = await Promise.any(
      regimeStates.map((s) =>
        page.getByRole('heading', { level: 1, name: s }).isVisible().then((v) => {
          if (!v) throw new Error()
          return s
        })
      )
    ).catch(() => null)
    expect(found).not.toBeNull()
  })

  test('renders deployment multiplier', async ({ page }) => {
    await expect(page.getByText(/Deployment:/)).toBeVisible()
  })

  test('renders breadth indicators section', async ({ page }) => {
    await expect(page.getByText('Breadth indicators')).toBeVisible()
  })

  test('time range toggle is visible and functional', async ({ page }) => {
    await expect(page.getByRole('group', { name: 'Time range' }).first()).toBeVisible()
    await page.getByRole('button', { name: '1M' }).first().click()
    await expect(page).toHaveURL(/range=1M/)
  })
})
