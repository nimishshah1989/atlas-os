// frontend/src/components/v6/__tests__/SectorDetailClient.test.tsx
//
// D.4 tests — 5 required cases:
//   1. Hero renders with sector name + rank
//   2. Hero strip shows book vs benchmark with chip
//   3. Constituent table renders PortfolioBadge for held iids
//   4. Empty constituents: fallback message
//   5. ARIA labels present

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SectorDetailClient } from '../SectorDetailClient'
import type { SectorDetailClientProps } from '../SectorDetailClient'
import type { ScreenSector } from '@/lib/api/v1'
import type { StockV6Row } from '@/lib/queries/v6/stocks'
import type { SectorBookExposure } from '@/lib/queries/v6/sector_book_exposure'
import type { SectorBreadth } from '@/lib/queries/v6/sector_breadth'

// ---------------------------------------------------------------------------
// Mocks — isolate from Radix, Recharts, heavy sub-components
// ---------------------------------------------------------------------------

vi.mock('../SectorBookStrip', () => ({
  SectorBookStrip: ({ exposures }: { exposures: unknown[] }) => (
    <div data-testid="sector-book-strip" data-count={exposures.length} />
  ),
}))

vi.mock('../SectorBreadthPanel', () => ({
  SectorBreadthPanel: ({ breadth }: { breadth: { sector: string } }) => (
    <div data-testid="sector-breadth-panel" data-sector={breadth.sector} />
  ),
}))

vi.mock('../BubbleRiskReturnChart', () => ({
  BubbleRiskReturnChart: ({ data }: { data: unknown[] }) => (
    <div data-testid="bubble-chart" data-count={data.length} />
  ),
}))

vi.mock('../PortfolioBadge', () => ({
  PortfolioBadge: ({
    state,
    variant,
  }: {
    state: unknown
    variant?: string
  }) => {
    if (!state) return null
    return (
      <span data-testid="portfolio-badge" data-variant={variant}>
        Held
      </span>
    )
  },
}))

vi.mock('../ConvictionTape', () => ({
  ConvictionTape: () => <div data-testid="conviction-tape" />,
}))

vi.mock('../ColumnChooser', () => ({
  ColumnChooser: () => <button data-testid="column-chooser">Columns</button>,
}))

vi.mock('@/components/ui/StateBadge', () => ({
  StateBadge: ({ state }: { state: string }) => (
    <span data-testid="state-badge">{state}</span>
  ),
}))

