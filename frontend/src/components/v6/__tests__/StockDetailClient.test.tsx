// frontend/src/components/v6/__tests__/StockDetailClient.test.tsx
//
// C.16 tests — 5 required cases:
//   1. Hero renders with grade chip + ticker + PortfolioBadge expanded when held
//   2. PortfolioBadge silently absent when holdingState === null
//   3. CrossRuleDepth shows N/5 rules when data; shows "—" when null
//   4. Tab switching works (Overview → Technicals → Audit)
//   5. CrossRuleDepth color: 5/5=signal-pos, 3-4=signal-warn, 0-2=signal-neg

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StockHero } from '../StockHero'
import type { StockHeroProps } from '../StockHero'
import type { ScreenStock } from '@/lib/api/v1'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { StockTechnicals } from '@/lib/queries/v6/stock_technicals'
import { StockDetailClient } from '../StockDetailClient'
import type { StockDetailClientProps } from '../StockDetailClient'

// ---------------------------------------------------------------------------
// Mock ConvictionTape (uses client-only Radix primitives internally is fine)
// ---------------------------------------------------------------------------

vi.mock('../ConvictionTape', () => ({
  ConvictionTape: ({ tape }: { tape: unknown }) => (
    <div data-testid="conviction-tape" data-tape={JSON.stringify(tape)} />
  ),
}))

vi.mock('../TVMetricsBadge', () => ({
  TVMetricsBadgeFromRow: () => <div data-testid="tv-metrics-badge-from-row" />,
}))

vi.mock('../TVChartPanel', () => ({
  TVChartPanel: ({ symbol }: { symbol: string }) => (
    <div data-testid="tv-chart-panel" role="tabpanel" aria-labelledby="tab-chart" id="tabpanel-chart">
      TVChart:{symbol}
    </div>
  ),
}))

vi.mock('../PositionSizingWidget', () => ({
  PositionSizingWidget: ({ cellConvictionDepth }: { cellConvictionDepth: number }) => (
    <div data-testid="position-sizing-widget" data-depth={cellConvictionDepth} />
  ),
}))

vi.mock('../GradeChip', () => ({
  GradeChip: ({ grade }: { grade: string }) => (
    <span data-testid="grade-chip" data-grade={grade} role="img" aria-label={`Atlas grade ${grade}`}>
      {grade}
    </span>
  ),
}))

vi.mock('../PortfolioBadge', () => ({
  PortfolioBadge: ({ state, variant }: { state: unknown; variant?: string }) => {
    if (!state) return null
    return (
      <div
        data-testid="portfolio-badge"
        data-variant={variant}
      >
        PortfolioBadge
      </div>
    )
  },
}))

vi.mock('../MultiBenchmarkRSWaterfall', () => ({
  MultiBenchmarkRSWaterfall: () => <div data-testid="waterfall" />,
}))

vi.mock('../RankDecompositionCards', () => ({
  RankDecompositionCards: () => <div data-testid="rank-decomposition" />,
}))

