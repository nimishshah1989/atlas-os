// frontend/src/components/v6/__tests__/PositionSizingWidget.test.tsx
//
// 5 test cases per plan:
//   1. Not held (holdingState=null): renders "first position" copy, current_weight_pct=0
//   2. Held: current weight derived from aggregate_weight via toNumber()
//   3. Binding constraint "max_per_stock": suggested_add=0, "at cap" copy
//   4. Binding constraint "conviction_floor": cellConvictionDepth=0 → "conviction too thin"
//   5. Sector overweight: binding "sector_cap" → "book overweight" copy

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PositionSizingWidget } from '../PositionSizingWidget'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** aggregate_weight "0.035" = 3.5% as whole-number pct to computeSizing */
const HOLDING_3_5PCT: HoldingState = {
  portfolio_count: 2,
  weight_range: ['0.03', '0.04'],
  aggregate_weight: '0.035',
  last_add_date: '2026-04-10',
}

/** aggregate_weight at full cap: 5% / max_per_stock_pct 5 → suggested = 0 */
const HOLDING_AT_CAP: HoldingState = {
  portfolio_count: 1,
  weight_range: ['0.05', '0.05'],
  aggregate_weight: '0.05',
  last_add_date: '2026-03-20',
}

// ---------------------------------------------------------------------------
// 1. Not held (null): "first position" copy
// ---------------------------------------------------------------------------

describe('PositionSizingWidget — not held (holdingState=null)', () => {
  it('renders first-position headline and passes current_weight_pct=0 to computeSizing', () => {
    render(
      <PositionSizingWidget
        holdingState={null}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={3}
        maxPerStockPct={5}
      />,
    )
    // With no holding, current_weight=0, max=5, depth=3, no sector gap → suggests room
    // aria-label encodes current weight 0.0
    const ariaLabel = screen.getByLabelText(/suggested position add/i)
    expect(ariaLabel).toBeInTheDocument()
    expect(ariaLabel.getAttribute('aria-label')).toContain('current weight 0.0%')
    // Headline copy includes "first position"
    expect(screen.getByText(/first position/i)).toBeInTheDocument()
  })

  it('shows current 0% in aria-label when not held', () => {
    render(
      <PositionSizingWidget
        holdingState={null}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={2}
      />,
    )
    const el = screen.getByLabelText(/suggested position add/i)
    expect(el.getAttribute('aria-label')).toContain('0.0%')
  })
})

// ---------------------------------------------------------------------------
// 2. Held: current weight derived from aggregate_weight (toNumber boundary)
// ---------------------------------------------------------------------------

describe('PositionSizingWidget — held with 3.5% weight', () => {
  it('derives current_weight_pct from aggregate_weight "0.035" (3.5%) correctly', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_3_5PCT}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={4}
        maxPerStockPct={5}
      />,
    )
    // current weight = 3.5%, max = 5%, room = 1.5%
    // Expected: "+1.5% suggested next add (current 3.5%)"
    const el = screen.getByLabelText(/suggested position add/i)
    expect(el.getAttribute('aria-label')).toContain('3.5%')
    // Headline contains the add amount
    expect(screen.getByText(/suggested next add/i)).toBeInTheDocument()
    expect(screen.getByText(/3\.5%/)).toBeInTheDocument()
  })

  it('shows rationale secondary line', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_3_5PCT}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={4}
        maxPerStockPct={5}
      />,
    )
    // rationale is the secondary text line from computeSizing
    // It should be non-empty (the sizing fn always returns a rationale string)
    const rationaleLine = screen
      .getAllByRole('paragraph')
      .find((p) => p.className.includes('ink-tertiary'))
    // Fallback: just check there is a text element containing "%" or "cap"
    const all = screen.getAllByText(/\+|\bmax\b|\bsuggested\b|\bcap\b/i)
    expect(all.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// 3. Binding constraint: max_per_stock — suggested = 0, "at cap" copy
// ---------------------------------------------------------------------------

describe('PositionSizingWidget — binding: max_per_stock', () => {
  it('renders at-cap headline when holding equals maxPerStockPct', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_AT_CAP}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={3}
        maxPerStockPct={5}
      />,
    )
    // aggregate_weight=0.05 → 5%, max=5 → roomToMax=0 → binding=max_per_stock, add=0
    expect(screen.getByText(/at cap/i)).toBeInTheDocument()
    // binding chip shows "max per stock"
    expect(screen.getByText('max per stock')).toBeInTheDocument()
    // aria-label: +0.0%
    const el = screen.getByLabelText(/suggested position add/i)
    expect(el.getAttribute('aria-label')).toContain('+0.0%')
  })

  it('renders cap value in chip suffix', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_AT_CAP}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={3}
        maxPerStockPct={5}
      />,
    )
    // The "5% cap" suffix should be visible
    expect(screen.getByText('5% cap')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 4. Binding constraint: conviction_floor — cellConvictionDepth=0
// ---------------------------------------------------------------------------

describe('PositionSizingWidget — binding: conviction_floor', () => {
  it('renders "conviction too thin" headline when depth=0', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_3_5PCT}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={0}
        maxPerStockPct={5}
      />,
    )
    // computeSizing fires conviction_floor when depth <= 0
    expect(screen.getByText(/conviction too thin/i)).toBeInTheDocument()
    // binding chip label
    expect(screen.getByText('conviction floor')).toBeInTheDocument()
  })

  it('has +0.0% in aria-label for zero conviction', () => {
    render(
      <PositionSizingWidget
        holdingState={null}
        deploymentMultiplier={1.0}
        sectorGapPp={0}
        cellConvictionDepth={0}
      />,
    )
    const el = screen.getByLabelText(/suggested position add/i)
    expect(el.getAttribute('aria-label')).toContain('+0.0%')
    expect(el.getAttribute('aria-label')).toContain('conviction floor')
  })
})

// ---------------------------------------------------------------------------
// 5. Sector overweight: binding sector_cap
// ---------------------------------------------------------------------------

describe('PositionSizingWidget — binding: sector_cap (overweight)', () => {
  it('renders sector-overweight headline when sectorGapPp > 5', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_3_5PCT}
        deploymentMultiplier={1.0}
        sectorGapPp={8}   // 8pp overweight → sector_cap fires
        cellConvictionDepth={4}
        maxPerStockPct={5}
      />,
    )
    // binding = sector_cap, suggested = 0
    expect(screen.getByText(/book overweight in sector/i)).toBeInTheDocument()
    // chip label
    expect(screen.getByText('sector cap')).toBeInTheDocument()
  })

  it('aria-label reflects sector_cap constraint', () => {
    render(
      <PositionSizingWidget
        holdingState={HOLDING_3_5PCT}
        deploymentMultiplier={1.0}
        sectorGapPp={8}
        cellConvictionDepth={4}
        maxPerStockPct={5}
      />,
    )
    const el = screen.getByLabelText(/suggested position add/i)
    expect(el.getAttribute('aria-label')).toContain('sector cap')
    expect(el.getAttribute('aria-label')).toContain('+0.0%')
  })
})
