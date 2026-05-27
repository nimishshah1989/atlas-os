// frontend/src/components/v6/__tests__/FundDetailClient.test.tsx
//
// D.6 test cases:
//   1. Hero renders all elements (grade + manager + AUM + thesis)
//   2. PortfolioBadge expanded when held; absent when null
//   3. Holdings tab renders top-20 with verdict chips
//   4. Tab switching (Overview / Holdings / Audit)
//   5. SWITCH banner visible when fund is Q3/Q4

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FundDetailClient } from '../FundDetailClient'
import { FundHero } from '../FundHero'
import type { FundDetailClientProps } from '../FundDetailClient'
import type { FundDetail } from '@/lib/queries/v6/funds'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { SwitchProposal } from '@/lib/queries/v6/switch_proposals'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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
      <div data-testid="portfolio-badge" data-variant={variant}>
        PortfolioBadge
      </div>
    )
  },
}))

vi.mock('../SwitchProposalsBanner', () => ({
  SwitchProposalsBanner: ({ proposals }: { proposals: unknown[] }) => {
    if (!proposals || proposals.length === 0) return null
    return (
      <div data-testid="switch-proposals-banner">
        {proposals.length} switch proposal(s)
      </div>
    )
  },
}))

vi.mock('../RankDecompositionCards', () => ({
  RankDecompositionCards: () => <div data-testid="rank-decomposition" />,
}))

