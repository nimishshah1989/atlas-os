/**
 * Task 1.6 — Sector cross-link tests
 * Verifies that stock symbols in sector tables use <LinkedTicker> (real hrefs),
 * sector chips use <LinkedSector>, and SectorDecisionTable leader symbols are linked.
 * Wave-1 B1 — SectorStocksTab renders a link to the pre-filtered screener.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StocksTable } from '../StocksTable'
import { TopPicksCallout } from '../TopPicksCallout'
import { SectorDecisionTable } from '../SectorDecisionTable'
import { SectorStocksTab } from '../SectorStocksTab'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

// SectorDecisionTable imports a 'use server' action — mock to avoid module resolution error in jsdom
vi.mock('@/app/sectors/actions', () => ({
  getTopPicksAction: vi.fn().mockResolvedValue([]),
}))

function makeStockRow(overrides: Partial<StockRow> = {}): StockRow {
  return {
    instrument_id: 'inst-1',
    symbol: 'RELIANCE',
    company_name: 'Reliance Industries',
    rs_state: 'Overweight_RS',
    momentum_state: 'Improving',
    risk_state: 'Low',
    ret_1m: '0.03',
    ret_3m: '0.07',
    ret_6m: '0.12',
    rs_3m_nifty500: '0.05',
    rs_3m_tier_gold: null,
    rs_pctile_3m: '0.80',
    position_size_pct: '1.0',
    ema_10_at_20d_high: true,
    weinstein_gate_pass: true,
    is_investable: true,
    market_gate: true,
    sector_gate: true,
    strength_gate: true,
    direction_gate: true,
    risk_gate: true,
    in_nifty_50: true,
    in_nifty_100: true,
    in_nifty_500: true,
    ...overrides,
  }
}

describe('SectorStocksTab — sector→screener handoff link (B1)', () => {
  it('renders a link with href /stocks?sector=<encoded name>', () => {
    render(
      <SectorStocksTab
        sectorName="Financial Services"
        stocks={[makeStockRow()]}
        range="3M"
        regime={null}
      />,
    )
    const link = screen.getByRole('link', { name: /Financial Services.*screener|screener.*Financial Services|View all.*Financial Services|Financial Services.*stocks/i })
    expect(link).toHaveAttribute('href', '/stocks?sector=Financial%20Services')
  })

  it('encodes special characters in sector name', () => {
    render(
      <SectorStocksTab
        sectorName="Oil & Gas"
        stocks={[makeStockRow()]}
        range="3M"
        regime={null}
      />,
    )
    const link = screen.getByRole('link', { name: /Oil.*Gas.*screener|screener.*Oil.*Gas|View all.*Oil|Oil.*Gas.*stocks/i })
    expect(link).toHaveAttribute('href', '/stocks?sector=Oil%20%26%20Gas')
  })
})

describe('StocksTable — LinkedTicker for stock symbols', () => {
  it('renders stock symbol as a link to /stocks/[symbol]', () => {
    render(<StocksTable stocks={[makeStockRow()]} unit="inr" />)
    const link = screen.getByRole('link', { name: 'RELIANCE' })
    expect(link).toHaveAttribute('href', '/stocks/RELIANCE')
  })

  it('renders multiple stock rows each as links', () => {
    const stocks = [
      makeStockRow({ instrument_id: 'i1', symbol: 'RELIANCE' }),
      makeStockRow({ instrument_id: 'i2', symbol: 'INFY' }),
    ]
    render(<StocksTable stocks={stocks} unit="inr" />)
    const relianceLink = screen.getByRole('link', { name: 'RELIANCE' })
    const infyLink = screen.getByRole('link', { name: 'INFY' })
    expect(relianceLink).toHaveAttribute('href', '/stocks/RELIANCE')
    expect(infyLink).toHaveAttribute('href', '/stocks/INFY')
  })
})

describe('TopPicksCallout — LinkedTicker for top-pick symbols', () => {
  it('renders investable pick symbol as a link to /stocks/[symbol]', () => {
    render(<TopPicksCallout stocks={[makeStockRow()]} />)
    const link = screen.getByRole('link', { name: 'RELIANCE' })
    expect(link).toHaveAttribute('href', '/stocks/RELIANCE')
  })

  it('renders em-dash (no link) when no investable picks', () => {
    // A non-investable stock should NOT produce a link in TopPicksCallout picks section
    render(<TopPicksCallout stocks={[makeStockRow({ is_investable: false })]} />)
    expect(screen.queryByRole('link', { name: 'RELIANCE' })).not.toBeInTheDocument()
  })
})

describe('SectorDecisionTable — LinkedTicker for leader chips', () => {
  const minimalRow = {
    sector_name: 'Technology',
    constituent_count: 20,
    bottomup_ret_1w: null,
    bottomup_ret_1m: null,
    bottomup_ret_3m: null,
    bottomup_ret_6m: null,
    bottomup_rs_3m_nifty500: null,
    rs_momentum: null,
    participation_50: null,
    leadership_concentration: null,
    sector_state: 'Overweight',
    bottomup_momentum_state: null,
    bottomup_rs_state: null,
    bottomup_ema_10_ratio: null,
    bottomup_ema_20_ratio: null,
    topdown_rs_3m_nifty500: null,
    divergence_flag: false,
    decision: 'HOLD' as const,
    days_in_state: 5,
  }

  it('renders top_symbols chip as an anchor with /stocks/[symbol] href', () => {
    render(
      <SectorDecisionTable
        data={[minimalRow]}
        onSelect={() => undefined}
        leadingRRGCount={0}
        leadersBySector={{
          Technology: { leader_count: 2, top_symbols: ['INFY', 'TCS'] },
        }}
      />
    )
    const infyLink = screen.getByRole('link', { name: 'INFY' })
    expect(infyLink).toHaveAttribute('href', '/stocks/INFY')
  })
})
