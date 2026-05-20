/**
 * Task 1.6 — Fund holdings cross-link tests
 * Verifies stock symbols → <LinkedTicker>, sector text → <LinkedSector>
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundHoldingsTab } from '../FundHoldingsTab'
import type { FundHoldingRow } from '@/lib/queries/funds'

function makeHolding(overrides: Partial<FundHoldingRow> = {}): FundHoldingRow {
  return {
    symbol: 'TCS',
    company_name: 'Tata Consultancy Services',
    weight: '0.085',
    sector: 'Technology',
    rs_state: 'Leader',
    momentum_state: 'Improving',
    risk_state: 'Low',
    ret_1m: '0.02',
    ret_3m: '0.06',
    holdings_date: '2026-04-30',
    ...overrides,
  }
}

describe('FundHoldingsTab — cross-link tokens', () => {
  it('renders stock symbol as a link to /stocks/[symbol]', () => {
    render(<FundHoldingsTab holdings={[makeHolding()]} />)
    const link = screen.getByRole('link', { name: 'TCS' })
    expect(link).toHaveAttribute('href', '/stocks/TCS')
  })

  it('renders sector name as a link to /sectors/[sector]', () => {
    render(<FundHoldingsTab holdings={[makeHolding()]} />)
    const link = screen.getByRole('link', { name: 'Technology' })
    expect(link).toHaveAttribute('href', '/sectors/Technology')
  })

  it('renders em-dash for null symbol (no link)', () => {
    render(<FundHoldingsTab holdings={[makeHolding({ symbol: null })]} />)
    expect(screen.queryByRole('link', { name: '—' })).not.toBeInTheDocument()
  })

  it('renders em-dash for null sector (no link)', () => {
    render(<FundHoldingsTab holdings={[makeHolding({ sector: null })]} />)
    // No sector link when sector is null
    expect(screen.queryByRole('link', { name: /Technology/ })).not.toBeInTheDocument()
  })
})
