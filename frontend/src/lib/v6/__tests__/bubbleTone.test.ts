import { describe, it, expect } from 'vitest'
import { quartileCuts, relativeTone } from '../bubbleTone'

// REAL fund composites pulled from atlas_foundation (snapshot 2026-06-26) — the actual values
// that made every bubble red under the old 60/45 cut. They cluster ~42–55 (rule #0: real data).
const REAL_FUND_COMPOSITES = [
  48.34, 52.0, 50.51, 44.4, 43.85, 43.24, 42.94, 41.27, 39.33, 39.21, 37.87, 35.52,
  55.43, 53.61, 49.25, 47.76, 46.52, 54.13, 51.09, 50.07, 52.12, 46.91, 47.67,
]

describe('quartileCuts', () => {
  it('splits the real fund cohort into non-degenerate cuts inside its range', () => {
    const [lo, hi] = quartileCuts(REAL_FUND_COMPOSITES)
    expect(lo).toBeLessThan(hi)
    expect(lo).toBeGreaterThanOrEqual(Math.min(...REAL_FUND_COMPOSITES))
    expect(hi).toBeLessThanOrEqual(Math.max(...REAL_FUND_COMPOSITES))
  })

  it('handles empty input without throwing', () => {
    expect(quartileCuts([])).toEqual([0, 0])
  })
})

describe('relativeTone', () => {
  it('gives a real green/grey/red spread on the real cohort (not all red)', () => {
    const [lo, hi] = quartileCuts(REAL_FUND_COMPOSITES)
    const tones = REAL_FUND_COMPOSITES.map((v) => relativeTone(v, lo, hi))
    const pos = tones.filter((t) => t === 'pos').length
    const neg = tones.filter((t) => t === 'neg').length
    const neutral = tones.filter((t) => t === 'neutral').length
    // every bucket is populated — the bug was 0 green + mostly red
    expect(pos).toBeGreaterThan(0)
    expect(neg).toBeGreaterThan(0)
    expect(neutral).toBeGreaterThan(0)
  })

  it('top value is green, bottom value is red', () => {
    const [lo, hi] = quartileCuts(REAL_FUND_COMPOSITES)
    expect(relativeTone(Math.max(...REAL_FUND_COMPOSITES), lo, hi)).toBe('pos')
    expect(relativeTone(Math.min(...REAL_FUND_COMPOSITES), lo, hi)).toBe('neg')
  })

  it('null/unscored is neutral', () => {
    expect(relativeTone(null, 40, 50)).toBe('neutral')
    expect(relativeTone(undefined, 40, 50)).toBe('neutral')
  })
})
