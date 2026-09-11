// The pure half of the ranked board. Nothing here is a market number: a decile is 1–10 by
// definition, a lens count is a count, and the peer-group tokens are the ones
// scripts/global_market/score_etfs.py writes (`<asset class>:<strategy>`, both vocabularies fixed
// by ddl/03_classification.sql's CHECK). What is under test is the mapping to the screen — and,
// above all, that an absent measurement never comes out as a zero (rule #0).
import { describe, expect, it } from 'vitest'
import {
  decileColour,
  isLeader,
  LEADER_DECILE,
  lensesLabel,
  lensesShort,
  lensSubs,
  orderBy,
  peerGroupLabel,
  peerGroupOf,
  rankSentence,
  rsTint,
  tierLabel,
  TIER_LABEL,
  universeSide,
} from '@/lib/scores'
import { CEILING } from '@/lib/tone'

describe('decile → colour', () => {
  it('maps each decile to its own step of the ramp defined in globals.css', () => {
    for (let n = 1; n <= 10; n += 1) expect(decileColour(n)).toBe(`var(--decile-${n})`)
  })
  it('reads a NUMERIC string, which is how postgres hands a decile over', () => {
    expect(decileColour('7')).toBe('var(--decile-7)')
  })
  it('has NO colour outside 1–10, and none at all for an unscored row', () => {
    for (const v of [0, 11, -1, NaN, null, undefined, '', 'x']) expect(decileColour(v)).toBeNull()
  })
  it('rounds to the nearest step rather than dropping the chip (ntile only ever gives integers)', () => {
    expect(decileColour(6.6)).toBe('var(--decile-7)')
  })
  it('reserves Leader for the top decile, the same cut India makes within cap cohort', () => {
    expect(LEADER_DECILE).toBe(10)
    expect(isLeader(10)).toBe(true)
    expect(isLeader(9)).toBe(false)
    expect(isLeader(null)).toBe(false)
  })
})

describe('the lens count printed beside every composite', () => {
  it('says how many of how many, so a one-lens score cannot read as a full one', () => {
    expect(lensesLabel(1, 5)).toBe('1 of 5 lenses')
    expect(lensesLabel(2, 5)).toBe('2 of 5 lenses')
    expect(lensesLabel(5, 5)).toBe('5 of 5 lenses')
  })
  it('says "not yet scored" for a row the scorer has not reached — never "0 of 5"', () => {
    expect(lensesLabel(null, 5)).toBe('not yet scored')
    expect(lensesLabel(undefined, 5)).toBe('not yet scored')
    expect(lensesShort(null, 5)).toBe('—')
  })
  it('drops the denominator rather than guessing one when no weight table was read', () => {
    expect(lensesLabel(2, 0)).toBe('2 lenses')
    expect(lensesShort(2, 0)).toBe('2')
  })
  it('abbreviates to n/m at table density', () => {
    expect(lensesShort(2, 5)).toBe('2/5')
  })
})

