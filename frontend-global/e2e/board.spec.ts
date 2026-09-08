// e2e/board.spec.ts — the facts surfaces on a real database (see playwright.config.ts for the
// environment). Every assertion is against rows the scratch database actually holds: the ETF
// count, the 503 S&P 500 members at EOD, SPY's and AAPL's identity and bars.
import { expect, test } from '@playwright/test'

const READY = Boolean(process.env.ATLAS_GLOBAL_DB_URL && process.env.ATLAS_E2E_BYPASS)

// Words that mean a value leaked through unformatted.
const LEAKS = /NaN|Unmapped|undefined/

test.describe('board', () => {
  test.skip(!READY, 'set ATLAS_GLOBAL_DB_URL and ATLAS_E2E_BYPASS (see playwright.config.ts)')

  test('/etfs lists every active ETF through a virtualised table', async ({ page }) => {
    await page.goto('/etfs')
    await expect(page.getByRole('heading', { level: 1, name: 'ETFs' })).toBeVisible()
    const count = page.getByTestId('count')
    await expect(count).toBeVisible()
    const total = Number(await count.getAttribute('data-total'))
    expect(total).toBeGreaterThanOrEqual(5000)
    expect(Number(await count.getAttribute('data-shown'))).toBe(total)

    const dom = await page.locator('tr[data-row]').count()
    expect(dom).toBeGreaterThan(0)
    expect(dom).toBeLessThan(total / 20)

    const rowHeight = await page.locator('tr[data-row]').first().evaluate((el) => el.getBoundingClientRect().height)
    expect(Math.round(rowHeight)).toBe(44)

    await expect(page.getByRole('status').filter({ hasText: 'Prices not loaded yet' })).toBeVisible()
    expect(await page.locator('main').innerText()).not.toMatch(LEAKS)

    // The far end of the list is reachable and rendered.
    await page.locator('.dt').evaluate((el) => {
      el.scrollTop = el.scrollHeight
    })
    await expect(page.locator('tr[data-row]').last()).toBeVisible()
    expect(await page.locator('tr[data-row]').count()).toBeLessThan(total / 20)
  })

  test('/stocks opens on the S&P 500 members and can widen to every listed stock', async ({ page }) => {
    await page.goto('/stocks')
    await expect(page.getByRole('heading', { level: 1, name: 'Stocks' })).toBeVisible()
    const count = page.getByTestId('count')
    await expect(count).toHaveAttribute('data-shown', '503')
    const total = Number(await count.getAttribute('data-total'))
    expect(total).toBeGreaterThan(503)
    expect(await page.locator('main').innerText()).not.toMatch(LEAKS)

    await page.getByRole('radio', { name: /^All/ }).check()
    await expect(count).toHaveAttribute('data-shown', String(total))
    await expect(page).toHaveURL(/sp500=all/)

    // Sorting by listing date puts the oldest listing first.
    await page.getByRole('button', { name: 'Listed' }).click()
    await expect(page).toHaveURL(/sort=listed/)
    const first = await page.locator('tr[data-row]').first().innerText()
    expect(first).toMatch(/19\d\d/)
  })

  test('the search box filters the loaded list, dash spelling included', async ({ page }) => {
    await page.goto('/stocks?sp500=all')
    await page.getByRole('searchbox', { name: 'Search symbol or name' }).fill('brk-b')
    await expect(page.getByTestId('count')).toHaveAttribute('data-shown', '1')
    await expect(page.getByRole('link', { name: 'BRK.B' })).toBeVisible()
    await expect(page).toHaveURL(/q=brk-b/)
  })

  test('/etfs/SPY shows the facts and the bars provenance', async ({ page }) => {
    await page.goto('/etfs/SPY')
    await expect(page.getByRole('heading', { level: 1, name: 'State Street SPDR S&P 500 ETF Trust' })).toBeVisible()
    const main = page.locator('main')
    await expect(main).toContainText('29 Jan 1993')
    await expect(main).toContainText('0000884394')
    await expect(main).toContainText('Stooq CSV')
    await expect(main).toContainText('adjusted closes not yet labelled')
    expect(await main.innerText()).not.toMatch(LEAKS)
  })

  test('/stocks/AAPL shows identity, membership and provenance', async ({ page }) => {
    await page.goto('/stocks/AAPL')
    await expect(page.getByRole('heading', { level: 1, name: 'Apple Inc. - Common Stock' })).toBeVisible()
    const main = page.locator('main')
    await expect(main).toContainText('Information Technology')
    await expect(main).toContainText('current member')
    await expect(main).toContainText('SSGA weekly holdings')
    await expect(main).toContainText('0000320193')
    await expect(main).toContainText('Stooq CSV')
    expect(await main.innerText()).not.toMatch(LEAKS)
  })

  test('a symbol of the other kind is a 404, not a blank page', async ({ page }) => {
    const res = await page.goto('/stocks/SPY')
    expect(res?.status()).toBe(404)
    await expect(page.getByRole('heading', { level: 1, name: 'Nothing here yet' })).toBeVisible()
  })
})