vi.mock('../MultiBenchmarkRSWaterfall', () => ({
  MultiBenchmarkRSWaterfall: () => <div data-testid="waterfall" />,
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_FUND: FundDetail = {
  iid: 'fund-abc-123',
  code: 'INF200KA1RD2',
  name: 'Axis Bluechip Fund - Growth',
  category: 'Large Cap',
  amc: 'Axis AMC',
  fund_style: 'Growth',
  composite_score: '72.50',
  risk_adjusted_return_score: '75.00',
  holdings_conviction_score: '65.00',
  style_sector_score: '70.00',
  cost_manager_score: '80.00',
  rank_in_category: 3,
  category_size: 25,
  is_atlas_leader: true,
  is_avoid: false,
  confidence_low: false,
  eli5: 'Strong risk-adjusted returns. Manager tenure of 8 years. Low expense ratio.',
  ter_pct: '1.25',
  aum_cr: '12500',
  manager_tenure_years: '8.2',
  fund_age_years: '11.5',
  sharpe: '1.42',
  max_dd: '-0.28',
  ret_1m: 0.025,
  ret_3m: 0.082,
  ret_6m: 0.156,
  ret_12m: 0.221,
  rs_pctile_3m: '0.78',
  top_holdings: [
    { instrument_id: 'iid-001', symbol: 'RELIANCE', weight_pct: 9.5, verdict: 'POSITIVE' },
    { instrument_id: 'iid-002', symbol: 'HDFC', weight_pct: 8.2, verdict: 'NEUTRAL' },
    { instrument_id: 'iid-003', symbol: 'INFY', weight_pct: 7.1, verdict: 'NEGATIVE' },
    { instrument_id: 'iid-004', symbol: 'TCS', weight_pct: 6.8, verdict: 'POSITIVE' },
    { instrument_id: null, symbol: null, weight_pct: 4.2, verdict: null }, // not in universe
  ],
  snapshot_date: '2026-05-26',
  nav_as_of: '2026-05-25',
  holdings_as_of: '2026-04-30',
}

const MOCK_HOLDING: HoldingState = {
  portfolio_count: 2,
  weight_range: ['0.08', '0.10'],
  aggregate_weight: '0.09',
  last_add_date: '2026-04-01',
}

const MOCK_SWITCH_PROPOSAL: SwitchProposal = {
  source_iid: 'fund-abc-123',
  source_code: 'INF200KA1RD2',
  source_name: 'Axis Bluechip Fund - Growth',
  source_peer_quartile: 'Q3',
  target_iid: 'fund-xyz-456',
  target_code: 'INF109KA1RZ3',
  target_name: 'Mirae Asset Large Cap Fund - Growth',
  target_peer_quartile: 'Q1',
  category: 'Large Cap',
}

const BASE_PROPS: FundDetailClientProps = {
  fund: MOCK_FUND,
  holdingState: null,
  switchProposals: [],
  waterfallData: null,
}

// ---------------------------------------------------------------------------
// Test 1: Hero renders all elements (grade + manager + AUM + thesis)
// ---------------------------------------------------------------------------

describe('FundHero — renders all required elements', () => {
  it('shows grade chip, fund name, manager tenure, AUM and thesis bullets', () => {
    render(
      <FundHero
        fund={MOCK_FUND}
        holdingState={null}
        switchProposals={[]}
      />,
    )

    // Grade chip present
    expect(screen.getByTestId('grade-chip')).toBeInTheDocument()

    // Fund name present
    expect(screen.getByText('Axis Bluechip Fund - Growth')).toBeInTheDocument()

    // Manager tenure (8.2 years → "8 yrs")
    expect(screen.getByText(/8 yrs/)).toBeInTheDocument()

    // AUM ("₹12,500 Cr")
    expect(screen.getByText(/12,500/)).toBeInTheDocument()

    // TER
    expect(screen.getByText(/1.25%/)).toBeInTheDocument()

    // Thesis bullets (ELI5 parsed)
    expect(screen.getByText(/Strong risk-adjusted returns/)).toBeInTheDocument()
  })

  it('shows Atlas Leader badge when is_atlas_leader is true', () => {
    render(
      <FundHero
        fund={MOCK_FUND}
        holdingState={null}
        switchProposals={[]}
      />,
    )
    expect(screen.getByText('Atlas Leader')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: PortfolioBadge expanded when held; absent when null
// ---------------------------------------------------------------------------

describe('FundHero — PortfolioBadge', () => {
  it('renders PortfolioBadge expanded variant when holdingState is non-null', () => {
    render(
      <FundHero
        fund={MOCK_FUND}
        holdingState={MOCK_HOLDING}
        switchProposals={[]}
      />,
    )
    const badge = screen.getByTestId('portfolio-badge')
    expect(badge).toBeInTheDocument()
    expect(badge.getAttribute('data-variant')).toBe('expanded')
  })

  it('does NOT render PortfolioBadge when holdingState is null', () => {
    render(
      <FundHero
        fund={MOCK_FUND}
        holdingState={null}
        switchProposals={[]}
      />,
    )
    expect(screen.queryByTestId('portfolio-badge')).not.toBeInTheDocument()
  })

  it('still renders grade chip and fund name without holding', () => {
    render(
      <FundHero
        fund={MOCK_FUND}
        holdingState={null}
        switchProposals={[]}
      />,
    )
    expect(screen.getByTestId('grade-chip')).toBeInTheDocument()
    expect(screen.getByText('Axis Bluechip Fund - Growth')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: Holdings tab renders top-20 with verdict chips
// ---------------------------------------------------------------------------

describe('FundDetailClient — Holdings tab', () => {
  it('renders holdings table with verdict chips after switching to Holdings tab', () => {
    render(<FundDetailClient {...BASE_PROPS} />)

    // Switch to Holdings tab
    const holdingsTab = screen.getByRole('tab', { name: 'Holdings' })
    fireEvent.click(holdingsTab)

    // Table should be present
    expect(screen.getByRole('tabpanel', { name: /holdings/i })).toBeInTheDocument()

    // Holdings from fixture
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.getByText('HDFC')).toBeInTheDocument()
    expect(screen.getByText('INFY')).toBeInTheDocument()
    expect(screen.getByText('TCS')).toBeInTheDocument()
  })

  it('shows verdict chips for in-universe holdings', () => {
    render(<FundDetailClient {...BASE_PROPS} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Holdings' }))

    // POSITIVE verdict
    expect(screen.getAllByText('POSITIVE').length).toBeGreaterThan(0)
    // NEUTRAL verdict
    expect(screen.getAllByText('NEUTRAL').length).toBeGreaterThan(0)
    // NEGATIVE verdict
    expect(screen.getAllByText('NEGATIVE').length).toBeGreaterThan(0)
  })

  it('shows "Not in universe" chip for holdings with null instrument_id', () => {
    render(<FundDetailClient {...BASE_PROPS} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Holdings' }))

    expect(screen.getByText('Not in universe')).toBeInTheDocument()
  })

  it('shows empty state when top_holdings is null', () => {
    const fundNoHoldings = { ...MOCK_FUND, top_holdings: null }
    render(<FundDetailClient {...BASE_PROPS} fund={fundNoHoldings} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Holdings' }))

    expect(screen.getByText(/Holdings data not available/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 4: Tab switching (Overview / Holdings / Audit)
// ---------------------------------------------------------------------------

describe('FundDetailClient — tab switching', () => {
  it('defaults to Overview tab', () => {
    render(<FundDetailClient {...BASE_PROPS} />)
    const overviewTab = screen.getByRole('tab', { name: 'Overview' })
    expect(overviewTab.getAttribute('aria-selected')).toBe('true')
  })

  it('switches to Holdings tab on click', () => {
    render(<FundDetailClient {...BASE_PROPS} />)
    const holdingsTab = screen.getByRole('tab', { name: 'Holdings' })
    fireEvent.click(holdingsTab)
    expect(holdingsTab.getAttribute('aria-selected')).toBe('true')
  })

  it('switches to Audit Trail tab on click', () => {
    render(<FundDetailClient {...BASE_PROPS} />)
    const auditTab = screen.getByRole('tab', { name: 'Audit Trail' })
    fireEvent.click(auditTab)
    expect(auditTab.getAttribute('aria-selected')).toBe('true')
  })

  it('shows fund audit trail placeholder on Audit tab', () => {
    render(<FundDetailClient {...BASE_PROPS} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Audit Trail' }))
    expect(screen.getByText(/Fund Audit Trail/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 5: SWITCH banner visible when fund is Q3/Q4
// ---------------------------------------------------------------------------

describe('FundDetailClient — SWITCH proposal banner', () => {
  it('shows switch banner in hero when fund has a Q3 switch proposal', () => {
    render(
      <FundDetailClient
        {...BASE_PROPS}
        switchProposals={[MOCK_SWITCH_PROPOSAL]}
      />,
    )

    // Banner should be present (proposal is for source_code = 'INF200KA1RD2' which matches fund.code)
    expect(screen.getByTestId('switch-proposals-banner')).toBeInTheDocument()
    expect(screen.getByText(/1 switch proposal/)).toBeInTheDocument()
  })

  it('does NOT show switch banner when there are no proposals', () => {
    render(<FundDetailClient {...BASE_PROPS} switchProposals={[]} />)
    expect(screen.queryByTestId('switch-proposals-banner')).not.toBeInTheDocument()
  })

  it('does NOT show switch banner for proposals belonging to a different fund', () => {
    const otherProposal: SwitchProposal = {
      ...MOCK_SWITCH_PROPOSAL,
      source_iid: 'other-fund-999',
      source_code: 'INF999XX9XX9',
    }
    render(
      <FundDetailClient
        {...BASE_PROPS}
        switchProposals={[otherProposal]}
      />,
    )
    expect(screen.queryByTestId('switch-proposals-banner')).not.toBeInTheDocument()
  })
})