vi.mock('../MultiTenureReturnsTable', () => ({
  MultiTenureReturnsTable: () => <div data-testid="multi-tenure-returns" />,
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const NEUTRAL_VERDICT = { direction: 'NEUTRAL' as const, ic: null, rule_count: 0, top_rule_id: null }
const POS_VERDICT = { direction: 'POSITIVE' as const, ic: 0.07, rule_count: 3, top_rule_id: 'r1' }

const MOCK_STOCK: ScreenStock = {
  iid: 'aaa-111',
  symbol: 'RELIANCE',
  company_name: 'Reliance Industries Ltd',
  sector: 'Energy',
  tier: 'Large',
  mcap_inr: null,
  rs_state: 'Stage2',
  stage: null,
  conviction_tape: {
    '1m': NEUTRAL_VERDICT,
    '3m': POS_VERDICT,
    '6m': POS_VERDICT,
    '12m': POS_VERDICT,
  },
  ret_1m: 0.03,
  ret_3m: 0.08,
  ret_6m: 0.15,
  ret_12m: 0.22,
  rs_pctile_3m: 0.72,
  is_investable: true,
}

const MOCK_HOLDING: HoldingState = {
  portfolio_count: 2,
  weight_range: ['0.03', '0.04'],
  aggregate_weight: '0.035',
  last_add_date: '2026-04-10',
}

const MOCK_TECHNICALS: StockTechnicals = {
  iid: 'aaa-111',
  date: '2026-05-26',
  ema_distance_20: '0.05',
  ema_distance_50: '0.08',
  ema_distance_200: '0.12',
  rsi_14: '62.5',
  rs_pct_nifty500: '0.15',
  vol_252d: '0.24',
  obv_20d: '0.0012',
  atr_14: '0.02',
  pct_from_52w_high: '-0.08',
  pct_from_52w_low: '0.32',
  log_med_tv_60d: '12.5',
  drawdown_from_peak: '-0.12',
}

const BASE_HERO_PROPS: StockHeroProps = {
  stock: MOCK_STOCK,
  holdingState: null,
  technicals: MOCK_TECHNICALS,
  deploymentMultiplier: 1.0,
  sectorGapPp: 0,
  crossRuleDepth: null,
  actionVerb: 'BUY',
  bullets: ['Strong momentum.', 'RS outperforming cohort.'],
}

const BASE_CLIENT_PROPS: StockDetailClientProps = {
  stock: MOCK_STOCK,
  holdingState: null,
  technicals: MOCK_TECHNICALS,
  returns: null,
  fundsHolding: [],
  auditTrail: null,
  crossRuleDepth: null,
  deploymentMultiplier: 1.0,
  sectorGapPp: 0,
  actionVerb: 'BUY',
  bullets: ['Strong momentum.'],
  tvMetrics: null,
  waterfallData: null,
  rankData: null,
}

// ---------------------------------------------------------------------------
// Test 1: Hero renders with grade chip + ticker + PortfolioBadge when held
// ---------------------------------------------------------------------------

describe('StockHero — renders with grade chip + ticker + PortfolioBadge when held', () => {
  it('shows grade chip, ticker symbol, and PortfolioBadge expanded variant', () => {
    render(
      <StockHero
        {...BASE_HERO_PROPS}
        holdingState={MOCK_HOLDING}
      />,
    )

    // Grade chip present
    expect(screen.getByTestId('grade-chip')).toBeInTheDocument()

    // Ticker symbol present
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()

    // PortfolioBadge present (expanded variant)
    const badge = screen.getByTestId('portfolio-badge')
    expect(badge).toBeInTheDocument()
    expect(badge.getAttribute('data-variant')).toBe('expanded')
  })

  it('shows action verb in hero', () => {
    render(<StockHero {...BASE_HERO_PROPS} holdingState={MOCK_HOLDING} actionVerb="ACCUMULATE" />)
    expect(screen.getByText('ACCUMULATE')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: PortfolioBadge silently absent when holdingState === null
// ---------------------------------------------------------------------------

describe('StockHero — PortfolioBadge absent when holdingState is null', () => {
  it('does NOT render PortfolioBadge when holdingState is null', () => {
    render(<StockHero {...BASE_HERO_PROPS} holdingState={null} />)
    expect(screen.queryByTestId('portfolio-badge')).not.toBeInTheDocument()
  })

  it('still renders ticker and grade chip without holding', () => {
    render(<StockHero {...BASE_HERO_PROPS} holdingState={null} />)
    expect(screen.getByTestId('grade-chip')).toBeInTheDocument()
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: CrossRuleDepth — shows N/5 when data; shows "—" when null
// ---------------------------------------------------------------------------

describe('StockHero — CrossRuleDepth metric', () => {
  it('shows "3/5 rules" when depth is 3 of 5', () => {
    render(
      <StockHero
        {...BASE_HERO_PROPS}
        crossRuleDepth={{ depth: 3, total: 5 }}
      />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el).toBeInTheDocument()
    expect(el.textContent).toContain('3/5 rules')
  })

  it('shows "—" when crossRuleDepth is null', () => {
    render(<StockHero {...BASE_HERO_PROPS} crossRuleDepth={null} />)
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.textContent).toContain('—')
  })

  it('shows "—" when depth is null inside the data object', () => {
    render(
      <StockHero
        {...BASE_HERO_PROPS}
        crossRuleDepth={{ depth: null, total: 5 }}
      />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.textContent).toContain('—')
  })
})

// ---------------------------------------------------------------------------
// Test 4: Tab switching — Overview → Technicals → Audit
// ---------------------------------------------------------------------------

describe('StockDetailClient — tab switching', () => {
  it('defaults to Overview tab and shows it', () => {
    render(<StockDetailClient {...BASE_CLIENT_PROPS} />)
    // Overview tab should be aria-selected
    const overviewTab = screen.getByRole('tab', { name: 'Overview' })
    expect(overviewTab.getAttribute('aria-selected')).toBe('true')
  })

  it('switches to Technicals tab on click', () => {
    render(<StockDetailClient {...BASE_CLIENT_PROPS} />)
    const techTab = screen.getByRole('tab', { name: 'Technicals' })
    fireEvent.click(techTab)
    expect(techTab.getAttribute('aria-selected')).toBe('true')
    // Technicals panel visible — check for no technical data message
    expect(screen.getByRole('tabpanel', { name: /technicals/i })).toBeInTheDocument()
  })

  it('switches to Chart tab on click and shows TVChartPanel (TV-05)', () => {
    render(<StockDetailClient {...BASE_CLIENT_PROPS} />)
    const chartTab = screen.getByRole('tab', { name: 'Chart' })
    fireEvent.click(chartTab)
    expect(chartTab.getAttribute('aria-selected')).toBe('true')
    expect(screen.getByTestId('tv-chart-panel')).toBeInTheDocument()
  })

  it('switches to Audit tab on click', () => {
    render(<StockDetailClient {...BASE_CLIENT_PROPS} />)
    const auditTab = screen.getByRole('tab', { name: 'Audit' })
    fireEvent.click(auditTab)
    expect(auditTab.getAttribute('aria-selected')).toBe('true')
  })
})

// ---------------------------------------------------------------------------
// Test 5: CrossRuleDepth color classes
// ---------------------------------------------------------------------------

describe('StockHero — CrossRuleDepth color classes', () => {
  it('applies signal-pos class for 5/5 (full conviction)', () => {
    render(
      <StockHero {...BASE_HERO_PROPS} crossRuleDepth={{ depth: 5, total: 5 }} />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.className).toContain('text-signal-pos')
  })

  it('applies signal-pos class for 4/5', () => {
    render(
      <StockHero {...BASE_HERO_PROPS} crossRuleDepth={{ depth: 4, total: 5 }} />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.className).toContain('text-signal-warn')
  })

  it('applies signal-warn class for 3/5', () => {
    render(
      <StockHero {...BASE_HERO_PROPS} crossRuleDepth={{ depth: 3, total: 5 }} />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.className).toContain('text-signal-warn')
  })

  it('applies signal-neg class for 2/5 (low conviction)', () => {
    render(
      <StockHero {...BASE_HERO_PROPS} crossRuleDepth={{ depth: 2, total: 5 }} />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.className).toContain('text-signal-neg')
  })

  it('applies signal-neg class for 0/5 (no conviction)', () => {
    render(
      <StockHero {...BASE_HERO_PROPS} crossRuleDepth={{ depth: 0, total: 5 }} />,
    )
    const el = screen.getByTestId('cross-rule-depth')
    expect(el.className).toContain('text-signal-neg')
  })
})
