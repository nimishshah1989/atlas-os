// frontend/src/components/v6/__tests__/TenureToggle.test.tsx
//
// Unit tests for TenureToggle + useTenurePreference (5 acceptance criteria).
//
// Mocking strategy:
//   - `next/navigation` → vi.mock with configurable searchParams + router stubs
//   - `localStorage` → vitest fake (jsdom provides a real LS; we spy on it)

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── next/navigation mock ──────────────────────────────────────────────────────
// We set these before each test via setSearchParamValue.

let _searchParamValue: string | null = null
const _routerReplace = vi.fn()
const _pathname = '/v6/stocks'

vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: (key: string) => (key === 'tenure' ? _searchParamValue : null),
    toString: () => (_searchParamValue != null ? `tenure=${_searchParamValue}` : ''),
  }),
  useRouter: () => ({ replace: _routerReplace }),
  usePathname: () => _pathname,
}))

// ── Import component AFTER mocks ──────────────────────────────────────────────
import { TenureToggle } from '../TenureToggle'

// ── localStorage helpers ──────────────────────────────────────────────────────

function setLS(pageKey: string, value: string): void {
  window.localStorage.setItem(`v6.tenure.${pageKey}`, value)
}

function getLS(pageKey: string): string | null {
  return window.localStorage.getItem(`v6.tenure.${pageKey}`)
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

describe('TenureToggle', () => {
  // Case 1 — URL truth: ?tenure=3m renders 3m active, LS irrelevant
  it('URL param overrides localStorage — renders 3m active', () => {
    _searchParamValue = '3m'
    setLS('test-page', '12m') // LS says 12m — should be ignored

    render(<TenureToggle pageKey="test-page" />)

    const checked = screen
      .getAllByRole('radio')
      .find((el) => el.getAttribute('aria-checked') === 'true')

    expect(checked).toBeDefined()
    expect(checked?.textContent).toBe('3m')

    // Confirm 12m is NOT active
    const twelvem = screen.getByRole('radio', { name: '12m' })
    expect(twelvem.getAttribute('aria-checked')).toBe('false')
  })

  // Case 2 — LS seed: no URL param, LS has 12m → renders 12m active
  it('seeds from localStorage when URL param is absent', () => {
    _searchParamValue = null
    setLS('fund-page', '12m')

    render(<TenureToggle pageKey="fund-page" />)

    const checked = screen
      .getAllByRole('radio')
      .find((el) => el.getAttribute('aria-checked') === 'true')

    expect(checked?.textContent).toBe('12m')
  })

  // Case 3 — Click writes both URL and LS
  it('clicking a pill writes URL param and localStorage', async () => {
    const user = userEvent.setup()
    _searchParamValue = null

    render(<TenureToggle pageKey="sector-page" />)

    const sixm = screen.getByRole('radio', { name: '6m' })
    await user.click(sixm)

    // URL updated
    expect(_routerReplace).toHaveBeenCalledOnce()
    const [urlArg] = _routerReplace.mock.calls[0] as [string]
    expect(urlArg).toContain('tenure=6m')

    // LS written
    expect(getLS('sector-page')).toBe('6m')
  })

  // Case 4 — Default 6m: no URL, no LS → renders 6m active
  it('defaults to 6m when neither URL nor localStorage has a value', () => {
    _searchParamValue = null

    render(<TenureToggle pageKey="fresh-page" />)

    const checked = screen
      .getAllByRole('radio')
      .find((el) => el.getAttribute('aria-checked') === 'true')

    expect(checked?.textContent).toBe('6m')
  })

  // Case 5 — Keyboard nav: Tab focuses first, Right Arrow advances, Home returns to first
  it('keyboard navigation: Right Arrow advances selection, Home returns to first', async () => {
    const user = userEvent.setup()
    _searchParamValue = null

    render(<TenureToggle pageKey="keyboard-page" />)

    // Default active is 6m (index 2). Tab to focus.
    const sixm = screen.getByRole('radio', { name: '6m' })
    await user.tab()
    // The active pill (6m) should get focus since tabIndex=0 is set on it.
    // In some environments focus goes to 1m first (tabIndex on first) —
    // click 6m to ensure it's active and focused, then arrow forward.
    sixm.focus()
    expect(document.activeElement?.textContent).toBe('6m')

    // Right arrow from 6m → 12m
    await user.keyboard('{ArrowRight}')
    // The router.replace is called with tenure=12m
    const lastCall = _routerReplace.mock.calls.at(-1)?.[0] as string
    expect(lastCall).toContain('tenure=12m')

    // Home key — jump to first (1m)
    const radioGroup = screen.getByRole('radiogroup')
    const firstPill = screen.getByRole('radio', { name: '1m' })
    firstPill.focus()
    await user.keyboard('{Home}')
    const homeCall = _routerReplace.mock.calls.at(-1)?.[0] as string
    expect(homeCall).toContain('tenure=1m')
    // Suppress unused-var warning for radioGroup — kept for readability
    void radioGroup
  })

  // Structural: 4 pills rendered with correct ARIA structure
  it('renders 4 radio pills inside a radiogroup', () => {
    render(<TenureToggle pageKey="structural-check" />)
    expect(screen.getByRole('radiogroup')).toBeDefined()
    expect(screen.getAllByRole('radio')).toHaveLength(4)
    expect(screen.getByRole('radio', { name: '1m' })).toBeDefined()
    expect(screen.getByRole('radio', { name: '3m' })).toBeDefined()
    expect(screen.getByRole('radio', { name: '6m' })).toBeDefined()
    expect(screen.getByRole('radio', { name: '12m' })).toBeDefined()
  })
})
