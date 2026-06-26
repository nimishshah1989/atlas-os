import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LensRankingTable } from '../LensRankingTable'
import type { LensScoreSummary } from '@/lib/queries/lens-scores'

function makeSummary(overrides: Partial<LensScoreSummary> = {}): LensScoreSummary {
  return {
    instrument_id: 'iid-1',
    symbol: 'RELIANCE',
    name: 'Reliance Industries Ltd',
    sector: 'Energy',
    technical: 72,
    fundamental: 65,
    valuation: 45,
    catalyst: 58,
    flow: 80,
    policy: 50,
    composite: 63.5,
    conviction_tier: 'HIGH',
    risk_flags: null,
    ...overrides,
  }
}

describe('LensRankingTable', () => {
  it('renders table headers', () => {
    render(<LensRankingTable scores={[makeSummary()]} />)
    expect(screen.getByText('Symbol')).toBeDefined()
    // "Composite" has sort indicator appended; look for the column header
    expect(screen.getByText(/^Composite/)).toBeDefined()
    expect(screen.getByText('Tech')).toBeDefined()
    expect(screen.getByText(/^Fund/)).toBeDefined()
    expect(screen.getByText('Val')).toBeDefined()
    expect(screen.getByText('Cat')).toBeDefined()
    // "Flow" appears as both a header and lens value
    expect(screen.getAllByText(/^Flow/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Pol')).toBeDefined()
    expect(screen.getByText('Tier')).toBeDefined()
  })

  it('renders stock row with symbol link', () => {
    render(<LensRankingTable scores={[makeSummary()]} />)
    const link = screen.getByRole('link', { name: 'RELIANCE' })
    expect(link.getAttribute('href')).toBe('/stocks/RELIANCE')
  })

  it('renders composite score', () => {
    render(<LensRankingTable scores={[makeSummary()]} />)
    // 63.5 → toFixed(0) = "64"
    expect(screen.getAllByText('64').length).toBeGreaterThanOrEqual(1)
  })

  it('renders conviction tier badge', () => {
    render(<LensRankingTable scores={[makeSummary()]} />)
    // "HIGH" appears both as a tier filter option and in the badge
    expect(screen.getAllByText('HIGH').length).toBeGreaterThanOrEqual(1)
  })

  it('shows risk flag count when present', () => {
    render(<LensRankingTable scores={[makeSummary({ risk_flags: ['auditor_change', 'pledge_spike'] })]} />)
    expect(screen.getByText('2')).toBeDefined()
  })

  it('renders empty state gracefully', () => {
    render(<LensRankingTable scores={[]} />)
    expect(screen.getByText('0 stocks')).toBeDefined()
  })

  it('renders multiple rows', () => {
    const scores = [
      makeSummary({ instrument_id: 'iid-1', symbol: 'RELIANCE' }),
      makeSummary({ instrument_id: 'iid-2', symbol: 'TCS', sector: 'IT', composite: 71 }),
      makeSummary({ instrument_id: 'iid-3', symbol: 'HDFCBANK', sector: 'Finance', composite: 55 }),
    ]
    render(<LensRankingTable scores={scores} />)
    expect(screen.getByText('3 stocks')).toBeDefined()
    expect(screen.getByRole('link', { name: 'RELIANCE' })).toBeDefined()
    expect(screen.getByRole('link', { name: 'TCS' })).toBeDefined()
    expect(screen.getByRole('link', { name: 'HDFCBANK' })).toBeDefined()
  })
})
