// The contrast floor is the whole point of this module, so the tests assert the CEILING is never
// exceeded and that the ramp actually lifts small readings — the two properties that were broken.
import { describe, expect, it } from 'vitest'
import { CEILING, rangeTint, shareTint, signedTint, tint } from '../tone'

/** The percentage inside a `color-mix(in srgb, <token> N%, transparent)` string. */
const pct = (s: string | undefined): number => {
  if (s == null) throw new Error('expected a tint')
  const m = /([\d.]+)%/.exec(s)
  if (!m) throw new Error(`not a color-mix: ${s}`)
  return Number(m[1])
}

describe('tint', () => {
  it('never exceeds the ceiling, however large the share', () => {
    for (const share of [1, 2, 10, 1e6, Infinity]) expect(pct(tint('var(--color-pos)', share))).toBeLessThanOrEqual(CEILING)
  })

  it('is zero at zero and the ceiling at one', () => {
    expect(pct(tint('var(--color-pos)', 0))).toBe(0)
    expect(pct(tint('var(--color-pos)', 1))).toBe(CEILING)
  })

  it('lifts a small reading above the linear ramp it replaced', () => {
    // 4% of the way to saturation was 4% of the ceiling — invisible. sqrt puts it at 20%.
    const small = pct(tint('var(--color-pos)', 0.04))
    expect(small).toBeGreaterThan(0.04 * CEILING * 3)
    expect(small).toBeLessThan(CEILING)
  })

  it('rises with the share and never falls', () => {
    const steps = [0, 0.1, 0.25, 0.5, 0.75, 1].map((s) => pct(tint('var(--color-neg)', s)))
    for (let i = 1; i < steps.length; i += 1) expect(steps[i]).toBeGreaterThan(steps[i - 1])
  })

  it('carries the token through rather than a baked colour', () => {
    expect(tint('var(--color-neg)', 0.5)).toContain('var(--color-neg)')
  })

  it('treats a non-finite share as no tint rather than NaN%', () => {
    expect(pct(tint('var(--color-pos)', Number.NaN))).toBe(0)
  })
})

describe('signedTint', () => {
  it('picks the positive token for a gain and the negative for a loss', () => {
    expect(signedTint('0.1', 0.2)).toContain('var(--color-pos)')
    expect(signedTint('-0.1', 0.2)).toContain('var(--color-neg)')
    expect(signedTint('0', 0.2)).toContain('var(--color-pos)')
  })

  it('saturates at the stated magnitude and no further', () => {
    expect(pct(signedTint('0.2', 0.2))).toBe(CEILING)
    expect(pct(signedTint('4.65', 0.2))).toBe(CEILING)
    expect(pct(signedTint('-99', 0.2))).toBe(CEILING)
  })

  it('has nothing to say about a value that was never measured', () => {
    expect(signedTint(null, 0.2)).toBeUndefined()
    expect(signedTint('', 0.2)).toBeUndefined()
    expect(signedTint('not a number', 0.2)).toBeUndefined()
  })
})

describe('shareTint', () => {
  it('is bare at the baseline and saturated at both ends', () => {
    expect(pct(shareTint(0.5))).toBe(0)
    expect(pct(shareTint(1))).toBe(CEILING)
    expect(pct(shareTint(0))).toBe(CEILING)
  })

  it('reads above the baseline as positive and below as negative', () => {
    expect(shareTint(0.8)).toContain('var(--color-pos)')
    expect(shareTint(0.2)).toContain('var(--color-neg)')
  })

  it('honours a baseline that is not one half', () => {
    expect(pct(shareTint(0.9, 0.9))).toBe(0)
    expect(pct(shareTint(1, 0.9))).toBe(CEILING)
  })
})

describe('rangeTint', () => {
  it('floors the weakest row instead of leaving it blank', () => {
    expect(pct(rangeTint('10', 10, 90))).toBeGreaterThan(0)
  })

  it('puts the strongest row at the ceiling', () => {
    expect(pct(rangeTint('90', 10, 90))).toBe(CEILING)
  })

  it('places a single-valued population mid-ramp rather than dividing by zero', () => {
    const only = pct(rangeTint('42', 42, 42))
    expect(Number.isFinite(only)).toBe(true)
    expect(only).toBeGreaterThan(0)
    expect(only).toBeLessThan(CEILING)
  })

  it('says nothing about an unscored row', () => {
    expect(rangeTint(null, 10, 90)).toBeUndefined()
  })
})
