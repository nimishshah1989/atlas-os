// frontend/src/components/v6/__tests__/RecentSignalCalls.test.tsx
//
// 5 test cases:
//   1. Empty state renders "No signal_calls in the last 7 days"
//   2. Rows render with ticker, cell_name, action pill
//   3. Each row links to /v6/stocks/[instrument_id]
//   4. Confidence displays as percentage (string Decimal → %)
//   5. Sort header click toggles sort direction

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RecentSignalCalls } from '../RecentSignalCalls'
import type { SignalCallEvent } from '@/lib/queries/v6/recent_signal_calls'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CALL_1: SignalCallEvent = {
  signal_call_id: 'sc-001',
  cell_id: 'cell-mid-12m',
  cell_name: 'Mid 12m POSITIVE',
  instrument_id: 'iid-reliance',
  ticker: 'RELIANCE',
  action: 'POSITIVE',
  cap_tier: 'Large',
  tenure: '12m',
  entry_date: '2026-05-26',
  entry_price: null,
  confidence_unconditional: '0.82',
  predicted_excess: '0.04',
  exit_date: null,
  is_active: true,
}

const CALL_2: SignalCallEvent = {
  signal_call_id: 'sc-002',
  cell_id: 'cell-small-3m',
  cell_name: 'Small 3m NEGATIVE',
  instrument_id: 'iid-tcs',
  ticker: 'TCS',
  action: 'NEGATIVE',
  cap_tier: 'Large',
  tenure: '3m',
  entry_date: '2026-05-25',
  entry_price: null,
  confidence_unconditional: '0.65',
  predicted_excess: null,
  exit_date: null,
  is_active: true,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RecentSignalCalls', () => {
  it('renders empty-state message when calls array is empty', () => {
    render(<RecentSignalCalls calls={[]} />)
    expect(screen.getByText(/no signal_calls in the last 7 days/i)).toBeInTheDocument()
  })

  it('renders ticker and cell name for each call', () => {
    render(<RecentSignalCalls calls={[CALL_1, CALL_2]} />)
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    expect(screen.getByText('TCS')).toBeInTheDocument()
    expect(screen.getByText('Mid 12m POSITIVE')).toBeInTheDocument()
    expect(screen.getByText('Small 3m NEGATIVE')).toBeInTheDocument()
  })

  it('each ticker row links to /v6/stocks/[instrument_id]', () => {
    render(<RecentSignalCalls calls={[CALL_1]} />)
    const link = screen.getByRole('link', { name: /view stock RELIANCE/i })
    expect(link).toHaveAttribute('href', '/v6/stocks/iid-reliance')
  })

  it('displays confidence as rounded percentage', () => {
    render(<RecentSignalCalls calls={[CALL_1]} />)
    // 0.82 → 82%
    expect(screen.getByText('82%')).toBeInTheDocument()
  })

  it('clicking a sort header toggles sort direction indicator', () => {
    render(<RecentSignalCalls calls={[CALL_1, CALL_2]} />)
    // Initial sort is entry_date desc — clicking it should toggle to asc
    const tickerHeader = screen.getByText(/^ticker$/i, { selector: 'th' })
    // Click once to sort by ticker asc
    fireEvent.click(tickerHeader)
    // Should show ascending arrow somewhere in the header
    expect(tickerHeader.textContent).toContain('↓')
    // Click again to toggle
    fireEvent.click(tickerHeader)
    expect(tickerHeader.textContent).toContain('↑')
  })
})
