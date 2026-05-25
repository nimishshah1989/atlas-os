// frontend/src/components/v6/__tests__/StocksListV6.test.tsx
//
// 5 test cases:
//   1. Default columns visible; ColumnChooser toggles optional columns
//   2. cap_tier filter: only Mid rows visible when filter_tier=Mid
//   3. in_my_book toggle: rows filtered to held iids only
//   4. PortfolioBadge visible for held iids; absent for unheld
//   5. No-match filter → empty state copy

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { StocksListV6 } from '../StocksListV6'
import type { StockV6Row } from '@/lib/queries/v6/stocks'

// ── Mocks ────────────────────────────────────────────────────────────────────

// next/navigation mock
vi.mock('next/navigation', () => ({
  useRouter:      () => ({ replace: vi.fn() }),
  usePathname:    () => '/v6/stocks',
  useSearchParams: () => new URLSearchParams(),
}))

// ConvictionTape — lightweight stub
vi.mock('@/components/v6/ConvictionTape', () => ({
  ConvictionTape: ({ tape }: { tape: unknown }) => (
    <div data-testid="conviction-tape">{JSON.stringify(tape)}</div>
  ),
}))

// ColumnChooser — lightweight stub that exposes checkbox for each column def
vi.mock('@/components/v6/ColumnChooser', () => ({
  ColumnChooser: ({
    columns,
    visible,
    onVisibleChange,
    open,
    onOpenChange,
  }: {
    columns: Array<{ key: string; label: string }>
    visible: string[]
    onVisibleChange: (cols: string[]) => void
    onReset: () => void
    open: boolean
    onOpenChange: (o: boolean) => void
  }) => (
    <div>
      <button onClick={() => onOpenChange(!open)} data-testid="chooser-trigger">
        Columns
      </button>
      {open && (
        <div data-testid="chooser-modal">
          {columns.map(c => (
            <label key={c.key}>
              <input
                type="checkbox"
                data-testid={`col-toggle-${c.key}`}
                checked={visible.includes(c.key)}
                onChange={() => {
                  const next = visible.includes(c.key)
                    ? visible.filter(k => k !== c.key)
                    : [...visible, c.key]
                  onVisibleChange(next)
                }}
              />
              {c.label}
            </label>
          ))}
        </div>
      )}
    </div>
  ),
}))

// useColumnPreferences — real implementation hits localStorage; mock for isolation
// We cannot use generics inside vi.mock factory, so we use a wrapper module approach.
import { useState as _useState } from 'react'

vi.mock('@/lib/v6/useColumnPreferences', () => ({
  useColumnPreferences: (
    _pageKey: string,
    defaults: string[],
  ) => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const [visible, setVisible] = _useState<string[]>(defaults)
    return {
      visible,
      setVisible,
      reset: () => setVisible(defaults),
    }
  },
}))

// ── Fixtures ─────────────────────────────────────────────────────────────────

function makeTape(direction: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' = 'POSITIVE') {
  const v = { direction, ic: direction === 'POSITIVE' ? 0.05 : null, rule_count: 1, top_rule_id: null }
  return { '1m': v, '3m': v, '6m': v, '12m': v }
}

function makeStock(
  overrides: Partial<StockV6Row> & { iid: string; symbol: string },
): StockV6Row {
  return {
    iid: overrides.iid,
    symbol: overrides.symbol,
    company_name: overrides.company_name ?? `${overrides.symbol} Ltd`,
    sector: overrides.sector ?? 'Financials',
    tier: overrides.tier ?? 'Large',
    mcap_inr: null,
    rs_state: overrides.rs_state ?? 'Leader',
    stage: null,
    conviction_tape: overrides.conviction_tape ?? makeTape('POSITIVE'),
    ret_1d: overrides.ret_1d ?? 0.01,
    ret_1w: overrides.ret_1w ?? 0.02,
    ret_1m: overrides.ret_1m ?? 0.05,
    ret_3m: overrides.ret_3m ?? 0.12,
    ret_6m: overrides.ret_6m ?? 0.18,
    ret_12m: overrides.ret_12m ?? 0.25,
    rs_pctile_3m: overrides.rs_pctile_3m ?? 0.80,
    is_investable: overrides.is_investable ?? true,
  }
}

const STOCK_LARGE = makeStock({ iid: 'iid-1', symbol: 'RELIANCE', tier: 'Large', sector: 'Energy' })
const STOCK_MID_1 = makeStock({ iid: 'iid-2', symbol: 'MIDCAP1',  tier: 'Mid',   sector: 'IT' })
const STOCK_MID_2 = makeStock({ iid: 'iid-3', symbol: 'MIDCAP2',  tier: 'Mid',   sector: 'IT',
  conviction_tape: makeTape('NEGATIVE') })
const STOCK_SMALL = makeStock({ iid: 'iid-4', symbol: 'SMALLCO',  tier: 'Small', sector: 'FMCG' })

const ALL_STOCKS = [STOCK_LARGE, STOCK_MID_1, STOCK_MID_2, STOCK_SMALL]

