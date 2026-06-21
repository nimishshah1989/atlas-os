// frontend/src/components/v6/__tests__/FundsList.test.tsx
//
// D.5 — 5 test cases:
//   1. Renders rows from query (fund-row for each fund)
//   2. PortfolioBadge column visible by default
//   3. Empty state: "No funds available"
//   4. Smoke: IndustrySnapshot + BubbleChart + SignatureMatrix all rendered
//   5. portfolio-badge renders for held fund (FM-critic §1.6 gap #1)

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundsList } from '../FundsList'
import type { FundRow } from '../FundsList'
import type { IndustrySnapshot as IndustrySnapshotData } from '@/lib/queries/v6/industry_snapshot'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('@/lib/v6/useColumnPreferences', () => ({
  useColumnPreferences: vi.fn((_pageKey: string, defaults: string[]) => ({
    visible: [...defaults],
    setVisible: vi.fn(),
    reset: vi.fn(),
  })),
}))

vi.mock('../IndustrySnapshot', () => ({
  IndustrySnapshot: ({ snapshot }: { snapshot: IndustrySnapshotData }) => (
    <div data-testid="industry-snapshot">
      {snapshot.asset_class === 'funds' ? 'Funds Industry' : 'ETFs Industry'}
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
  ColumnChooser: () => <div data-testid="column-chooser" />,
}))

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeFund(overrides: Partial<FundRow> = {}): FundRow {
  return {
    iid: 'fund-001',
    code: 'SC001',
    name: 'HDFC Top 100 Fund',
    category: 'India Fund Large-Cap',
    aum_cr: '28000',
    expense_ratio: '1.25',
    composite_score: '72.50',
    rank_in_category: 2,
    category_size: 30,
    is_atlas_leader: false,
    is_avoid: false,
    ret_1m: 0.022,
    ret_3m: 0.047,
    ret_6m: 0.089,
    ret_12m: 0.163,
    rs_pctile_3m: '0.72',
    sector_tilt: null,
    realized_vol_63: '0.18',
    ...overrides,
  }
}

function makeSnapshot(): IndustrySnapshotData {
  return {
    asset_class: 'funds',
    n_total: 3,
    n_atlas_leaders: 1,
    n_avoid: 0,
    pct_above_benchmark_3y: null,
    median_expense: '1.50',
    median_aum_cr: '12000',
    amc_leaderboard: [
      { amc: 'HDFC AMC', avg_composite: '72.50', n_funds: 2 },
      { amc: 'Axis AMC', avg_composite: '68.10', n_funds: 1 },
    ],
  }
}

function makeFundList(): FundRow[] {
  return [
    makeFund({
      iid: 'fund-001',
      name: 'HDFC Top 100 Fund',
      composite_score: '80.00',
      is_atlas_leader: true,
    }),
    makeFund({
      iid: 'fund-002',
      code: 'SC002',
      name: 'Axis Bluechip Fund',
      composite_score: '65.50',
    }),
    makeFund({
      iid: 'fund-003',
      code: 'SC003',
      name: 'SBI Small Cap Fund',
      category: 'India Fund Small-Cap',
      composite_score: '52.00',
      rs_pctile_3m: '0.35',
    }),
  ]
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('FundsList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // 1. Renders rows for each fund
  it('renders a table row for each fund in the data', () => {
    render(
      <FundsList
        funds={makeFundList()}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    const rows = screen.getAllByTestId('fund-row')
    expect(rows).toHaveLength(3)

    // Name may appear in SignatureMatrix title too — use getAllByText
    expect(screen.getAllByText('HDFC Top 100 Fund').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Axis Bluechip Fund').length).toBeGreaterThan(0)
    expect(screen.getAllByText('SBI Small Cap Fund').length).toBeGreaterThan(0)
  })

  // 2. PortfolioBadge column visible by default for held fund
  it('portfolio-badge renders for held fund (PortfolioBadge wiring)', () => {
    const holdingState: HoldingState = {
      portfolio_count: 2,
      weight_range: ['0.00', '0.00'],
      aggregate_weight: '0.00',
      last_add_date: null,
    }
    render(
      <FundsList
        funds={makeFundList()}
        snapshot={makeSnapshot()}
        holdingMap={{ 'fund-001': holdingState }}
        snapshotDate="2026-05-26"
      />,
    )

    // Only fund-001 is held — one badge rendered, others silent
    const badges = screen.getAllByTestId('portfolio-badge')
    expect(badges).toHaveLength(1)
    expect(badges[0].textContent).toContain('Held · 2 portfolio')
  })

  // 3. Empty state: "No funds available"
  it('renders empty state when no funds provided', () => {
    render(
      <FundsList
        funds={[]}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    expect(screen.getByTestId('funds-empty-state')).toBeDefined()
    expect(screen.getByText('No funds available')).toBeDefined()
    expect(screen.queryByTestId('funds-table')).toBeNull()
  })

  // 4. Smoke: IndustrySnapshot + BubbleChart + SignatureMatrix all rendered
  it('renders all 3 chart sections when funds are provided', () => {
    render(
      <FundsList
        funds={makeFundList()}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    expect(screen.getByTestId('industry-snapshot')).toBeDefined()
    expect(screen.getByTestId('bubble-chart')).toBeDefined()
    expect(screen.getByTestId('signature-matrix')).toBeDefined()
    // 3 funds → 3 bubbles in chart
    expect(screen.getByText('3 bubbles')).toBeDefined()
  })

  // 5. Atlas leader fund gets AAA grade
  it('derives AAA grade for atlas_leader fund', () => {
    render(
      <FundsList
        funds={[makeFund({ is_atlas_leader: true, composite_score: '80.00' })]}
        snapshot={makeSnapshot()}
        holdingMap={{}}
        snapshotDate="2026-05-26"
      />,
    )

    // Grade column should show AAA (is_atlas_leader takes priority)
    const rows = screen.getAllByTestId('fund-row')
    expect(rows[0].textContent).toContain('AAA')
  })
})
