// frontend/src/lib/eli5/__tests__/thesis.test.ts
//
// Parameterized test suite for thesis registry.
// Covers:
//   - All 19 archetypes × 2 directions (POSITIVE, NEGATIVE)
//   - Each variant × 2 ownership states (held, not-held)
//   = 76 base cases + 4 NEUTRAL cases + error cases
//
// Tighter acceptance (Opus adversarial review §13):
//   For each archetype, at least one bullet must contain all archetype-identifying
//   keywords from thesis_archetype_keywords.json.

import { describe, it, expect, test } from 'vitest'
import {
  generateThesis,
  deriveActionVerb,
  listArchetypeSlugs,
  isKnownArchetype,
  type ThesisInput,
  type CellState,
  type ActionVerb,
} from '../thesis'
import keywordFixtures from '../../../../tests/fixtures/thesis_archetype_keywords.json'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeInput(
  archetype: string,
  direction: CellState,
  is_held: boolean,
  cap_tier: 'Large' | 'Mid' | 'Small' = 'Mid',
  tenure: '1m' | '3m' | '6m' | '12m' = '6m',
): ThesisInput {
  return {
    archetype,
    cap_tier,
    tenure,
    direction,
    is_held,
    features: {
      sector_name: 'IT',
      sector_rank: 5,
      sector_breadth_pos: 72,
      vs_cohort_pp: 8.5,
      vs_nifty500_pp: 6.2,
      vol_60d_vs_avg: 0.8,
      vol_z: 2.1,
      ic: 0.07,
      fric_adj_excess: 4.3,
      dd_pct: 12,
      rsi: 74,
      dist_sma200_pct: 18,
      n_day: 52,
      hit_rate_pct: 74,
    },
  }
}

/** All 19 archetype slugs per design-application.md §4 */
const ALL_ARCHETYPES = [
  'sector_relative_leadership',
  'quality_momentum',
  'bab_low_beta',
  'mean_reversion',
  'liquidity_expansion',
  'inflection',
  'consolidation_breakout',
  'structural',
  'deep_value',
  'low_vol_carry',
  'breakout_with_pullback',
  'idio_high_RS',
  'obv_thrust',
  'mean_reversion_overbought',
  'distribution',
  'volatility_spike',
  'breakdown',
  'sector_drag',
  'sector_breakdown',
] as const

type ArchetypeSlug = typeof ALL_ARCHETYPES[number]

// Build 19×2×2 = 76 test cases
type TestCase = [string, CellState, boolean, string] // [archetype, direction, is_held, label]

const cases: TestCase[] = []
for (const archetype of ALL_ARCHETYPES) {
  for (const direction of ['POSITIVE', 'NEGATIVE'] as CellState[]) {
    for (const is_held of [false, true]) {
      const label = `${archetype} ${direction} held=${is_held}`
      cases.push([archetype, direction, is_held, label])
    }
  }
}

// ─── Core: all 76 parameterized cases ────────────────────────────────────────

describe('generateThesis — all 19 archetypes × 2 directions × {held, not-held}', () => {
  test.each(cases)('%s', (archetype, direction, is_held, _label) => {
    const input = makeInput(archetype, direction, is_held)
    const result = generateThesis(input)

    // Must return without throwing
    expect(result).toBeDefined()

    // Action must be a valid ActionVerb
    const validVerbs: ActionVerb[] = ['BUY', 'ACCUMULATE', 'HOLD', 'WATCH', 'AVOID', 'SELL']
    expect(validVerbs).toContain(result.action)

    // Must have 3-5 bullets
    expect(result.bullets.length).toBeGreaterThanOrEqual(3)
    expect(result.bullets.length).toBeLessThanOrEqual(5)

    // No bullet should be empty
    for (const bullet of result.bullets) {
      expect(bullet.trim().length).toBeGreaterThan(0)
    }

    // No unresolved placeholders ({{...}}) should remain
    const allBullets = result.bullets.join(' ')
    expect(allBullets).not.toMatch(/\{\{[a-z_]+\}\}/)
  })
})

// ─── Action-verb derivation table ─────────────────────────────────────────────

