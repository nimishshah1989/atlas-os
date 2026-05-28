import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FundDecisionHistory } from '../FundDecisionHistory'
import type { FundDecisionRow } from '@/lib/queries/funds'

const ROW: FundDecisionRow = {
  date: new Date('2026-04-30'),
  recommendation: 'Recommended',
  entry_trigger: false,
  exit_trigger: false,
  reduce_trigger: false,
  add_trigger: false,
  performance_gate: true,
  sectors_gate: true,
  stocks_gate: false,
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
    for (const h of ['Date', 'Rating', 'Entry', 'Exit', 'Reduce', 'Add', 'Performance', 'Sectors', 'Holdings', 'Market', 'In State']) {
      expect(screen.getByText(h)).toBeInTheDocument()
    }
  })

  it('renders group header labels', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    expect(screen.getByText(/Rating Change Triggers/i)).toBeInTheDocument()
    expect(screen.getByText(/Quality Gates/i)).toBeInTheDocument()
  })

  it('renders date in DD-MMM-YYYY format', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    expect(screen.getByText('30-Apr-2026')).toBeInTheDocument()
  })

  it('renders recommendation value in rating cell', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    expect(screen.getAllByText('Recommended').length).toBeGreaterThanOrEqual(1)
  })

  it('shows gate pass (✓) and fail (✗) symbols', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    // performance=true, sectors=true, market=true → 3 passes; stocks=false → 1 fail
    expect(screen.getAllByText('✓').length).toBe(3)
    expect(screen.getAllByText('✗').length).toBe(1)
  })

  it('inactive triggers render as em-dash', () => {
    render(<FundDecisionHistory decisions={[ROW]} />)
    // all 4 triggers are false → 4 dashes in trigger cells, plus recommendation dash when null
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBe(4) // 4 inactive triggers
  })

  it('active entry trigger renders Entry badge', () => {
    const r: FundDecisionRow = { ...ROW, entry_trigger: true }
    render(<FundDecisionHistory decisions={[r]} />)
    // The badge text "Entry" appears; column header also says "Entry" → getAllByText
    const entries = screen.getAllByText('Entry')
    expect(entries.length).toBe(2) // header + badge
  })

  it('renders em-dash for null recommendation', () => {
    const r: FundDecisionRow = { ...ROW, recommendation: null }
    render(<FundDecisionHistory decisions={[r]} />)
    // 4 trigger dashes + 1 null recommendation dash = 5
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(5)
  })

  it('shows null gate as ? symbol', () => {
    const r: FundDecisionRow = { ...ROW, performance_gate: null }
    render(<FundDecisionHistory decisions={[r]} />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('formats weeks_in_current_state using formatWeeksInState', () => {
    const r: FundDecisionRow = { ...ROW, weeks_in_current_state: '963' }
    render(<FundDecisionHistory decisions={[r]} />)
    expect(screen.getByText('52+')).toBeInTheDocument()
  })
})