describe('peer groups', () => {
  it('reads the score row’s token as words on both axes', () => {
    expect(peerGroupLabel('equity:sector')).toBe('Equity · Sector')
    expect(peerGroupLabel('alternative:options_income')).toBe('Alternative · Options income')
    expect(peerGroupLabel('equity:country')).toBe('Equity · Country')
  })
  it('does not repeat itself when the two axes carry the same word', () => {
    expect(peerGroupLabel('fixed_income:fixed_income')).toBe('Fixed income')
  })
  it('reads the asset-group fallback a small strategy bucket lands in', () => {
    expect(peerGroupLabel('equity')).toBe('Equity')
    expect(peerGroupLabel('mega')).toBe('Mega cap')
  })
  it('names the unclassified queue instead of hiding it', () => {
    expect(peerGroupLabel(null)).toBe('Unclassified')
    expect(peerGroupLabel('unclassified')).toBe('Unclassified')
    expect(peerGroupLabel('equity:unclassified')).toBe('Equity · Unclassified')
  })
  it('falls back to the classification for a fund with no score row, and to Unclassified with neither', () => {
    expect(peerGroupOf({ peer_group: 'equity', strategy: 'sector', class_asset_class: 'equity' })).toBe('equity')
    expect(peerGroupOf({ peer_group: null, strategy: 'sector', class_asset_class: 'equity' })).toBe('equity:sector')
    expect(peerGroupOf({ peer_group: null, strategy: null, class_asset_class: null })).toBe('unclassified')
  })
  it('spells the sentence the decile chip is shorthand for', () => {
    expect(rankSentence(4, 34, 'equity:sector')).toBe('ranked 4 of 34 in Equity · Sector')
    expect(rankSentence(null, 34, 'equity:sector')).toBe('not ranked in Equity · Sector')
    expect(rankSentence(1, 0, null)).toBe('not ranked in Unclassified')
  })
})

describe('conviction tiers', () => {
  it('prints the ladder in words, never the database token', () => {
    expect(Object.keys(TIER_LABEL)).toEqual(['HIGHEST', 'HIGH', 'MEDIUM', 'WATCH', 'BELOW_THRESHOLD'])
    expect(tierLabel('MEDIUM')).toBe('Medium')
    expect(tierLabel('BELOW_THRESHOLD')).toBe('Below threshold')
  })
  it('is an em dash for a row with no tier — not "below threshold", which is a verdict', () => {
    expect(tierLabel(null)).toBe('—')
    expect(tierLabel('')).toBe('—')
  })
})

describe('the relative-strength tint', () => {
  it('saturates at ±20 percent — at the shared ceiling, never at a solid colour', () => {
    // 100% of --color-pos under near-black ink was 3.9:1; the ceiling keeps every step over 10:1.
    expect(rsTint('0.2')).toBe(`color-mix(in srgb, var(--color-pos) ${CEILING.toFixed(1)}%, transparent)`)
    expect(rsTint('0.9')).toBe(rsTint('0.2'))
    expect(rsTint('-0.1')).toContain('var(--color-neg)')
    expect(rsTint('0.1')).toContain('var(--color-pos)')
    // The ramp is not linear: half the magnitude is more than half the tint, so a small lead shows.
    const pct = (s: string | undefined) => Number(/([\d.]+)%/.exec(s ?? '')?.[1])
    expect(pct(rsTint('0.1'))).toBeGreaterThan(CEILING / 2)
    expect(pct(rsTint('0.1'))).toBeLessThan(CEILING)
  })
  it('has no tint at all for a window an instrument is too young to have', () => {
    expect(rsTint(null)).toBeUndefined()
    expect(rsTint('')).toBeUndefined()
  })
})

describe('ordering and the universe side', () => {
  it('keeps an unmeasured value null so the sort puts it last instead of at zero', () => {
    expect(orderBy(null)).toBeNull()
    expect(orderBy('')).toBeNull()
    expect(orderBy('0')).toBe(0)
  })
  it('puts a row in the default view only when the snapshot said so', () => {
    expect(universeSide({ in_universe: true })).toBe('in')
    expect(universeSide({ in_universe: false })).toBe('out')
    expect(universeSide({ in_universe: null })).toBe('out')
  })
})

describe('the derivation tree', () => {
  it('knows each lens’s sub-score columns, per market', () => {
    expect(lensSubs('etf', 'technical')).toEqual(['tech_trend', 'tech_rs_spy', 'tech_rs_peer', 'tech_structure'])
    expect(lensSubs('stock', 'technical')).toEqual(['tech_trend', 'tech_rs', 'tech_vol_contraction', 'tech_volume'])
  })
  it('returns none for a lens the journal has no subs for, rather than throwing', () => {
    expect(lensSubs('etf', 'fundamental')).toEqual([])
  })
})
