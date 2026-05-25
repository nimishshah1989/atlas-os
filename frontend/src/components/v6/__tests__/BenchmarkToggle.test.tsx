// frontend/src/components/v6/__tests__/BenchmarkToggle.test.tsx
//
// Unit tests for BenchmarkToggle + useBenchmarkPreference (6 acceptance criteria).
//
// Mocking strategy:
//   - `next/navigation` → vi.mock with configurable searchParams + router stubs
//   - `localStorage` → jsdom provides a real LS; we spy/clear between tests

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── next/navigation mock ──────────────────────────────────────────────────────

let _searchParamValue: string | null = null
const _routerReplace = vi.fn()
const _pathname = '/v6/stocks'

vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: (key: string) => (key === 'benchmark' ? _searchParamValue : null),
    toString: () => (_searchParamValue != null ? `benchmark=${_searchParamValue}` : ''),
  }),
  useRouter: () => ({ replace: _routerReplace }),
  usePathname: () => _pathname,
}))

// ── Import component AFTER mocks ──────────────────────────────────────────────
import { BenchmarkToggle } from '../BenchmarkToggle'

// ── localStorage helpers ──────────────────────────────────────────────────────

function setLS(pageKey: string, value: string): void {
  window.localStorage.setItem(`v6.benchmark.${pageKey}`, value)
}

function getLS(pageKey: string): string | null {
  return window.localStorage.getItem(`v6.benchmark.${pageKey}`)
}

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  _searchParamValue = null
  _routerReplace.mockClear()
  window.localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('BenchmarkToggle', () => {
  // Case 1 — URL truth: ?benchmark=nifty50 renders nifty50 active
  it('URL param overrides localStorage — renders nifty50 active', () => {
    _searchParamValue = 'nifty50'
    setLS('test-page', 'nifty500') // LS says nifty500 — should be ignored

    render(<BenchmarkToggle pageKey="test-page" goldAvailable={true} />)

    const checked = screen
      .getAllByRole('radio')
      .find((el) => el.getAttribute('aria-checked') === 'true')

    expect(checked).toBeDefined()
    expect(checked?.textContent).toBe('Nifty 50')

    // Confirm nifty500 is NOT active
    const nifty500 = screen.getByRole('radio', { name: 'Nifty 500' })
    expect(nifty500.getAttribute('aria-checked')).toBe('false')
  })

  // Case 2 — LS seed: no URL, LS has 'gold' and goldAvailable=true → renders Gold active
  it('seeds from localStorage when URL param is absent — gold available', () => {
    _searchParamValue = null
    setLS('fund-page', 'gold')

    render(<BenchmarkToggle pageKey="fund-page" goldAvailable={true} />)

    const checked = screen
      .getAllByRole('radio')
      .find((el) => el.getAttribute('aria-checked') === 'true')

    expect(checked?.textContent).toBe('Gold')
  })

  // Case 3 — Click writes both URL + LS
  it('clicking a pill writes URL param and localStorage', async () => {
    const user = userEvent.setup()
    _searchParamValue = null

    render(<BenchmarkToggle pageKey="sector-page" goldAvailable={true} />)

    const nifty50 = screen.getByRole('radio', { name: 'Nifty 50' })
    await user.click(nifty50)

    // URL updated
    expect(_routerReplace).toHaveBeenCalledOnce()
    const [urlArg] = _routerReplace.mock.calls[0] as [string]
    expect(urlArg).toContain('benchmark=nifty50')

    // LS written
    expect(getLS('sector-page')).toBe('nifty50')
  })

  // Case 4 — Default nifty500: no URL, no LS → renders Nifty 500 active
  it('defaults to nifty500 when neither URL nor localStorage has a value', () => {
    _searchParamValue = null

    render(<BenchmarkToggle pageKey="fresh-page" goldAvailable={true} />)

    const checked = screen
      .getAllByRole('radio')
      .find((el) => el.getAttribute('aria-checked') === 'true')

    expect(checked?.textContent).toBe('Nifty 500')
  })

  // Case 5 — Gold-hide: goldAvailable=false → only 2 pills; URL gold → falls back to nifty500
  it('hides Gold pill when goldAvailable=false and falls back from gold URL value to nifty500', () => {
    _searchParamValue = 'gold' // URL says gold, but gold is unavailable

    render(<BenchmarkToggle pageKey="gold-hide-page" goldAvailable={false} />)

    const allPills = screen.getAllByRole('radio')
    expect(allPills).toHaveLength(2)
    expect(screen.getByRole('radio', { name: 'Nifty 50' })).toBeDefined()
    expect(screen.getByRole('radio', { name: 'Nifty 500' })).toBeDefined()
    expect(screen.queryByRole('radio', { name: 'Gold' })).toBeNull()

    // Since gold URL value is unavailable, falls back to nifty500 (default)
    const checked = allPills.find((el) => el.getAttribute('aria-checked') === 'true')
    expect(checked?.textContent).toBe('Nifty 500')
  })

  // Case 6 — Keyboard nav: arrow keys cycle, Home/End jump
  it('keyboard navigation: Right Arrow advances selection, Home/End jump to first/last', async () => {
    const user = userEvent.setup()
    _searchParamValue = null

    render(<BenchmarkToggle pageKey="keyboard-page" goldAvailable={true} />)

    // Default active is nifty500 (index 1). Focus it and press Right.
    const nifty500 = screen.getByRole('radio', { name: 'Nifty 500' })
    nifty500.focus()
    expect(document.activeElement?.textContent).toBe('Nifty 500')

    // Right arrow from nifty500 → Gold
    await user.keyboard('{ArrowRight}')
    const afterRight = _routerReplace.mock.calls.at(-1)?.[0] as string
    expect(afterRight).toContain('benchmark=gold')

    // Home key — jump to first (nifty50)
    const firstPill = screen.getByRole('radio', { name: 'Nifty 50' })
    firstPill.focus()
    await user.keyboard('{Home}')
    const afterHome = _routerReplace.mock.calls.at(-1)?.[0] as string
    expect(afterHome).toContain('benchmark=nifty50')

    // End key — jump to last (Gold)
    await user.keyboard('{End}')
    const afterEnd = _routerReplace.mock.calls.at(-1)?.[0] as string
    expect(afterEnd).toContain('benchmark=gold')
  })
})