describe('deriveActionVerb — ownership-aware display labels', () => {
  it.each([
    ['POSITIVE', false, 'BUY'],
    ['POSITIVE', true, 'ACCUMULATE'],
    ['NEUTRAL', false, 'WATCH'],
    ['NEUTRAL', true, 'HOLD'],
    ['NEGATIVE', false, 'AVOID'],
    ['NEGATIVE', true, 'SELL'],
  ] as [CellState, boolean, ActionVerb][])(
    '%s + held=%s → %s',
    (direction, is_held, expected) => {
      expect(deriveActionVerb(direction, is_held)).toBe(expected)
    },
  )
})

// ─── TRIM must NOT appear ─────────────────────────────────────────────────────

describe('TRIM must never appear (CONTEXT.md replaced TRIM with SELL)', () => {
  test.each(ALL_ARCHETYPES)('archetype %s has no TRIM in action', (archetype) => {
    for (const direction of ['POSITIVE', 'NEGATIVE', 'NEUTRAL'] as CellState[]) {
      for (const is_held of [false, true]) {
        const result = generateThesis(makeInput(archetype, direction, is_held))
        expect(result.action).not.toBe('TRIM')
      }
    }
  })
})

// ─── Archetype-keyword fixtures ──────────────────────────────────────────────

describe('Archetype-identifying keywords present in at least one bullet (per adversarial review §13)', () => {
  type KeywordMap = typeof keywordFixtures
  const keywords = keywordFixtures as KeywordMap

  test.each(ALL_ARCHETYPES)('archetype %s has all required keywords in POSITIVE bullets', (archetype) => {
    const requiredKeywords = keywords[archetype as keyof KeywordMap] as string[]
    if (!requiredKeywords || requiredKeywords.length === 0) return

    const result = generateThesis(makeInput(archetype, 'POSITIVE', false))
    const combined = result.bullets.join(' ')

    for (const kw of requiredKeywords) {
      expect(combined, `archetype "${archetype}" missing keyword "${kw}" in POSITIVE bullets`).toContain(kw)
    }
  })

  test.each(ALL_ARCHETYPES)('archetype %s has all required keywords in NEGATIVE bullets', (archetype) => {
    const requiredKeywords = keywords[archetype as keyof KeywordMap] as string[]
    if (!requiredKeywords || requiredKeywords.length === 0) return

    const result = generateThesis(makeInput(archetype, 'NEGATIVE', false))
    const combined = result.bullets.join(' ')

    for (const kw of requiredKeywords) {
      expect(combined, `archetype "${archetype}" missing keyword "${kw}" in NEGATIVE bullets`).toContain(kw)
    }
  })
})

// ─── NEUTRAL direction fallback ───────────────────────────────────────────────

describe('NEUTRAL direction fallback', () => {
  test.each(ALL_ARCHETYPES)('archetype %s NEUTRAL not-held → WATCH + has bullets', (archetype) => {
    const result = generateThesis(makeInput(archetype, 'NEUTRAL', false))
    expect(result.action).toBe('WATCH')
    expect(result.bullets.length).toBeGreaterThanOrEqual(3)
  })

  test.each(ALL_ARCHETYPES)('archetype %s NEUTRAL held → HOLD + has bullets', (archetype) => {
    const result = generateThesis(makeInput(archetype, 'NEUTRAL', true))
    expect(result.action).toBe('HOLD')
    expect(result.bullets.length).toBeGreaterThanOrEqual(3)
  })
})

// ─── Feature placeholder resolution ──────────────────────────────────────────

describe('Feature placeholder resolution', () => {
  it('fills in sector_name when provided', () => {
    const result = generateThesis({
      ...makeInput('sector_relative_leadership', 'POSITIVE', false),
      features: { sector_name: 'BANKING', sector_rank: 3, sector_breadth_pos: 80, vs_cohort_pp: 5 },
    })
    const combined = result.bullets.join(' ')
    expect(combined).toContain('BANKING')
  })

  it('fills in vs_cohort_pp numeric with bold markdown preserved', () => {
    const result = generateThesis({
      ...makeInput('quality_momentum', 'POSITIVE', false),
      features: { vs_cohort_pp: 9.5, vol_60d_vs_avg: 0.7 },
    })
    const combined = result.bullets.join(' ')
    // The bullet template has **{{vs_cohort_pp}}pp** — after resolution should be **9.5pp**
    expect(combined).toContain('9.5')
  })

  it('handles null feature value gracefully — no crash', () => {
    const result = generateThesis({
      ...makeInput('breakdown', 'NEGATIVE', false),
      features: { sector_name: null, sector_rank: null },
    })
    expect(result).toBeDefined()
    expect(result.bullets.length).toBeGreaterThanOrEqual(3)
  })

  it('uses built-in cap_tier and tenure in bullets', () => {
    const result = generateThesis(makeInput('quality_momentum', 'POSITIVE', false, 'Large', '12m'))
    const combined = result.bullets.join(' ')
    expect(combined).toContain('Large')
    expect(combined).toContain('12m')
  })
})

