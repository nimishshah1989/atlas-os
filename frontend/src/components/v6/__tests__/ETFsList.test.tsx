// frontend/src/components/v6/__tests__/ETFsList.test.tsx
//
// D.7 — 5 test cases:
//   1. Renders rows from query
//   2. PortfolioBadge column visible by default
//   3. ColumnChooser toggle hides a column
//   4. Empty state: "No ETFs available"
//   5. Sort by composite_score DESC by default (first row has highest score)

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ETFsList } from '../ETFsList'
import type { EtfV6Row } from '@/lib/queries/v6/etfs'
import type { IndustrySnapshot as IndustrySnapshotData } from '@/lib/queries/v6/industry_snapshot'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ── Module mocks ─────────────────────────────────────────────────────────────

// Mock server-only child modules used by ETFsList imports
vi.mock('@/lib/v6/useColumnPreferences', () => ({
  useColumnPreferences: vi.fn((pageKey: string, defaults: string[]) => ({
    visible: [...defaults],
    setVisible: vi.fn(),
    reset: vi.fn(),
  })),
}))

vi.mock('../IndustrySnapshot', () => ({
  IndustrySnapshot: ({ snapshot }: { snapshot: IndustrySnapshotData }) => (
    <div data-testid="industry-snapshot">
      {snapshot.asset_class === 'etfs' ? 'ETFs Industry' : 'Funds Industry'}
    </div>
  ),
}))

vi.mock('../BubbleRiskReturnChart', () => ({
  BubbleRiskReturnChart: ({ data }: { data: unknown[] }) => (
    <div data-testid="bubble-chart">{data.length} bubbles</div>
  ),
}))

vi.mock('../SignatureMatrix', () => ({
  SignatureMatrix: ({ asset_label }: { asset_label: string }) => (
    <div data-testid="signature-matrix">{asset_label}</div>
  ),
}))

vi.mock('../PortfolioBadge', () => ({
  PortfolioBadge: ({ state }: { state: HoldingState | null }) =>
    state ? (
      <span data-testid="portfolio-badge">
        Held · {state.portfolio_count} portfolio
      </span>
    ) : null,
}))

vi.mock('../ColumnChooser', () => ({
  ColumnChooser: ({
    open,
    onOpenChange,
    columns,
    visible,
    onVisibleChange,
  }: {
    open: boolean
    onOpenChange: (v: boolean) => void
    columns: { key: string; label: string }[]
    visible: string[]
    onVisibleChange: (v: string[]) => void
  }) => (
    <div data-testid="column-chooser">
      <button
        onClick={() => onOpenChange(!open)}
        aria-label="open column chooser"
      >
        Columns
      </button>
      {open &&
        columns.map(col => (
          <label key={col.key}>
            <input
              type="checkbox"
              checked={visible.includes(col.key)}
              onChange={e => {
                const next = e.target.checked
                  ? [...visible, col.key]
                  : visible.filter(k => k !== col.key)
                onVisibleChange(next as string[])
              }}
            />
            {col.label}
          </label>
        ))}
    </div>
  ),
}))

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeEtf(overrides: Partial<EtfV6Row> = {}): EtfV6Row {
  const NEUTRAL_TAPE = {
    '1m':  { direction: 'NEUTRAL' as const, ic: null, rule_count: 0, top_rule_id: null },
    '3m':  { direction: 'NEUTRAL' as const, ic: null, rule_count: 0, top_rule_id: null },
    '6m':  { direction: 'NEUTRAL' as const, ic: null, rule_count: 0, top_rule_id: null },
    '12m': { direction: 'NEUTRAL' as const, ic: null, rule_count: 0, top_rule_id: null },
  }
  return {
    iid: 'etf-001',
    ticker: 'NIFTYBEES',
    name: 'Nippon India ETF Nifty BeES',
    category: 'broad_index',
    aum_cr: '12500',
    expense_ratio: '0.04',
    tracking_error: '0.12',
    is_atlas_leader: false,
    composite_score: '72.50',
    conviction_tape: NEUTRAL_TAPE,
    ret_1m: 0.015,
    ret_3m: 0.041,
    ret_6m: 0.082,
    ret_12m: 0.143,
    rs_state: 'Strong',
    ...overrides,
  }
}

function makeSnapshot(): IndustrySnapshotData {
  return {
    asset_class: 'etfs',
    n_total: 3,
    n_atlas_leaders: 1,
    n_avoid: 0,
    pct_above_benchmark_3y: null,
    median_expense: '0.05',
    median_aum_cr: '8000',
    amc_leaderboard: [
      { amc: 'Nippon India', avg_composite: '72.50', n_funds: 1 },
      { amc: 'HDFC AMC',     avg_composite: '65.10', n_funds: 1 },
    ],
  }
}

