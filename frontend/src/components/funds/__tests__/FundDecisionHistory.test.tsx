import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundDecisionHistory } from '../FundDecisionHistory'
import type { FundDecisionRow } from '@/lib/queries/funds'

const ROW: FundDecisionRow = {
  date: new Date('2026-04-30'),
  recommendation: 'Recommended',
  entry_trigger: true,
  exit_trigger: false,
  reduce_trigger: false,
  performance_gate: true,
  sectors_gate: true,
  stocks_gate: true,
  market_gate: true,
  weeks_in_current_state: '12',
}

describe('FundDecisionHistory', () => {
  it('renders empty state when no decisions', () => {
    render(<FundDecisionHistory decisions={[]} />)
    expect(screen.getByText(/No decision history available/)).toBeInTheDocument()
  })

  it('renders all column headers', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    for (const h of ['DATE', 'RECOMMENDATION', 'ENTRY', 'EXIT', 'REDUCE', 'WEEKS']) {
      expect(screen.getByText(h)).toBeInTheDocument()
    }
  })

  it('renders date in DD-MMM-YYYY format', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    expect(screen.getByText('30-Apr-2026')).toBeInTheDocument()
  })

  it('renders recommendation value', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    expect(screen.getByText('Recommended')).toBeInTheDocument()
  })

  it('renders bullet for active triggers and blank for inactive', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    // entry_trigger=true → bullet appears
    expect(screen.getAllByText('●').length).toBe(1)
  })

  it('renders em-dash for null recommendation and null weeks', () => {
    const r: FundDecisionRow = {
      ...ROW,
      recommendation: null,
      weeks_in_current_state: null,
    }
    render(<FundDecisionHistory decisions={[r]} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })
})
