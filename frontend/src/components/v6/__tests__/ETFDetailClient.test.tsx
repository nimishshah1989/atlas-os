// frontend/src/components/v6/__tests__/ETFDetailClient.test.tsx
//
// D.8 — 5 test cases for ETFDetailClient:
//  1. Hero with TE / expense / AUM renders metric values
//  2. PortfolioBadge in hero when held (expanded variant)
//  3. Tab switching: clicking Holdings renders holdings panel
//  4. Missing TE renders "—" (no synthetic data substitution)
//  5. AuditTrailTab renders when Audit tab selected

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ETFDetailClient } from '../ETFDetailClient'
import type { ETFDetailClientProps } from '../ETFDetailClient'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ---------------------------------------------------------------------------
// Mock lazy imports (AuditTrailTab, MultiBenchmarkRSWaterfall use canvas/Recharts)
// ---------------------------------------------------------------------------

vi.mock('../AuditTrailTab', () => ({
  default: ({ auditTrail }: { auditTrail: unknown }) => (
    <div data-testid="audit-trail-tab">
      {auditTrail ? 'Audit data present' : 'No audit trail data available for this stock.'}
    </div>
  ),
}))

vi.mock('../MultiBenchmarkRSWaterfall', () => ({
  MultiBenchmarkRSWaterfall: ({ data }: { data: { tenure: string } }) => (
    <div data-testid="waterfall">{data.tenure}</div>
  ),
}))

vi.mock('../RankDecompositionCards', () => ({
  RankDecompositionCards: ({ composite_score }: { composite_score: string }) => (
    <div data-testid="rank-decomposition">composite: {composite_score}</div>
  ),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE_HERO: ETFDetailClientProps['hero'] = {
  iid: 'aaaa-1111',
  ticker: 'NIFTYBEES',
  name: 'Nippon India ETF Nifty BeES',
  category: 'broad_index',
  composite_score: '78.50',
  is_atlas_leader: false,
  aum_cr: '25000',
  expense_ratio: '0.0004',  // 0.04%
  tracking_error: '0.0023', // 0.23%
  bid_ask_spread: null,
  premium_to_nav: null,
  eli5: 'Broad Nifty 50 index ETF with lowest expense ratio in category; strong AUM and liquidity.',
  net_flow_30d: null,
}

const HOLDING_STATE: HoldingState = {
  portfolio_count: 2,
  weight_range: ['0.03', '0.05'],
  aggregate_weight: '0.038',
  last_add_date: '2026-05-10',
}

const RANK_DATA: ETFDetailClientProps['rankData'] = {
  composite_score: '78.50',
  components: [
    { name: 'Matrix Conviction', raw_score: '80', percentile_in_category: '80', weight_pct: '30', delta_vs_cohort: '30' },
  ],
  rank_in_category: 3,
  category_size: 24,
}

const WATERFALL_DATA: ETFDetailClientProps['waterfallData'] = {
  stock_return: '12.5',
  cohort_return: '10.0',
  nifty50_return: '0',
  nifty500_return: '0',
  gold_return: null,
  tenure: '6m',
}

const BASE_PROPS: ETFDetailClientProps = {
  hero: BASE_HERO,
  holdingState: null,
  auditTrail: null,
  rankData: RANK_DATA,
  waterfallData: WATERFALL_DATA,
  holdings: [],
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ETFDetailClient', () => {

  it('Hero renders TE / expense / AUM metric values', () => {
    render(<ETFDetailClient {...BASE_PROPS} />)

    // ETF ticker visible in hero h1
    expect(screen.getByTestId('etf-ticker')).toHaveTextContent('NIFTYBEES')

    // Metric tiles rendered
    expect(screen.getByTestId('etf-metrics')).toBeInTheDocument()

    // Tracking error: 0.0023 * 100 = 0.23%
    expect(screen.getByText('0.23%')).toBeInTheDocument()

    // Expense ratio: 0.0004 * 100 = 0.04%
    expect(screen.getByText('0.04%')).toBeInTheDocument()

    // AUM: ₹25000 Cr
    expect(screen.getByText(/₹25000 Cr|₹25\.0K Cr/)).toBeInTheDocument()

    // Thesis bullet from eli5
    expect(screen.getByTestId('etf-thesis')).toBeInTheDocument()
  })

  it('PortfolioBadge rendered in hero when ETF is held', () => {
    render(<ETFDetailClient {...BASE_PROPS} holdingState={HOLDING_STATE} />)

    // PortfolioBadge expanded renders "Held in N portfolios"
    expect(screen.getByRole('status', { name: /2 portfolios/i })).toBeInTheDocument()

    // Text "Held in" present
    expect(screen.getByText(/Held in/)).toBeInTheDocument()
  })

  it('PortfolioBadge absent when holdingState is null', () => {
    render(<ETFDetailClient {...BASE_PROPS} holdingState={null} />)

    // No "Held" text when not held
    expect(screen.queryByRole('status', { name: /portfolios/i })).not.toBeInTheDocument()
  })

  it('Tab switching: clicking Holdings tab renders holdings panel', () => {
    const holdings = [
      { ticker: 'RELIANCE', weight_pct: '0.1023', sector: 'Energy' },
      { ticker: 'TCS', weight_pct: '0.0891', sector: 'Technology' },
    ]
    render(<ETFDetailClient {...BASE_PROPS} holdings={holdings} />)

    // Initially on Overview tab — holdings panel not visible
    expect(screen.queryByText('RELIANCE')).not.toBeInTheDocument()

    // Click Holdings tab
    const holdingsTab = screen.getByRole('tab', { name: 'Holdings' })
    fireEvent.click(holdingsTab)

    // Holdings panel now visible
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.getByText('TCS')).toBeInTheDocument()

    // Weight rendered: 0.1023 * 100 = 10.23%
    expect(screen.getByText('10.23%')).toBeInTheDocument()
  })

  it('Missing TE renders "—" (no synthetic data)', () => {
    const heroWithNullTE: ETFDetailClientProps['hero'] = {
      ...BASE_HERO,
      tracking_error: null,
      expense_ratio: null,
    }
    render(<ETFDetailClient {...BASE_PROPS} hero={heroWithNullTE} />)

    // Multiple "—" dashes for null metrics
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(2)

    // Confirm no synthetic value injected — TE label is present
    expect(screen.getByText('Tracking Error')).toBeInTheDocument()

    // Expense Ratio label is present
    expect(screen.getByText('Expense Ratio')).toBeInTheDocument()
  })

  it('AuditTrailTab renders when Audit tab is clicked', async () => {
    render(<ETFDetailClient {...BASE_PROPS} auditTrail={null} />)

    // Click Audit tab
    const auditTab = screen.getByRole('tab', { name: 'Audit' })
    fireEvent.click(auditTab)

    // AuditTrailTab renders (mocked — checks graceful null state)
    const auditPanel = await screen.findByTestId('audit-trail-tab')
    expect(auditPanel).toBeInTheDocument()
    expect(auditPanel).toHaveTextContent('No audit trail data available')
  })

})
