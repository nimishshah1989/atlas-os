/**
 * Task 1.6 — ETF cross-link tests
 * Verifies: ETFHoldingsTab stock → <LinkedTicker>, sector → <LinkedSector>
 *           ETFScreener linked_sector → <LinkedSector>
 *           ETFDeepDiveHeader linked_sector → <LinkedSector>
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ETFHoldingsTab } from '../ETFHoldingsTab'
import { ETFScreener } from '../ETFScreener'
import { ETFDeepDiveHeader } from '../ETFDeepDiveHeader'
import type { ETFHoldingRow } from '@/lib/queries/etfs'
import type { ETFRow } from '@/lib/queries/etfs'

function makeHolding(overrides: Partial<ETFHoldingRow> = {}): ETFHoldingRow {
  return {
    symbol: 'HDFCBANK',
    company_name: 'HDFC Bank',
    weight: '0.10',
    sector: 'Financial Services',
    rs_state: 'Strong',
    momentum_state: 'Improving',
    risk_state: 'Normal',
    ret_1m: '0.02',
    ret_3m: '0.05',
    holdings_date: '2026-04-30',
    ...overrides,
  }
}

function makeETFRow(overrides: Partial<ETFRow> = {}): ETFRow {
  return {
    ticker: 'BANKBEES',
    etf_name: 'Bank BeES',
    theme: 'Sectoral',
    linked_sector: 'Financial Services',
    linked_index: 'Nifty Bank',
    inception_date: '2003-01-01',
    asset_class: 'Equity',
    fund_house: 'Nippon',
    data_as_of: '2026-05-18',
    ret_1w: '0.01',
    ret_1m: '0.02',
    ret_3m: '0.05',
    ret_6m: '0.10',
    ret_12m: '0.18',
    rs_pctile_3m: '0.70',
    rs_3m_benchmark: '0.02',
    ema_10_ratio: '1.01',
    extension_pct: '0.04',
    vol_63: '0.14',
    drawdown: '-0.05',
    volume_expansion: '1.1',
    avg_volume_20: '500000',
    effort_ratio_63: '1.0',
    above_30w_ma: true,
    ema_10_at_20d_high: true,
    days_in_state: null,
    rs_state: 'Strong',
    momentum_state: 'Improving',
    risk_state: 'Normal',
    weinstein_gate_pass: true,
    history_gate_pass: true,
    liquidity_gate_pass: true,
    is_investable: true,
    strength_gate: true,
    direction_gate: true,
    risk_gate: true,
    sector_gate: true,
    market_gate: true,
    position_size_pct: null,
    breakout_trigger: false,
    transition_trigger: false,
    exit_market_riskoff: null,
    exit_sector_avoid: null,
    exit_rs_deteriorate: null,
    exit_momentum_collapse: null,
    exit_stop_loss: null,
    mean_rs_rank_12m: 0.70,
    mean_within_state_rank: null,
    pct_stage_2: null,
    pct_stage_4: null,
    engine_state: null,
    ...overrides,
  }
}

describe('ETFHoldingsTab — cross-link tokens', () => {
  it('renders stock symbol as a link to /stocks/[symbol]', () => {
    render(<ETFHoldingsTab holdings={[makeHolding()]} />)
    const link = screen.getByRole('link', { name: 'HDFCBANK' })
    expect(link).toHaveAttribute('href', '/stocks/HDFCBANK')
  })

  it('renders sector as a link to /sectors/[sector]', () => {
    render(<ETFHoldingsTab holdings={[makeHolding()]} />)
    const link = screen.getByRole('link', { name: 'Financial Services' })
    expect(link).toHaveAttribute('href', '/sectors/Financial%20Services')
  })

  it('renders em-dash (not a link) when symbol is null', () => {
    render(<ETFHoldingsTab holdings={[makeHolding({ symbol: null })]} />)
    expect(screen.queryByRole('link', { name: 'HDFCBANK' })).not.toBeInTheDocument()
  })

  it('renders em-dash (not a link) when sector is null', () => {
    render(<ETFHoldingsTab holdings={[makeHolding({ sector: null })]} />)
    expect(screen.queryByRole('link', { name: 'Financial Services' })).not.toBeInTheDocument()
  })
})

describe('ETFScreener — linked_sector is a LinkedSector link', () => {
  beforeEach(() => localStorage.clear())

  it('renders linked_sector as a link to /sectors/[sector]', () => {
    render(<ETFScreener etfs={[makeETFRow()]} validations={[]} />)
    const link = screen.getByRole('link', { name: 'Financial Services' })
    expect(link).toHaveAttribute('href', '/sectors/Financial%20Services')
  })

  it('does not render a sector link when linked_sector is null', () => {
    render(<ETFScreener etfs={[makeETFRow({ linked_sector: null })]} validations={[]} />)
    expect(screen.queryByRole('link', { name: 'Financial Services' })).not.toBeInTheDocument()
  })
})

describe('ETFDeepDiveHeader — linked_sector is a LinkedSector link', () => {
  it('renders linked_sector as a link to /sectors/[sector]', () => {
    render(<ETFDeepDiveHeader etf={makeETFRow()} />)
    const link = screen.getByRole('link', { name: 'Financial Services' })
    expect(link).toHaveAttribute('href', '/sectors/Financial%20Services')
  })

  it('does not render sector link when linked_sector is null', () => {
    render(<ETFDeepDiveHeader etf={makeETFRow({ linked_sector: null })} />)
    expect(screen.queryByRole('link', { name: 'Financial Services' })).not.toBeInTheDocument()
  })
})
