/**
 * Task 1.7 — StockScreener sector/index pre-filter banner (TDD: failing first)
 *
 * Tests:
 * - When initialSectorFilter is passed, screener shows "Filtering: Banking ✕" banner
 * - Clicking ✕ navigates to /stocks (clears filter)
 * - When initialIndexFilter is passed, shows "Filtering: Nifty 50 ✕" banner
 * - Without initial filter props, no banner shown
 * - When sector filter active, default sort is within_state_rank desc
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { StockScreener } from '../StockScreener'
import type { StockRowWithSector } from '@/lib/queries/stocks'

// Mock next/link — in jsdom it just renders an <a>
vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [k: string]: unknown }) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

// Mock next/navigation for router.push
const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeStockRow(overrides: Partial<StockRowWithSector> = {}): StockRowWithSector {
  return {
    instrument_id: 'inst-1',
    symbol: 'HDFC',
    company_name: 'HDFC Bank',
    sector: 'Banking',
    in_nifty_50: true,
    in_nifty_100: true,
    in_nifty_500: true,
    ret_1m: '0.03',
    ret_3m: '0.07',
    ret_6m: '0.12',
    rs_pctile_3m: '0.80',
    above_30w_ma: true,
    ema_10_at_20d_high: true,
    weinstein_gate_pass: true,
    ret_1w: null,
    extension_pct: null,
    vol_63: null,
    realized_vol_63: null,
    avg_volume_20: null,
    ret_12m: null,
    ret_1d: null,
    rs_pctile_1w: null,
    rs_pctile_1m: null,
    vol_ratio_63: null,
    max_drawdown_252: null,
    volume_expansion: null,
    effort_ratio_63: null,
    ema_20_ratio: null,
    ma_30w_slope_4w: null,
    atr_21: null,
    above_200d_ma: null,
    above_50d_ma: null,
    drawdown: null,
    days_in_state: null,
    history_gate_pass: true,
    liquidity_gate_pass: true,
    strength_gate: true,
    direction_gate: true,
    risk_gate: true,
    volume_gate: true,
    sector_gate: true,
    market_gate: true,
    rs_state: 'Leader',
    momentum_state: 'Accelerating',
    risk_state: 'Low',
    volume_state: null,
    is_investable: true,
    engine_state: 'stage_2a',
    within_state_rank: 0.9,
    rs_rank_12m: 0.85,
    dwell_days: 12,
    urgency_score: null,
    alpha_3m: null,
    alpha_6m: null,
    // StockRow base fields
    rs_3m_nifty500: null,
    rs_3m_tier_gold: null,
    position_size_pct: null,
    ...overrides,
  }
}

const bankingStocks = [
  makeStockRow({ instrument_id: 'i1', symbol: 'HDFC', sector: 'Banking' }),
  makeStockRow({ instrument_id: 'i2', symbol: 'ICICI', sector: 'Banking' }),
]

// ---------------------------------------------------------------------------
// Tests: sector filter banner
// ---------------------------------------------------------------------------

describe('StockScreener — initialSectorFilter prop', () => {
  it('shows "Filtering: Banking" banner when initialSectorFilter is Banking', () => {
    render(
      <StockScreener
        stocks={bankingStocks}
        initialSectorFilter="Banking"
      />
    )
    expect(screen.getByTestId('sector-filter-banner')).toBeInTheDocument()
    expect(screen.getByTestId('sector-filter-banner')).toHaveTextContent('Banking')
  })

  it('shows a clear-filter link (✕) in the sector banner', () => {
    render(
      <StockScreener
        stocks={bankingStocks}
        initialSectorFilter="Banking"
      />
    )
    // The clear link should navigate to /stocks
    const clearLink = screen.getByTestId('sector-filter-clear')
    expect(clearLink).toBeInTheDocument()
    expect(clearLink).toHaveAttribute('href', '/stocks')
  })

  it('does NOT show sector banner when no initialSectorFilter', () => {
    render(<StockScreener stocks={bankingStocks} />)
    expect(screen.queryByTestId('sector-filter-banner')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Tests: index filter banner
// ---------------------------------------------------------------------------

describe('StockScreener — initialIndexFilter prop', () => {
  it('shows "Filtering: Nifty 50" banner when initialIndexFilter is Nifty 50', () => {
    render(
      <StockScreener
        stocks={bankingStocks}
        initialIndexFilter="Nifty 50"
      />
    )
    expect(screen.getByTestId('index-filter-banner')).toBeInTheDocument()
    expect(screen.getByTestId('index-filter-banner')).toHaveTextContent('Nifty 50')
  })

  it('shows a clear-filter link (✕) in the index banner linking to /stocks', () => {
    render(
      <StockScreener
        stocks={bankingStocks}
        initialIndexFilter="Nifty 100"
      />
    )
    const clearLink = screen.getByTestId('index-filter-clear')
    expect(clearLink).toHaveAttribute('href', '/stocks')
  })

  it('does NOT show index banner when no initialIndexFilter', () => {
    render(<StockScreener stocks={bankingStocks} />)
    expect(screen.queryByTestId('index-filter-banner')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Tests: StockDeepDiveHeader IndexBadge linking (Part B)
// ---------------------------------------------------------------------------

import { StockDeepDiveHeader } from '../StockDeepDiveHeader'

function makeFullStockRow(overrides: Partial<StockRowWithSector> = {}): StockRowWithSector {
  return {
    ...makeStockRow(),
    // StockDeepDiveHeader also uses position_size_pct — present in StockRow
    ...overrides,
  }
}

describe('StockDeepDiveHeader — IndexBadge links', () => {
  it('renders Nifty 50 badge as a link to /stocks?index=Nifty%2050', () => {
    render(<StockDeepDiveHeader stock={makeFullStockRow({ in_nifty_50: true })} />)
    const link = screen.getByRole('link', { name: /Nifty 50/i })
    expect(link).toHaveAttribute('href', '/stocks?index=Nifty%2050')
  })

  it('renders Nifty 100 badge as a link to /stocks?index=Nifty%20100 when not in Nifty 50', () => {
    render(
      <StockDeepDiveHeader stock={makeFullStockRow({ in_nifty_50: false, in_nifty_100: true })} />
    )
    const link = screen.getByRole('link', { name: /Nifty 100/i })
    expect(link).toHaveAttribute('href', '/stocks?index=Nifty%20100')
  })

  it('renders Nifty 500 badge as a link when not in Nifty 50 or 100', () => {
    render(
      <StockDeepDiveHeader
        stock={makeFullStockRow({ in_nifty_50: false, in_nifty_100: false, in_nifty_500: true })}
      />
    )
    const link = screen.getByRole('link', { name: /Nifty 500/i })
    expect(link).toHaveAttribute('href', '/stocks?index=Nifty%20500')
  })

  it('renders no index badge link when stock is not in any index', () => {
    render(
      <StockDeepDiveHeader
        stock={makeFullStockRow({ in_nifty_50: false, in_nifty_100: false, in_nifty_500: false })}
      />
    )
    expect(screen.queryByRole('link', { name: /Nifty/i })).not.toBeInTheDocument()
  })
})
