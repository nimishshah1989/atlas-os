// frontend/playwright/smoke.spec.ts
import { test, expect } from '@playwright/test'

const PASSWORD = process.env.ATLAS_PASSWORD ?? 'test123'

test.describe('Auth gate', () => {
  test('redirects unauthenticated users to /login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
  })

  test('login page renders the form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Atlas-OS' })).toBeVisible()
    await expect(page.getByPlaceholder('Password')).toBeVisible()
  })

  test('correct password grants access', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL('/')
  })

  test('wrong password stays on login', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('Password').fill('wrong')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/login/)
  })
})

test.describe('Regime page', () => {
  test.beforeEach(async ({ page }) => {
    // Authenticate first
    await page.goto('/login')
    await page.getByPlaceholder('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForURL('/')
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
