/**
 * Tests for frontend/src/lib/sector-targets.ts
 *
 * deriveSectorTargets is a pure TS mirror of targets.py:derive_sector_targets.
 * Formula:
 *   raw[i] = pct_stage_2[i] * mean_within_state_rank[i]
 *   total_raw = sum(raw)
 *   normalized[i] = raw[i] / total_raw
 *   pre_cap[i] = normalized[i] * regime_cap
 *   target[i] = min(pre_cap[i], max_per_sector_pct), rounded to 2dp
 *   gap[i] = target[i] - current[i]
 */
import { describe, it, expect } from 'vitest'
import { deriveSectorTargets, type SectorSignalInput, type SectorTargetOutput } from '@/lib/sector-targets'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sig(sector: string, pct_stage_2: number | null, mean_within_state_rank: number | null): SectorSignalInput {
  return { sector, pct_stage_2, mean_within_state_rank }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('deriveSectorTargets', () => {
  it('returns empty list for empty input', () => {
    expect(deriveSectorTargets([], {}, 100, 15)).toEqual([])
  })

  it('degenerate: all zero pct_stage_2 → all targets 0', () => {
    const signals = [sig('A', 0, 0.5), sig('B', 0, 0.8)]
    const result = deriveSectorTargets(signals, {}, 80, 15)
    expect(result).toHaveLength(2)
    expect(result[0].target).toBe(0)
    expect(result[1].target).toBe(0)
  })

  it('degenerate: null pct_stage_2 treated as 0 → all targets 0', () => {
    const signals = [sig('A', null, null), sig('B', null, null)]
    const result = deriveSectorTargets(signals, {}, 80, 15)
    expect(result.every(t => t.target === 0)).toBe(true)
  })

  it('single sector gets all allocation up to cap', () => {
    // One sector: raw = 1.0, normalized = 1.0, pre_cap = 80, target = min(80, 15) = 15
    const signals = [sig('A', 1.0, 1.0)]
    const result = deriveSectorTargets(signals, {}, 80, 15)
    expect(result).toHaveLength(1)
    expect(result[0].target).toBe(15)
  })

  it('two equal sectors split regime_cap evenly, capped at max_per_sector', () => {
    // raw_A = raw_B = 0.5*0.8 = 0.4
    // total_raw = 0.8, normalized = 0.5 each
    // pre_cap = 0.5 * 40 = 20 each → capped at 15
    const signals = [sig('A', 0.5, 0.8), sig('B', 0.5, 0.8)]
    const result = deriveSectorTargets(signals, {}, 40, 15)
    expect(result[0].target).toBe(15)
    expect(result[1].target).toBe(15)
  })

  it('target cannot exceed max_per_sector_pct', () => {
    const signals = [sig('A', 1.0, 1.0)]
    const result = deriveSectorTargets(signals, {}, 100, 25)
    expect(result[0].target).toBe(25)
  })

  it('gap = target - current (positive = add, negative = trim)', () => {
    const signals = [sig('A', 1.0, 1.0)]
    const currentWeights = { A: 10 }
    const result = deriveSectorTargets(signals, currentWeights, 80, 15)
    // target = 15, current = 10, gap = 5
    expect(result[0].current).toBe(10)
    expect(result[0].gap).toBeCloseTo(result[0].target - result[0].current)
  })

  it('missing sector in currentWeights defaults to 0 current', () => {
    const signals = [sig('A', 0.5, 0.8)]
    const result = deriveSectorTargets(signals, {}, 80, 15)
    expect(result[0].current).toBe(0)
    expect(result[0].gap).toBe(result[0].target)
  })

  it('target rounded to 2 decimal places', () => {
    // Ensures output doesn't have long floating-point tails
    const signals = [sig('A', 0.33, 0.77), sig('B', 0.67, 0.55)]
    const result = deriveSectorTargets(signals, {}, 80, 15)
    for (const t of result) {
      const rounded = Math.round(t.target * 100) / 100
      expect(t.target).toBeCloseTo(rounded, 5)
    }
  })

  it('sum of targets <= regime_cap', () => {
    const signals = [sig('A', 0.6, 0.9), sig('B', 0.4, 0.8), sig('C', 0.8, 0.7)]
    const result = deriveSectorTargets(signals, {}, 60, 15)
    const total = result.reduce((acc, t) => acc + t.target, 0)
    expect(total).toBeLessThanOrEqual(60 + 0.01) // +0.01 for rounding tolerance
  })

  it('no portfolio (no active portfolio) → pass regime_cap=100 and arbitrary max_sector → no errors', () => {
    const signals = [sig('A', 0.5, 0.7), sig('B', 0.3, 0.6)]
    // Should not throw
    expect(() => deriveSectorTargets(signals, {}, 100, 20)).not.toThrow()
  })
})
