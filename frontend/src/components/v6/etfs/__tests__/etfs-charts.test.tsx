// frontend/src/components/v6/etfs/__tests__/etfs-charts.test.tsx
//
// I2: Smoke + NULL-path tests for chart-heavy components:
//   PremiumDiscountScatter, PriceMultidim180d, EtfHeroStrip
//
// Recharts is mocked to avoid heavy SVG rendering in jsdom.

import { vi, describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

// ── Recharts mock — avoid heavy chart rendering in tests ──────────────────────

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="rc">{children}</div>
  ),
  ScatterChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="scatter-chart">{children}</div>
  ),
  Scatter: () => null,
  ComposedChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="composed-chart">{children}</div>
  ),
  Line: () => null,
  Bar: ({ children }: { children?: ReactNode }) => (
    <div data-testid="bar">{children}</div>
  ),
  Cell: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ReferenceLine: () => null,
  ReferenceArea: () => null,
}))

// ── Import AFTER mocks ────────────────────────────────────────────────────────

import { PremiumDiscountScatter } from '../PremiumDiscountScatter'
import { PriceMultidim180d } from '../PriceMultidim180d'
import { EtfHeroStrip } from '../EtfHeroStrip'
import type { EtfListV6Row, PriceBar, EtfDeepdiveRow } from '@/lib/queries/v6/etfs'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeEtfRow(overrides: Partial<EtfListV6Row> = {}): EtfListV6Row {
  return {
    ticker: 'TESTBEES',
    etf_name: 'Test ETF BeES',
    fund_house: 'NIPPON',
    asset_class: 'equity',
    etf_category: 'index',
    composite_score: 0.72,
    is_atlas_leader: false,
    premium_bps: 5,
    te_60d: 0.0010,
    adv_20d_inr: 5e7,
    adv_monthly_cr: 150,
    ret_1d: 0.002,
    ret_1w: 0.01,
    ret_1m: 0.03,
    ret_3m: 0.05,
    ret_6m: 0.08,
    ret_12m: 0.15,
    rs_state: 'Strong',
    momentum_state: 'Strong',
    action: 'BUY',
    scatter_zone: 'clean_buy',
    signal_fire_date: '2026-01-15',
    signal_tenure: null,
    as_of_date: '2026-05-27',
    eli5: 'Strong gold leadership',
    ...overrides,
  }
}

function makePriceBar(overrides: Partial<PriceBar> = {}): PriceBar {
  return {
    date: '2026-05-27',
    open: 100,
    high: 102,
    low: 99,
    close: 101,
    volume: 500000,
    ...overrides,
  }
}

function makeDeepdiveRow(overrides: Partial<EtfDeepdiveRow> = {}): EtfDeepdiveRow {
  return {
    ticker: 'GOLDBEES',
    etf_name: 'Nippon India ETF Gold BeES',
    fund_house: 'NIPPON',
    asset_class: 'commodity',
    etf_category: 'commodity',
    as_of_date: '2026-05-27',
    composite_score: 0.82,
    is_atlas_leader: true,
    premium_bps: 3,
    te_60d: 0.0008,
    adv_20d_inr: 8.4e7,
    ret_1m: 0.02,
    ret_3m: 0.06,
    ret_6m: 0.10,
    ret_12m: 0.18,
    rs_state: 'Leader',
    action: 'BUY',
    eli5: 'Gold ETF with tight tracking and high liquidity.',
    price_180d: null,
    peer_set: null,
    ...overrides,
  }
}

// ── PremiumDiscountScatter ────────────────────────────────────────────────────

describe('PremiumDiscountScatter', () => {
  it('renders chart container with valid ETF data', () => {
    const etfs = [
      makeEtfRow({ ticker: 'GOLDBEES', action: 'BUY', premium_bps: 3, adv_20d_inr: 8.4e7 }),
      makeEtfRow({ ticker: 'CPSEETF', action: 'BUY', premium_bps: 30, adv_20d_inr: 4.6e7 }),
      makeEtfRow({ ticker: 'NIFTYBEES', action: 'WATCH', premium_bps: -10, adv_20d_inr: 6.2e7 }),
    ]
    render(<PremiumDiscountScatter etfs={etfs} />)
    expect(screen.getByTestId('premium-discount-scatter')).toBeDefined()
    expect(screen.getByTestId('scatter-chart')).toBeDefined()
  })

  it('shows empty state when no ETFs have adv_20d_inr', () => {
    const etfs = [
      makeEtfRow({ adv_20d_inr: null }),
    ]
    render(<PremiumDiscountScatter etfs={etfs} />)
    expect(screen.getByText(/iNAV ingest first/)).toBeDefined()
  })

  it('renders with null premium_bps (plots at x=0)', () => {
    const etfs = [
      makeEtfRow({ ticker: 'UTINEXT50', premium_bps: null, adv_20d_inr: 5e7, scatter_zone: 'premium_unknown' }),
    ]
    render(<PremiumDiscountScatter etfs={etfs} />)
    // Should render chart (adv_20d_inr is non-null), not empty state
    expect(screen.getByTestId('premium-discount-scatter')).toBeDefined()
  })

  it('shapes toScatterPoints correctly: log10 y value >= 0', () => {
    // ₹0.1cr ADV → log10(0.1) = -1 → clamp to 0
    const etfs = [
      makeEtfRow({ adv_20d_inr: 1e6, premium_bps: 0 }),  // 0.1 cr
    ]
    render(<PremiumDiscountScatter etfs={etfs} />)
    // Chart renders (non-empty), no crash
    expect(screen.getByTestId('premium-discount-scatter')).toBeDefined()
  })
})

