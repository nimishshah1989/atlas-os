// Tests for src/lib/position-sizing.ts

import { describe, it, expect } from 'vitest'
import { computeSizing } from '@/lib/position-sizing'

describe('computeSizing', () => {
  it('returns max_per_stock as suggested when it is the tightest constraint', () => {
    // regimeCap = 1.0 * 100 = 100, regimeRoom = 100 - 0 = 100
    // targetGap = maxPs = 5 → suggested = 5, binding = max_per_stock
    const result = computeSizing('5', '1', 0)
    expect(result.suggestedPct).toBe('5.0')
    expect(result.bindingConstraint).toBe('max_per_stock')
  })

  it('returns regime_cap as binding when regimeRoom is tighter', () => {
    // regimeCap = 0.03 * 100 = 3, regimeRoom = 3 - 0 = 3
    // maxPs = 5 → raw = min(5, 5, 3) = 3 → binding = regime_cap
    const result = computeSizing('5', '0.03', 0)
    expect(result.suggestedPct).toBe('3.0')
    expect(result.bindingConstraint).toBe('regime_cap')
  })

  it('subtracts currentInvested from regimeRoom', () => {
    // regimeCap = 1.0 * 100 = 100, currentInvested = 98
    // regimeRoom = 100 - 98 = 2 → tighter than maxPs=5 → regime_cap
    const result = computeSizing('5', '1', 98)
    expect(result.suggestedPct).toBe('2.0')
    expect(result.bindingConstraint).toBe('regime_cap')
  })

  it('returns 0.0 and regime_cap when portfolio is fully invested', () => {
    // regimeRoom = 100 - 100 = 0 → suggested = max(0, 0) = 0
    const result = computeSizing('5', '1', 100)
    expect(result.suggestedPct).toBe('0.0')
    expect(result.bindingConstraint).toBe('regime_cap')
  })

  it('clamps negative regimeRoom to 0', () => {
    // currentInvested > regimeCap → regimeRoom is negative → suggested = 0
    const result = computeSizing('5', '0.5', 60)
    expect(result.suggestedPct).toBe('0.0')
    expect(result.bindingConstraint).toBe('regime_cap')
  })

  it('always returns sectorGapApplied = false (not yet wired)', () => {
    const result = computeSizing('5', '1', 0)
    expect(result.sectorGapApplied).toBe(false)
  })

  it('handles string currentInvested-equivalent: zero portfolio (empty instruments)', () => {
    // currentInvested = 0 when portfolio has no instruments
    const result = computeSizing('5', '0.8', 0)
    expect(result.suggestedPct).toBe('5.0')
    expect(result.bindingConstraint).toBe('max_per_stock')
  })

  it('handles regime_cap = 0 (deployment_multiplier = 0)', () => {
    const result = computeSizing('5', '0', 0)
    expect(result.suggestedPct).toBe('0.0')
    expect(result.bindingConstraint).toBe('regime_cap')
  })
})
