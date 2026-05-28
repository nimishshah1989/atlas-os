// frontend/src/components/v6/calls/__tests__/SixCellCards.test.tsx
//
// Tests for the six-cell cards section.
// Updated for new TopSixResult prop shape ({best, worst}) — C3.
// Uses realized hit_rate and avg_realized_excess from mv_calls_performance.
//
// Test cases:
//   1. Renders BEST tag for best cells
//   2. Renders WORST tag for worst cells
//   3. Shows cell_label via LinkedCell in each card
//   4. Shows ActionBadge (BUY/AVOID direction)
//   5. Shows win rate and realized excess
//   6. Shows call count and in-flight count
//   7. Empty state renders without error

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SixCellCards } from '../SixCellCards'
import type { TopSixResult } from '@/lib/queries/v6/calls'

const BEST_CELLS = [
  {
    cell_name: 'Large-6m-POSITIVE',
    cell_label: 'L 6m POS',
    cap_tier: 'Large',
    tenure: '6m',
    action: 'POSITIVE',
    action_display: 'BUY',
    call_count: 98,
    hit_rate: 0.92,
    avg_realized_excess: 0.084,
    avg_predicted_excess: 0.075,
    in_flight_count: 82,
  },
  {
    cell_name: 'Small-12m-NEGATIVE',
    cell_label: 'S 12m NEG',
    cap_tier: 'Small',
    tenure: '12m',
    action: 'NEGATIVE',
    action_display: 'AVOID',
    call_count: 186,
    hit_rate: 0.78,
    avg_realized_excess: 0.072,
    avg_predicted_excess: 0.068,
    in_flight_count: 142,
  },
  {
    cell_name: 'Large-12m-POSITIVE',
    cell_label: 'L 12m POS',
    cap_tier: 'Large',
    tenure: '12m',
    action: 'POSITIVE',
    action_display: 'BUY',
    call_count: 84,
    hit_rate: 0.67,
    avg_realized_excess: 0.058,
    avg_predicted_excess: 0.060,
    in_flight_count: 62,
  },
]

const WORST_CELLS = [
  {
    cell_name: 'Mid-6m-NEGATIVE',
    cell_label: 'M 6m NEG',
    cap_tier: 'Mid',
    tenure: '6m',
    action: 'NEGATIVE',
    action_display: 'AVOID',
    call_count: 94,
    hit_rate: 0.32,
    avg_realized_excess: -0.018,
    avg_predicted_excess: 0.010,
    in_flight_count: 68,
  },
  {
    cell_name: 'Small-3m-POSITIVE',
    cell_label: 'S 3m POS',
    cap_tier: 'Small',
    tenure: '3m',
    action: 'POSITIVE',
    action_display: 'BUY',
    call_count: 52,
    hit_rate: 0.25,
    avg_realized_excess: -0.031,
    avg_predicted_excess: 0.012,
    in_flight_count: 42,
  },
  {
    cell_name: 'Large-1m-NEGATIVE',
    cell_label: 'L 1m NEG',
    cap_tier: 'Large',
    tenure: '1m',
    action: 'NEGATIVE',
    action_display: 'AVOID',
    call_count: 18,
    hit_rate: 0.28,
    avg_realized_excess: -0.045,
    avg_predicted_excess: -0.004,
    in_flight_count: 14,
  },
]

const TOP_SIX: TopSixResult = {
  best: BEST_CELLS,
  worst: WORST_CELLS,
}

describe('SixCellCards', () => {
  it('renders BEST tags for top cells', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    const bestTags = screen.getAllByText('BEST')
    expect(bestTags.length).toBe(3)
  })

  it('renders WORST tags for bottom cells', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    const worstTags = screen.getAllByText('WORST')
    expect(worstTags.length).toBe(3)
  })

  it('renders cell_label in each card', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    expect(screen.getAllByText(/L 6m POS/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/S 12m NEG/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows BUY direction badge via ActionBadge', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    const buyTags = screen.getAllByText('BUY')
    expect(buyTags.length).toBeGreaterThanOrEqual(1)
  })

  it('shows AVOID direction badge via ActionBadge', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    const avoidTags = screen.getAllByText('AVOID')
    expect(avoidTags.length).toBeGreaterThanOrEqual(1)
  })

  it('shows win rate in card metrics', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    // 0.92 hit_rate → 92.0%
    expect(screen.getByText('92.0%')).toBeInTheDocument()
  })

  it('shows realized excess with sign in card metrics', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    // 0.084 realized → +8.4%
    expect(screen.getByText('+8.4%')).toBeInTheDocument()
    // -0.045 → -4.5%
    expect(screen.getByText('-4.5%')).toBeInTheDocument()
  })

  it('shows call count for each cell', () => {
    render(<SixCellCards topSix={TOP_SIX} />)
    expect(screen.getByText(/n=98/i)).toBeInTheDocument()
  })

  it('renders empty state without crashing when both arrays empty', () => {
    render(<SixCellCards topSix={{ best: [], worst: [] }} />)
    expect(screen.getByText(/no cell data/i)).toBeInTheDocument()
  })
})
