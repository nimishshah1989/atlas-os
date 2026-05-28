// frontend/src/components/v6/calls/__tests__/WinRateMatrix.test.tsx
//
// Tests for the tier × tenure × direction win-rate matrix.
// Updated to use real hit_rate + avg_realized_excess from mv_calls_performance.
//
// Test cases:
//   1. Renders tier row labels (Large, Mid, Small)
//   2. Renders tenure column headers (1m, 3m, 6m, 12m)
//   3. Renders POS/NEG direction sub-headers
//   4. Formats hit_rate as integer percentage
//   5. Shows — for cells with no data
//   6. Renders call count (n=X) in each cell
//   7. Legend renders with win rate labels

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WinRateMatrix } from '../WinRateMatrix'
import type { WinRateCell } from '@/lib/queries/v6/calls'

const MATRIX: WinRateCell[] = [
  {
    cap_tier: 'Large',
    tenure: '6m',
    action: 'POSITIVE',
    call_count: 98,
    hit_rate: 0.72,
    avg_realized_excess: 0.084,
  },
  {
    cap_tier: 'Large',
    tenure: '12m',
    action: 'POSITIVE',
    call_count: 84,
    hit_rate: 0.81,
    avg_realized_excess: 0.088,
  },
  {
    cap_tier: 'Mid',
    tenure: '6m',
    action: 'NEGATIVE',
    call_count: 94,
    hit_rate: 0.55,
    avg_realized_excess: 0.032,
  },
  {
    cap_tier: 'Small',
    tenure: '12m',
    action: 'NEGATIVE',
    call_count: 186,
    hit_rate: 0.25,
    avg_realized_excess: -0.012,
  },
]

describe('WinRateMatrix', () => {
  it('renders tier row labels', () => {
    render(<WinRateMatrix cells={MATRIX} />)
    expect(screen.getByText('Large')).toBeInTheDocument()
    expect(screen.getByText('Mid')).toBeInTheDocument()
    expect(screen.getByText('Small')).toBeInTheDocument()
  })

  it('renders tenure column headers', () => {
    render(<WinRateMatrix cells={MATRIX} />)
    expect(screen.getAllByText('1m').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('6m').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('12m').length).toBeGreaterThanOrEqual(1)
  })

  it('renders POS and NEG direction sub-headers', () => {
    render(<WinRateMatrix cells={MATRIX} />)
    const posHeaders = screen.getAllByText('POS')
    const negHeaders = screen.getAllByText('NEG')
    expect(posHeaders.length).toBeGreaterThanOrEqual(4)
    expect(negHeaders.length).toBeGreaterThanOrEqual(4)
  })

  it('formats hit_rate as integer percentage', () => {
    render(<WinRateMatrix cells={MATRIX} />)
    // 0.72 → 72%
    expect(screen.getByText('72%')).toBeInTheDocument()
    // 0.81 → 81%
    expect(screen.getByText('81%')).toBeInTheDocument()
  })

  it('shows — for cells with no data', () => {
    render(<WinRateMatrix cells={[]} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('shows call count n= for populated cells', () => {
    render(<WinRateMatrix cells={MATRIX} />)
    expect(screen.getByText('n=98')).toBeInTheDocument()
    expect(screen.getByText('n=186')).toBeInTheDocument()
  })

  it('renders the legend with win rate scale', () => {
    render(<WinRateMatrix cells={MATRIX} />)
    expect(screen.getByText(/win rate scale/i)).toBeInTheDocument()
  })
})