// ── Test setup ────────────────────────────────────────────────────────────────

let lsStore: Record<string, string> = {}

beforeEach(() => {
  lsStore = {}
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(
    (key: string) => lsStore[key] ?? null,
  )
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(
    (key: string, val: string) => { lsStore[key] = val },
  )
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(
    (key: string) => { delete lsStore[key] },
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

function renderList(
  stocks = ALL_STOCKS,
  heldIids: string[] = [],
) {
  return render(
    <StocksListV6
      stocks={stocks}
      heldIids={heldIids}
      snapshotDate="2026-05-26"
    />,
  )
}

// ── Test 1: Default columns visible; ColumnChooser toggles optional columns ──

describe('StocksListV6 — column visibility', () => {
  it('renders default columns and allows toggling optional via ColumnChooser', () => {
    renderList()

    // Default header visible: ticker col header
    expect(screen.getByText('Ticker')).toBeInTheDocument()
    // Composite column header
    expect(screen.getByText('Composite')).toBeInTheDocument()

    // Volatility (optional) is NOT visible by default — header absent
    expect(screen.queryByText('Vol')).not.toBeInTheDocument()

    // Open ColumnChooser
    fireEvent.click(screen.getByTestId('chooser-trigger'))
    expect(screen.getByTestId('chooser-modal')).toBeInTheDocument()

    // Toggle volatility on
    const volToggle = screen.getByTestId('col-toggle-volatility')
    expect(volToggle).not.toBeChecked()
    fireEvent.click(volToggle)

    // Volatility header should now be visible
    expect(screen.getByText('Vol')).toBeInTheDocument()
  })
})

// ── Test 2: cap_tier filter ───────────────────────────────────────────────────

describe('StocksListV6 — tier filter', () => {
  it('shows only Mid rows when tier filter set to Mid', () => {
    renderList()

    const tierSelect = screen.getByTestId('tier-filter')
    fireEvent.change(tierSelect, { target: { value: 'Mid' } })

    // Rows with data-tier="Mid" present
    const rows = screen.getAllByTestId('stocks-row')
    const tiers = rows.map(r => r.getAttribute('data-tier'))
    expect(tiers.every(t => t === 'Mid')).toBe(true)
    expect(rows).toHaveLength(2)

    // RELIANCE (Large) row absent
    expect(screen.queryByText('RELIANCE')).not.toBeInTheDocument()
  })
})

// ── Test 3: in_my_book toggle ─────────────────────────────────────────────────

describe('StocksListV6 — in_my_book toggle', () => {
  it('filters rows to only held iids when in_my_book is active', () => {
    // Only iid-2 (MIDCAP1) is held
    renderList(ALL_STOCKS, ['iid-2'])

    // Initially all 4 rows visible
    expect(screen.getAllByTestId('stocks-row')).toHaveLength(4)

    // Toggle in-my-book
    fireEvent.click(screen.getByTestId('in-my-book-toggle'))

    // Now only MIDCAP1 row visible
    const rows = screen.getAllByTestId('stocks-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('MIDCAP1')).toBeInTheDocument()
  })
})

// ── Test 4: PortfolioBadge present for held iids, absent for unheld ───────────

describe('StocksListV6 — PortfolioBadge column', () => {
  it('renders PortfolioBadge only for held iids', () => {
    // iid-1 (RELIANCE) is held; others are not
    renderList(ALL_STOCKS, ['iid-1'])

    const rows = screen.getAllByTestId('stocks-row')
    // RELIANCE row: find badge via aria-label on the "Held" cell
    const relianceRow = rows.find(r =>
      within(r).queryByText('RELIANCE') !== null,
    )
    expect(relianceRow).toBeDefined()

    // PortfolioBadge renders with aria-label="Held in 1 portfolio, aggregate ..."
    // The badge container has role="status"
    const badge = within(relianceRow!).queryByRole('status')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toContain('Held')

    // Non-held row (MIDCAP1) should have no badge
    const midRow = rows.find(r =>
      within(r).queryByText('MIDCAP1') !== null,
    )
    expect(midRow).toBeDefined()
    expect(within(midRow!).queryByRole('status')).toBeNull()
  })
})

// ── Test 5: Empty filter → empty state ───────────────────────────────────────

describe('StocksListV6 — empty state', () => {
  it('shows empty state message when no stocks match the filters', () => {
    renderList()

    // Select FMCG sector first to reduce rows, then select an action that matches none
    const tierSelect = screen.getByTestId('tier-filter')
    fireEvent.change(tierSelect, { target: { value: 'Mid' } })

    // Now filter by AVOID (NEGATIVE dominant) — MIDCAP2 has NEGATIVE tape, MIDCAP1 has POSITIVE
    // But then also filter "in my book" with no held iids — 0 results
    fireEvent.click(screen.getByTestId('in-my-book-toggle'))

    // No stocks held → empty state
    expect(screen.getByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('No stocks match the current filters.')).toBeInTheDocument()
    expect(screen.getByText('Clear filters')).toBeInTheDocument()
  })
})
