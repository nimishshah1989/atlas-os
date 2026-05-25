// Tests for frontend/src/lib/v6/sizing.ts — B.5 position sizing
// 8 cases covering all 4 binding constraints + boundary conditions.

import { describe, it, expect } from 'vitest'
import { computeSizing } from '../sizing'
import type { SizingInput, SizingRec, BindingConstraint } from '../sizing'

// ---------------------------------------------------------------------------
// Helper factory — produces a fully-typed SizingInput with sensible defaults.
// ---------------------------------------------------------------------------
function makeInput(overrides: Partial<SizingInput> = {}): SizingInput {
  return {
    current_weight_pct: 1.5,
    max_per_stock_pct: 5,
    deployment_multiplier: 1.0,
    sector_gap_pp: 0,
    cell_conviction_depth: 3,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Case 1 — Below max_per_stock, regime 1.0x, conviction high, sector neutral
//          → suggest meaningful add; binding = max_per_stock
// ---------------------------------------------------------------------------
describe('computeSizing', () => {
  it('case 1: below cap, regime 1.0x, high conviction, neutral sector → meaningful add', () => {
    const result: SizingRec = computeSizing(
      makeInput({
        current_weight_pct: 1.5,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.0,
        sector_gap_pp: 0,
        cell_conviction_depth: 4,
      }),
    )

    expect(result.suggested_add_pct).toBeGreaterThan(0)
    expect(result.binding_constraint).toBe<BindingConstraint>('max_per_stock')
    expect(result.rationale).toContain('+')
    // Room to max = 5 - 1.5 = 3.5; regime room = 5*1.0 - 1.5 = 3.5 → suggest 3.5
    expect(result.suggested_add_pct).toBe(3.5)
  })

  // -------------------------------------------------------------------------
  // Case 2 — Already at max_per_stock → suggested_add = 0, binding = max_per_stock
  // -------------------------------------------------------------------------
  it('case 2: at max_per_stock cap → suggested_add_pct = 0, binding = max_per_stock', () => {
    const result = computeSizing(
      makeInput({
        current_weight_pct: 5,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.0,
        sector_gap_pp: 0,
        cell_conviction_depth: 3,
      }),
    )

    expect(result.suggested_add_pct).toBe(0)
    expect(result.binding_constraint).toBe<BindingConstraint>('max_per_stock')
  })

  // -------------------------------------------------------------------------
  // Case 3 — Regime 0.5x bear → suggested_add reduced vs 1.0x baseline
  // -------------------------------------------------------------------------
  it('case 3: regime 0.5x → suggested reduced vs 1.0x baseline', () => {
    const baseline = computeSizing(
      makeInput({ current_weight_pct: 0, max_per_stock_pct: 5, deployment_multiplier: 1.0 }),
    )
    const bearCase = computeSizing(
      makeInput({ current_weight_pct: 0, max_per_stock_pct: 5, deployment_multiplier: 0.5 }),
    )

    // Bear regime: effective cap = 5 * 0.5 = 2.5; baseline: effective cap = 5
    expect(bearCase.suggested_add_pct).toBeLessThan(baseline.suggested_add_pct)
    expect(bearCase.binding_constraint).toBe<BindingConstraint>('deployment_cap')
    expect(bearCase.suggested_add_pct).toBe(2.5)
  })

  // -------------------------------------------------------------------------
  // Case 4 — Sector overweight > 5pp → binding = sector_cap, suggested = 0
  // -------------------------------------------------------------------------
  it('case 4: sector overweight >5pp → sector_cap binding, suggested = 0', () => {
    const result = computeSizing(
      makeInput({
        current_weight_pct: 1,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.0,
        sector_gap_pp: 8,  // 8pp overweight — exceeds 5pp threshold
        cell_conviction_depth: 3,
      }),
    )

    expect(result.suggested_add_pct).toBe(0)
    expect(result.binding_constraint).toBe<BindingConstraint>('sector_cap')
    expect(result.rationale).toContain('sector overweight')
  })

  // -------------------------------------------------------------------------
  // Case 5 — Sector underweight + high conviction → suggested_add boosted
  // -------------------------------------------------------------------------
  it('case 5: sector underweight + high conviction → suggested boosted vs neutral', () => {
    const neutral = computeSizing(
      makeInput({
        current_weight_pct: 0,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.0,
        sector_gap_pp: 0,
        cell_conviction_depth: 4,
      }),
    )
    const underweight = computeSizing(
      makeInput({
        current_weight_pct: 0,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.0,
        sector_gap_pp: -8,  // -8pp underweight — below -5pp threshold
        cell_conviction_depth: 4,
      }),
    )

    expect(underweight.suggested_add_pct).toBeGreaterThanOrEqual(neutral.suggested_add_pct)
    expect(underweight.rationale).toContain('underweight')
  })

  // -------------------------------------------------------------------------
  // Case 6 — Conviction depth 0 → conviction_floor binding, suggested = 0
  // -------------------------------------------------------------------------
  it('case 6: conviction_depth = 0 → conviction_floor, suggested = 0', () => {
    const result = computeSizing(
      makeInput({
        current_weight_pct: 0,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.0,
        sector_gap_pp: 0,
        cell_conviction_depth: 0,
      }),
    )

    expect(result.suggested_add_pct).toBe(0)
    expect(result.binding_constraint).toBe<BindingConstraint>('conviction_floor')
    expect(result.rationale).toContain('conviction')
  })

  // -------------------------------------------------------------------------
  // Case 7 — Deployment cap binding (multiplier is very low)
  // -------------------------------------------------------------------------
  it('case 7: deployment cap binding (multiplier 0.1 with 0% current) → deployment_cap', () => {
    const result = computeSizing(
      makeInput({
        current_weight_pct: 0,
        max_per_stock_pct: 5,
        deployment_multiplier: 0.1,  // effective cap = 0.5%
        sector_gap_pp: 0,
        cell_conviction_depth: 3,
      }),
    )

    // effectiveCap = 5 * 0.1 = 0.5; roomToMax = 5; regimeRoom = 0.5
    expect(result.binding_constraint).toBe<BindingConstraint>('deployment_cap')
    expect(result.suggested_add_pct).toBe(0.5)
  })

  // -------------------------------------------------------------------------
  // Case 8 — Boundary: current_weight = max_per_stock exactly → 0, max_per_stock
  // -------------------------------------------------------------------------
  it('case 8: boundary — current_weight equals max_per_stock exactly → 0, max_per_stock', () => {
    const result = computeSizing(
      makeInput({
        current_weight_pct: 5,
        max_per_stock_pct: 5,
        deployment_multiplier: 1.5,  // even bull regime can't override the hard cap
        sector_gap_pp: -10,          // even underweight sector can't override
        cell_conviction_depth: 5,    // even max conviction can't override
      }),
    )

    expect(result.suggested_add_pct).toBe(0)
    expect(result.binding_constraint).toBe<BindingConstraint>('max_per_stock')
  })
})