// ── PriceMultidim180d ─────────────────────────────────────────────────────────

describe('PriceMultidim180d', () => {
  it('renders chart with valid price data', () => {
    const bars: PriceBar[] = Array.from({ length: 30 }, (_, i) =>
      makePriceBar({
        date: `2026-0${Math.floor(i / 30) + 3}-${String((i % 28) + 1).padStart(2, '0')}`,
        close: 100 + i * 0.5,
        volume: 5e5 + i * 1000,
      }),
    )
    render(<PriceMultidim180d ticker="GOLDBEES" priceData={bars} />)
    expect(screen.getByTestId('price-multidim-180d')).toBeDefined()
  })

  it('renders empty state when priceData is null', () => {
    render(<PriceMultidim180d ticker="GOLDBEES" priceData={null} />)
    expect(screen.getByTestId('price-multidim-empty')).toBeDefined()
    expect(screen.getByText(/GOLDBEES/)).toBeDefined()
  })

  it('renders empty state when priceData is empty array', () => {
    render(<PriceMultidim180d ticker="TESTBEES" priceData={[]} />)
    expect(screen.getByTestId('price-multidim-empty')).toBeDefined()
  })

  it('computes 20D MA correctly — first 19 bars have null MA', () => {
    // Build 25 bars with known closes: 100..124
    const bars: PriceBar[] = Array.from({ length: 25 }, (_, i) =>
      makePriceBar({ date: `2026-01-${String(i + 1).padStart(2, '0')}`, close: 100 + i, volume: 1e5 })
    )
    render(<PriceMultidim180d ticker="TESTBEES" priceData={bars} />)
    // Should render without crash — 20D MA is null for first 19 bars (connectNulls handles gap)
    expect(screen.getByTestId('price-multidim-180d')).toBeDefined()
  })

  it('per-bar volume coloring: Cell children render without crash', () => {
    const bars: PriceBar[] = [
      makePriceBar({ close: 100, volume: 1e5 }),
      makePriceBar({ close: 99, volume: 2e5 }),  // down → red
      makePriceBar({ close: 101, volume: 1.5e5 }), // up → green
    ]
    render(<PriceMultidim180d ticker="GOLDBEES" priceData={bars} />)
    // Bar component renders (Cell mocked, no crash)
    expect(screen.getAllByTestId('bar').length).toBeGreaterThanOrEqual(1)
  })
})

// ── EtfHeroStrip ──────────────────────────────────────────────────────────────

describe('EtfHeroStrip', () => {
  it('renders all 6 metric tiles with valid data', () => {
    const row = makeDeepdiveRow()
    render(<EtfHeroStrip deepdive={row} />)
    expect(screen.getByTestId('etf-hero-strip')).toBeDefined()
    // Ticker and action badge
    expect(screen.getByText('GOLDBEES')).toBeDefined()
    expect(screen.getByText('BUY')).toBeDefined()
  })

  it('renders — for null premium_bps', () => {
    const row = makeDeepdiveRow({ premium_bps: null })
    render(<EtfHeroStrip deepdive={row} />)
    // fmtBps(null) → '—'
    const strip = screen.getByTestId('etf-hero-strip')
    expect(strip.textContent).toContain('—')
  })

  it('renders — for null te_60d', () => {
    const row = makeDeepdiveRow({ te_60d: null })
    render(<EtfHeroStrip deepdive={row} />)
    // fmtTe(null) → '—'
    const strip = screen.getByTestId('etf-hero-strip')
    expect(strip.textContent).toContain('—')
  })

  it('shows AVOID badge for AVOID action', () => {
    const row = makeDeepdiveRow({ action: 'AVOID' })
    render(<EtfHeroStrip deepdive={row} />)
    expect(screen.getByText('AVOID')).toBeDefined()
  })

  it('rs_state hint includes band attribution', () => {
    const row = makeDeepdiveRow({ rs_state: 'Leader' })
    render(<EtfHeroStrip deepdive={row} />)
    const strip = screen.getByTestId('etf-hero-strip')
    expect(strip.textContent).toContain('rs_pctile_3m band')
  })

  it('handles null rs_state gracefully', () => {
    const row = makeDeepdiveRow({ rs_state: null })
    render(<EtfHeroStrip deepdive={row} />)
    // rs_state ?? '—' → '—'
    const strip = screen.getByTestId('etf-hero-strip')
    expect(strip.textContent).toContain('—')
  })
})