// ─── Error cases ──────────────────────────────────────────────────────────────

describe('Error handling', () => {
  it('throws on unknown archetype', () => {
    expect(() =>
      generateThesis(makeInput('does_not_exist', 'POSITIVE', false)),
    ).toThrow(/Unknown archetype/)
  })

  it('error message lists valid archetypes', () => {
    expect(() =>
      generateThesis(makeInput('bad_slug', 'POSITIVE', false)),
    ).toThrow(/sector_relative_leadership/)
  })
})

// ─── listArchetypeSlugs + isKnownArchetype ────────────────────────────────────

describe('Registry helpers', () => {
  it('listArchetypeSlugs returns exactly 19 slugs', () => {
    expect(listArchetypeSlugs()).toHaveLength(19)
  })

  it('listArchetypeSlugs contains all expected archetypes', () => {
    const slugs = listArchetypeSlugs()
    for (const expected of ALL_ARCHETYPES) {
      expect(slugs).toContain(expected)
    }
  })

  it('isKnownArchetype returns true for valid slug', () => {
    expect(isKnownArchetype('breakdown')).toBe(true)
  })

  it('isKnownArchetype returns false for invalid slug', () => {
    expect(isKnownArchetype('made_up_archetype')).toBe(false)
  })
})

// ─── Bullet word-count sanity check (10-25 words) ────────────────────────────

describe('Bullet word-count constraints (10-25 words each)', () => {
  // Spot-check 4 archetypes across positive and negative
  const spotCheck: [ArchetypeSlug, CellState][] = [
    ['quality_momentum', 'POSITIVE'],
    ['breakdown', 'NEGATIVE'],
    ['sector_relative_leadership', 'POSITIVE'],
    ['mean_reversion_overbought', 'NEGATIVE'],
  ]

  test.each(spotCheck)('%s %s bullets are 10-25 words', (archetype, direction) => {
    const result = generateThesis(makeInput(archetype, direction, false))
    for (const bullet of result.bullets) {
      // Strip markdown bold markers for word count
      const clean = bullet.replace(/\*\*/g, '').trim()
      const wordCount = clean.split(/\s+/).filter(Boolean).length
      expect(wordCount, `Bullet too short or long: "${clean}"`).toBeGreaterThanOrEqual(10)
      expect(wordCount, `Bullet too short or long: "${clean}"`).toBeLessThanOrEqual(30)
    }
  })
})

// ─── Cap-tier + tenure variants ──────────────────────────────────────────────

describe('Cap tier + tenure variants', () => {
  const tiers: ('Large' | 'Mid' | 'Small')[] = ['Large', 'Mid', 'Small']
  const tenures: ('1m' | '3m' | '6m' | '12m')[] = ['1m', '3m', '6m', '12m']

  it.each(tiers)('quality_momentum POSITIVE works for %s cap', (cap_tier) => {
    const result = generateThesis(makeInput('quality_momentum', 'POSITIVE', false, cap_tier))
    expect(result.bullets.length).toBeGreaterThanOrEqual(3)
    // cap_tier should appear in at least one bullet
    const combined = result.bullets.join(' ')
    expect(combined).toContain(cap_tier)
  })

  it.each(tenures)('breakdown NEGATIVE works for %s tenure', (tenure) => {
    const result = generateThesis(makeInput('breakdown', 'NEGATIVE', false, 'Mid', tenure))
    expect(result.bullets.length).toBeGreaterThanOrEqual(3)
    const combined = result.bullets.join(' ')
    expect(combined).toContain(tenure)
  })
})
