// Formatting + flagging for the instrument insight panel.
// RULE #0: every number below is a REAL value read from atlas_foundation for BIOCON
// (technical_daily + atlas_lens_scores_daily, date 2026-07-29). Nothing is invented —
// in particular no numeric threshold is introduced here, because thresholds are
// methodology and live in atlas_thresholds (rule #4). Flags come only from values the
// engine already produced: signs, engine booleans, engine tiers, engine risk_flags.
import { describe, it, expect } from 'vitest'

import { toPp, decileOf, weakTier, isConcern, emaStack } from '../insight'

describe('toPp — RS and returns are stored as fractions', () => {
  it('converts a real BIOCON 1m return to percentage points', () => {
    expect(toPp(0.04142083)).toBeCloseTo(4.14, 2)
  })

  it('converts a real negative 1d return', () => {
    expect(toPp(-0.0087106)).toBeCloseTo(-0.87, 2)
  })

  it('passes null through as null rather than 0', () => {
    // A missing metric must never render as a neutral zero (rule #0).
    expect(toPp(null)).toBeNull()
  })
})

describe('emaStack — price vs 21/50/200 EMA alignment (FM rule, 2026-07-30)', () => {
  // All four numbers in each case are REAL closes and EMAs from technical_daily 2026-07-29.
  it('calls a fully ascending stack aligned up — the buy alignment', () => {
    // BIOCON: 432.45 > 428.51 > 418.60 > 392.20
    const s = emaStack(432.45, 428.512094, 418.601494, 392.196852)
    expect(s.verdict).toBe('aligned-up')
    expect(s.links.map((l) => l.up)).toEqual([true, true, true])
  })

  it('calls a fully descending stack aligned down', () => {
    // IRFC: 87.15 < 89.41 < 92.85 < 105.81
    const s = emaStack(87.15, 89.407231, 92.848227, 105.810462)
    expect(s.verdict).toBe('aligned-down')
    expect(s.links.map((l) => l.up)).toEqual([false, false, false])
  })

  it('calls a broken stack mixed, and says which link broke', () => {
    // TCS: 2398 > 2208 (up), but 2208 < 2226 (down) and 2226 < 2618 (down)
    const s = emaStack(2398, 2208.175378, 2225.980799, 2618.206284)
    expect(s.verdict).toBe('mixed')
    expect(s.links.map((l) => l.up)).toEqual([true, false, false])
  })

  it('handles a commodity ETF whose stack is genuinely mixed', () => {
    // GOLDBEES: 116.83 < 118.10, 118.10 < 120.13, but 120.13 > 115.16
    const s = emaStack(116.83, 118.099855, 120.129659, 115.163643)
    expect(s.verdict).toBe('mixed')
    expect(s.links.map((l) => l.up)).toEqual([false, false, true])
  })

  it('labels the links so the chain reads price → 21 → 50 → 200', () => {
    const s = emaStack(432.45, 428.512094, 418.601494, 392.196852)
    expect(s.links.map((l) => l.label)).toEqual(['Price/21', '21/50', '50/200'])
  })

  it('returns no verdict when an EMA is missing rather than guessing one', () => {
    const s = emaStack(432.45, null, 418.6, 392.2)
    expect(s.verdict).toBeNull()
    expect(s.links).toEqual([])
  })
})

describe('decileOf — 0-100 lens scores drive the board decile meter', () => {
  it('puts a real composite of 86 in the top decile band', () => {
    expect(decileOf(86)).toBe(9)
  })

  it('puts a real valuation score of 12.5 near the bottom', () => {
    expect(decileOf(12.5)).toBe(2)
  })

  it('maps a perfect 100 into the tenth decile, not an eleventh', () => {
    expect(decileOf(100)).toBe(10)
  })

  it('maps 0 to the first decile', () => {
    expect(decileOf(0)).toBe(1)
  })

  it('returns null when the score is missing', () => {
    expect(decileOf(null)).toBeNull()
  })
})

describe('weakTier — the engine names its own weak tiers', () => {
  it.each(['BELOW_THRESHOLD', 'WATCH'])('flags %s', (tier) => {
    expect(weakTier(tier)).toBe(true)
  })

  it.each(['HIGHEST', 'HIGH', 'MEDIUM'])('does not flag %s', (tier) => {
    expect(weakTier(tier)).toBe(false)
  })

  it('does not flag an unscored instrument', () => {
    expect(weakTier(null)).toBe(false)
  })
})

describe('isConcern — what the FM should cross-check', () => {
  it('flags a negative return', () => {
    expect(isConcern({ kind: 'signed', value: -0.87 })).toBe(true)
  })

  it('does not flag a positive return', () => {
    expect(isConcern({ kind: 'signed', value: 4.14 })).toBe(false)
  })

  it('flags being below a moving average', () => {
    expect(isConcern({ kind: 'bool', value: false })).toBe(true)
  })

  it('does not flag being above a moving average', () => {
    expect(isConcern({ kind: 'bool', value: true })).toBe(false)
  })

  it('flags the engine OVERVALUED zone', () => {
    expect(isConcern({ kind: 'zone', value: 'OVERVALUED' })).toBe(true)
  })

  it('does not flag a FAIR zone', () => {
    expect(isConcern({ kind: 'zone', value: 'FAIR' })).toBe(false)
  })

  it('never flags a missing value — absence is not a concern, it is unknown', () => {
    expect(isConcern({ kind: 'signed', value: null })).toBe(false)
    expect(isConcern({ kind: 'bool', value: null })).toBe(false)
    expect(isConcern({ kind: 'zone', value: null })).toBe(false)
  })
})
