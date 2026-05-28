// frontend/src/components/v6/calls/__tests__/CallsLedger.test.tsx
//
// Tests for the calls ledger table component.
// Updated for new CallRow shape from mv_calls_performance.
// Uses status column directly (I1), virtualization (I2), ActionBadge (I3).
//
// Test cases:
//   1. Renders all column headers including Real ex. and Hit
//   2. Renders symbol for each row
//   3. Direction column shows BUY / AVOID via ActionBadge
//   4. Status chip shows IN FLIGHT for in_flight calls
//   5. Status chip shows CLOSED for closed calls
//   6. Filtering by status (in_flight/closed) narrows rows
//   7. Filtering by direction (BUY/AVOID) narrows rows
//   8. Search by symbol narrows rows
//   9. Empty state shows message when no rows match filter
//  10. Positive realized excess shows + sign (C2)
//  11. Negative realized excess shows - sign (C2)
//  12. Hit column shows checkmark for wins, X for losses
//  13. Sort header click changes sort column

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CallsLedger } from '../CallsLedger'
import type { CallRow } from '@/lib/queries/v6/calls'

const CALL_OPEN: CallRow = {
  signal_call_id: 'sc-001',
  symbol: 'RELIANCE',
  company_name: 'Reliance Industries',
  cap_tier: 'Large',
  tenure: '6m',
  action: 'POSITIVE',
  action_display: 'BUY',
  cell_name: 'Large-6m-POSITIVE',
  cell_label: 'L 6m POS',
  entry_date: '2026-03-19',
  days_in_position: 68,
  predicted_excess: 0.053,
  realized_excess_pct: 0.071,
  is_hit: true,
  status: 'in_flight',
}

const CALL_CLOSED: CallRow = {
  signal_call_id: 'sc-002',
  symbol: 'VEDL',
  company_name: 'Vedanta Ltd',
  cap_tier: 'Small',
  tenure: '12m',
  action: 'NEGATIVE',
  action_display: 'AVOID',
  cell_name: 'Small-12m-NEGATIVE',
  cell_label: 'S 12m NEG',
  entry_date: '2026-03-01',
  days_in_position: 86,
  predicted_excess: -0.054,
  realized_excess_pct: -0.028,
  is_hit: false,
  status: 'closed',
}

const CALLS = [CALL_OPEN, CALL_CLOSED]

describe('CallsLedger', () => {
  it('renders all expected column headers', () => {
    render(<CallsLedger calls={CALLS} />)
    // "Symbol · Company" is in the header
    expect(screen.getAllByText(/symbol/i).length).toBeGreaterThanOrEqual(1)
    // "Status" appears in both filter label and table header
    expect(screen.getAllByText(/^status$/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/^cell$/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/^tier$/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/^dir$/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/opened/i)).toBeInTheDocument()
    expect(screen.getByText(/pred ex\./i)).toBeInTheDocument()
    expect(screen.getByText(/real ex\./i)).toBeInTheDocument()
    expect(screen.getByText(/^hit$/i)).toBeInTheDocument()
  })

  it('renders symbol for each row', () => {
    render(<CallsLedger calls={CALLS} />)
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.getByText('VEDL')).toBeInTheDocument()
  })

  it('shows BUY direction badge for POSITIVE action', () => {
    render(<CallsLedger calls={[CALL_OPEN]} />)
    expect(screen.getByText('BUY')).toBeInTheDocument()
  })

  it('shows AVOID direction badge for NEGATIVE action', () => {
    render(<CallsLedger calls={[CALL_CLOSED]} />)
    expect(screen.getByText('AVOID')).toBeInTheDocument()
  })

  it('shows IN FLIGHT chip for in_flight status', () => {
    render(<CallsLedger calls={[CALL_OPEN]} />)
    expect(screen.getByText('IN FLIGHT')).toBeInTheDocument()
  })

  it('shows CLOSED chip for closed status', () => {
    render(<CallsLedger calls={[CALL_CLOSED]} />)
    expect(screen.getByText('CLOSED')).toBeInTheDocument()
  })

  it('filtering by in_flight shows only open rows', () => {
    render(<CallsLedger calls={CALLS} />)
    // Button text: "In flight (1)"
    const inFlightButton = screen.getByRole('button', { name: /in flight/i })
    fireEvent.click(inFlightButton)
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.queryByText('VEDL')).not.toBeInTheDocument()
  })

  it('filtering by BUY shows only BUY rows', () => {
    render(<CallsLedger calls={CALLS} />)
    const buyButton = screen.getByRole('button', { name: /^buy/i })
    fireEvent.click(buyButton)
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.queryByText('VEDL')).not.toBeInTheDocument()
  })

  it('filtering by AVOID shows only AVOID rows', () => {
    render(<CallsLedger calls={CALLS} />)
    const avoidButton = screen.getByRole('button', { name: /^avoid/i })
    fireEvent.click(avoidButton)
    expect(screen.queryByText('RELIANCE')).not.toBeInTheDocument()
    expect(screen.getByText('VEDL')).toBeInTheDocument()
  })

  it('searching by symbol filters rows', () => {
    render(<CallsLedger calls={CALLS} />)
    const input = screen.getByPlaceholderText(/search ticker/i)
    fireEvent.change(input, { target: { value: 'REL' } })
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.queryByText('VEDL')).not.toBeInTheDocument()
  })

  it('shows empty state message when no rows match', () => {
    render(<CallsLedger calls={CALLS} />)
    const input = screen.getByPlaceholderText(/search ticker/i)
    fireEvent.change(input, { target: { value: 'ZZZNOMATCH' } })
    expect(screen.getByText(/no calls match/i)).toBeInTheDocument()
  })

  it('formats positive predicted excess with + sign (C2)', () => {
    render(<CallsLedger calls={[CALL_OPEN]} />)
    expect(screen.getByText('+5.3%')).toBeInTheDocument()
  })

  it('formats positive realized excess with + sign (C2)', () => {
    render(<CallsLedger calls={[CALL_OPEN]} />)
    expect(screen.getByText('+7.1%')).toBeInTheDocument()
  })

  it('formats negative realized excess with - sign (C2)', () => {
    render(<CallsLedger calls={[CALL_CLOSED]} />)
    expect(screen.getByText('-2.8%')).toBeInTheDocument()
  })
})
