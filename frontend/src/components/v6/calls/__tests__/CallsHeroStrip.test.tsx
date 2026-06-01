// frontend/src/components/v6/calls/__tests__/CallsHeroStrip.test.tsx
//
// Tests for the calls hero stats strip.
// Updated to use real avg_realized_excess + overall_hit_rate from mv_calls_performance.
//
// Test cases:
//   1. Renders all 6 tile labels
//   2. Shows correct call counts
//   3. Avg realized excess formats with + sign for positive values
//   4. Avg realized excess formats with - sign for negative values
//   5. Null realized excess shows —
//   6. Win rate renders as percentage
//   7. Data-as-of date displays in footer
//   8. Open foot text is conditional — "All positions currently active" when closed=0

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CallsHeroStrip } from '../CallsHeroStrip'
import type { CallsHero } from '@/lib/queries/v6/calls'

const HERO_FULL: CallsHero = {
  total_calls: 587,
  open_calls: 420,
  closed_calls: 167,
  buy_calls: 342,
  avoid_calls: 245,
  realized_count: 576,
  avg_realized_excess: 0.052,
  overall_hit_rate: 0.68,
  data_as_of: '2026-05-27',
}

const HERO_ALL_OPEN: CallsHero = {
  total_calls: 587,
  open_calls: 587,
  closed_calls: 0,
  buy_calls: 342,
  avoid_calls: 245,
  realized_count: 576,
  avg_realized_excess: null,
  overall_hit_rate: null,
  data_as_of: '2026-05-27',
}

const HERO_NEGATIVE: CallsHero = {
  total_calls: 100,
  open_calls: 60,
  closed_calls: 40,
  buy_calls: 60,
  avoid_calls: 40,
  realized_count: 80,
  avg_realized_excess: -0.031,
  overall_hit_rate: 0.42,
  data_as_of: '2026-05-27',
}

describe('CallsHeroStrip', () => {
  it('renders all 6 tile labels', () => {
    render(<CallsHeroStrip hero={HERO_FULL} />)
    expect(screen.getByText('Total fired')).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('Closed')).toBeInTheDocument()
    expect(screen.getByText('Win rate')).toBeInTheDocument()
    expect(screen.getByText('BUY calls')).toBeInTheDocument()
    expect(screen.getByText('Avg realized ex.')).toBeInTheDocument()
  })

  it('displays correct call counts', () => {
    render(<CallsHeroStrip hero={HERO_FULL} />)
    // total calls as standalone value tile
    expect(screen.getByText('587')).toBeInTheDocument()
    // buy count appears in tile value + in foot text "342 BUY · 245 AVOID"
    expect(screen.getByText(/342 buy/i)).toBeInTheDocument()
    // avoid count embedded in same foot text
    expect(screen.getByText(/245 avoid/i)).toBeInTheDocument()
  })

  it('formats positive avg realized excess with + sign', () => {
    render(<CallsHeroStrip hero={HERO_FULL} />)
    expect(screen.getByText('+5.2%')).toBeInTheDocument()
  })

  it('formats negative avg realized excess with - sign', () => {
    render(<CallsHeroStrip hero={HERO_NEGATIVE} />)
    expect(screen.getByText('-3.1%')).toBeInTheDocument()
  })

  it('shows — when avg realized excess is null', () => {
    render(<CallsHeroStrip hero={HERO_ALL_OPEN} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('shows win rate as percentage', () => {
    render(<CallsHeroStrip hero={HERO_FULL} />)
    expect(screen.getByText('68.0%')).toBeInTheDocument()
  })

  it('shows conditional open text when all positions open', () => {
    render(<CallsHeroStrip hero={HERO_ALL_OPEN} />)
    expect(screen.getByText(/all positions currently active/i)).toBeInTheDocument()
  })

  it('shows in-flight text when some calls closed', () => {
    render(<CallsHeroStrip hero={HERO_FULL} />)
    expect(screen.getByText(/of .* still in flight/i)).toBeInTheDocument()
  })

  it('renders data-as-of footer text', () => {
    render(<CallsHeroStrip hero={HERO_FULL} />)
    expect(screen.getByText(/data as of/i)).toBeInTheDocument()
  })
})