function makeEtfList(): EtfV6Row[] {
  // Pre-sorted by composite_score DESC (as the query returns)
  return [
    makeEtf({ iid: 'etf-001', ticker: 'NIFTYBEES', composite_score: '80.00', is_atlas_leader: true }),
    makeEtf({ iid: 'etf-002', ticker: 'BANKBEES',  composite_score: '65.50', name: 'Nippon India ETF Bank BeES' }),
    makeEtf({ iid: 'etf-003', ticker: 'GOLDBEES',  composite_score: '52.00', category: 'commodity' }),
  ]
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ETFsList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // 1. Renders rows from query
  it('renders a table row for each ETF in the data', () => {
    render(
      <ETFsList
        etfs={makeEtfList()}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    const rows = screen.getAllByTestId('etf-row')
    expect(rows).toHaveLength(3)

    // All tickers rendered (getBy would fail on multiple; use getAllBy)
    expect(screen.getAllByText('NIFTYBEES').length).toBeGreaterThan(0)
    expect(screen.getByText('BANKBEES')).toBeInTheDocument()
    expect(screen.getByText('GOLDBEES')).toBeInTheDocument()
  })

  // 2. PortfolioBadge column visible by default
  it('renders portfolio-badge cells for every row by default', () => {
    const holdingState: HoldingState = {
      portfolio_count: 2,
      weight_range: ['0.00', '0.00'],
      aggregate_weight: '0.00',
      last_add_date: null,
    }
    // Only etf-001 is held
    render(
      <ETFsList
        etfs={makeEtfList()}
        snapshot={makeSnapshot()}
        holdingMap={{ 'etf-001': holdingState }}
        snapshotDate="2026-05-26"
      />,
    )

    // own_badge column is rendered — badge cells are present
    const badgeCells = screen.getAllByTestId('portfolio-badge-cell')
    expect(badgeCells.length).toBe(3)

    // The held ETF shows its badge; unheld ones are null (silent absence)
    expect(screen.getByTestId('portfolio-badge')).toBeInTheDocument()
    expect(screen.getByText(/Held · 2/)).toBeInTheDocument()
  })

  // 3. ColumnChooser toggle
  it('column chooser button is rendered; toggling open shows column checkboxes', async () => {
    const { useColumnPreferences } = await import('@/lib/v6/useColumnPreferences')
    const mockSetVisible = vi.fn()
    vi.mocked(useColumnPreferences).mockReturnValue({
      visible: ['ticker', 'name', 'category', 'aum', 'expense_ratio',
        'tracking_error', 'grade', 'ret_1w', 'ret_6m', 'composite',
        'holdings', 'own_badge'],
      setVisible: mockSetVisible,
      reset: vi.fn(),
    })

    render(
      <ETFsList
        etfs={makeEtfList()}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    const trigger = screen.getByRole('button', { name: /open column chooser/i })
    expect(trigger).toBeInTheDocument()

    // Click to open
    fireEvent.click(trigger)

    await waitFor(() => {
      // Expense ratio checkbox should appear (in chooser)
      expect(screen.getByLabelText(/expense ratio/i)).toBeInTheDocument()
    })
  })

  // 4. Empty state
  it('renders "No ETFs available" when etfs array is empty', () => {
    render(
      <ETFsList
        etfs={[]}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    expect(screen.getByTestId('etfs-empty-state')).toBeInTheDocument()
    expect(screen.getByText('No ETFs available')).toBeInTheDocument()

    // No table rows
    expect(screen.queryByTestId('etf-row')).toBeNull()
  })

  // 5. Sort by composite_score DESC by default
  it('renders rows in composite_score DESC order (first row has highest score)', () => {
    // Data arrives pre-sorted from query (composite_score DESC)
    const etfs = makeEtfList() // [80.00, 65.50, 52.00]

    render(
      <ETFsList
        etfs={etfs}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    const rows = screen.getAllByTestId('etf-row')
    expect(rows).toHaveLength(3)

    // First row is NIFTYBEES (highest score 80.00)
    const firstRowText = rows[0].textContent ?? ''
    expect(firstRowText).toContain('NIFTYBEES')

    // Last row is GOLDBEES (lowest score 52.00)
    const lastRowText = rows[2].textContent ?? ''
    expect(lastRowText).toContain('GOLDBEES')
  })
})