vi.mock('@/components/ui/LinkedToken', () => ({
  LinkedTicker: ({ symbol }: { symbol: string }) => (
    <span data-testid="linked-ticker">{symbol}</span>
  ),
  LinkedSector: ({ sector }: { sector: string }) => (
    <span>{sector}</span>
  ),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const NEUTRAL_VERDICT = {
  direction: 'NEUTRAL' as const,
  ic: null,
  rule_count: 0,
  top_rule_id: null,
}
const NEUTRAL_TAPE = {
  '1m': NEUTRAL_VERDICT,
  '3m': NEUTRAL_VERDICT,
  '6m': NEUTRAL_VERDICT,
  '12m': NEUTRAL_VERDICT,
}

const MOCK_SECTOR: ScreenSector = {
  sector_iid: 'Banking',
  sector_name: 'Banking',
  rank: 3,
  rank_change: 0,
  days_in_state: 0,
  sector_state: 'Overweight',
  breadth_pct_stage_2: 0.65,
  vol_regime: 'Normal',
  rs_pct_cross_sector: 0.72,
  ret_1m: 0.04,
  ret_3m: 0.09,
  rrg_quadrant: null,
  cells_favored_today: [],
}

function makeStock(iid: string, symbol: string): StockV6Row {
  return {
    iid,
    symbol,
    company_name: `${symbol} Ltd`,
    sector: 'Banking',
    tier: 'Large',
    mcap_inr: null,
    rs_state: 'Stage2',
    stage: 'Stage 2',
    conviction_tape: NEUTRAL_TAPE,
    ret_1d: null,
    ret_1w: null,
    ret_1m: 0.03,
    ret_3m: 0.07,
    ret_6m: 0.12,
    ret_12m: 0.20,
    rs_pctile_3m: 0.65,
    is_investable: true,
  }
}

const STOCK_A = makeStock('iid-aaa-001', 'HDFCBANK')
const STOCK_B = makeStock('iid-bbb-002', 'ICICIBANK')

const MOCK_EXPOSURE: SectorBookExposure = {
  sector_name: 'Banking',
  book_weight:      '8.50',
  benchmark_weight: '10.00',
  delta_pp:         '-1.50',
  holding_count: 3,
}

const MOCK_EXPOSURE_OVER: SectorBookExposure = {
  sector_name: 'Banking',
  book_weight:      '12.50',
  benchmark_weight: '10.00',
  delta_pp:         '2.50',
  holding_count: 4,
}

const MOCK_BREADTH: SectorBreadth = {
  sector: 'Banking',
  n_stocks: 38,
  pct_above_sma20: '74.00',
  pct_above_sma50: '66.00',
  pct_above_sma200: '58.00',
  top3_concentration_pct: '35.00',
  dispersion_sigma: '18.00',
  as_of_date: '2026-05-26',
}

const BASE_PROPS: SectorDetailClientProps = {
  sector: MOCK_SECTOR,
  sectorName: 'Banking',
  stocks: [STOCK_A, STOCK_B],
  exposure: MOCK_EXPOSURE,
  breadth: MOCK_BREADTH,
  heldIidSet: new Set<string>(),
  snapshotDate: '2026-05-26',
}

// ---------------------------------------------------------------------------
// Case 1: Hero renders with sector name + rank
// ---------------------------------------------------------------------------

describe('SectorDetailClient — case 1: hero renders sector name + rank', () => {
  it('renders the sector name as h1', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.textContent).toBe('Banking')
  })

  it('renders rank label', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    expect(screen.getByText(/Rank 3/)).toBeInTheDocument()
  })

  it('renders StateBadge with sector_state', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    expect(screen.getByTestId('state-badge')).toBeInTheDocument()
    expect(screen.getByTestId('state-badge').textContent).toBe('Overweight')
  })

  it('renders action verb OVERWEIGHT for Overweight state', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    expect(screen.getByText('OVERWEIGHT')).toBeInTheDocument()
  })

  it('renders thesis bullets', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    // Should contain at least one thesis bullet (returns / RS / breadth)
    expect(screen.getByRole('list', { name: /Sector thesis/i })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Case 2: Hero strip shows book vs benchmark with chip
// ---------------------------------------------------------------------------

describe('SectorDetailClient — case 2: hero book band with chip', () => {
  it('renders hero-book-band element', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    expect(screen.getByTestId('hero-book-band')).toBeInTheDocument()
  })

  it('displays book weight percentage', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    // book_weight = "8.50" → displays 8.5%
    expect(screen.getByTestId('hero-book-band').textContent).toContain('8.5%')
  })

  it('displays benchmark weight percentage', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    // benchmark_weight = "10.00" → displays 10.0%
    expect(screen.getByTestId('hero-book-band').textContent).toContain('10.0%')
  })

  it('renders UNDERWEIGHT chip when delta negative', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    // delta_pp = "-1.50" → UNDERWEIGHT
    expect(screen.getByTestId('book-weight-chip').textContent).toBe('UNDERWEIGHT')
  })

  it('renders OVERWEIGHT chip when delta positive', () => {
    render(
      <SectorDetailClient
        {...BASE_PROPS}
        exposure={MOCK_EXPOSURE_OVER}
      />
    )
    // delta_pp = "2.50" → OVERWEIGHT
    expect(screen.getByTestId('book-weight-chip').textContent).toBe('OVERWEIGHT')
  })

  it('hero-book-band is silent when exposure is null', () => {
    const { container } = render(
      <SectorDetailClient {...BASE_PROPS} exposure={null} />
    )
    expect(container.querySelector('[data-testid="hero-book-band"]')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Case 3: Constituent table renders PortfolioBadge for held iids
// ---------------------------------------------------------------------------

describe('SectorDetailClient — case 3: PortfolioBadge for held iids', () => {
  it('renders PortfolioBadge for held iid', () => {
    const heldSet = new Set(['iid-aaa-001'])
    render(<SectorDetailClient {...BASE_PROPS} heldIidSet={heldSet} />)
    const badges = screen.getAllByTestId('portfolio-badge')
    // STOCK_A is held → 1 badge
    expect(badges).toHaveLength(1)
    expect(badges[0].getAttribute('data-variant')).toBe('compact')
  })

  it('does NOT render PortfolioBadge for unheld iids', () => {
    const heldSet = new Set<string>()   // nothing held
    render(<SectorDetailClient {...BASE_PROPS} heldIidSet={heldSet} />)
    const badges = screen.queryAllByTestId('portfolio-badge')
    expect(badges).toHaveLength(0)
  })

  it('renders PortfolioBadge for multiple held iids', () => {
    const heldSet = new Set(['iid-aaa-001', 'iid-bbb-002'])
    render(<SectorDetailClient {...BASE_PROPS} heldIidSet={heldSet} />)
    const badges = screen.getAllByTestId('portfolio-badge')
    expect(badges).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// Case 4: Empty constituents shows fallback message
// ---------------------------------------------------------------------------

describe('SectorDetailClient — case 4: empty constituents fallback', () => {
  it('shows "No constituents found" when stocks is empty', () => {
    render(<SectorDetailClient {...BASE_PROPS} stocks={[]} />)
    expect(screen.getByTestId('empty-constituents')).toBeInTheDocument()
    expect(screen.getByTestId('empty-constituents').textContent).toContain(
      'No constituents found',
    )
  })

  it('does NOT render constituent table when stocks empty', () => {
    render(<SectorDetailClient {...BASE_PROPS} stocks={[]} />)
    // No linked-ticker elements when empty
    expect(screen.queryAllByTestId('linked-ticker')).toHaveLength(0)
  })

  it('SectorBookStrip is silent when exposure is null + stocks empty', () => {
    const { container } = render(
      <SectorDetailClient {...BASE_PROPS} stocks={[]} exposure={null} />
    )
    expect(container.querySelector('[data-testid="sector-book-strip"]')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Case 5: ARIA labels present
// ---------------------------------------------------------------------------

describe('SectorDetailClient — case 5: ARIA labels', () => {
  it('hero header has aria-label with sector name', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    const header = screen.getByRole('banner', { name: /Sector detail hero for Banking/ })
    expect(header).toBeInTheDocument()
  })

  it('hero-book-band has aria-label with book/benchmark figures', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    const band = screen.getByTestId('hero-book-band')
    const label = band.getAttribute('aria-label') ?? ''
    expect(label).toContain('Your book in this sector')
    expect(label).toContain('8.5%')
    expect(label).toContain('10.0%')
  })

  it('chip has aria-label indicating position class', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    const chip = screen.getByTestId('book-weight-chip')
    expect(chip.getAttribute('aria-label')).toContain('UNDERWEIGHT')
  })

  it('table has aria-label "Sector constituents"', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    expect(
      screen.getByRole('table', { name: /Sector constituents/ }),
    ).toBeInTheDocument()
  })

  it('constituent row cells have aria-label', () => {
    render(<SectorDetailClient {...BASE_PROPS} />)
    // At least one symbol cell aria-label present
    const symbolCells = screen.getAllByLabelText(/Symbol: HDFCBANK|Symbol: ICICIBANK/)
    expect(symbolCells.length).toBeGreaterThan(0)
  })
})
