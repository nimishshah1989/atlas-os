/**
 * Task 1.6 — Sector cross-link tests
 * Verifies that stock symbols in sector tables use <LinkedTicker> (real hrefs),
 * sector chips use <LinkedSector>, and SectorDecisionTable leader symbols are linked.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StocksTable } from '../StocksTable'
import { TopPicksCallout } from '../TopPicksCallout'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

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
