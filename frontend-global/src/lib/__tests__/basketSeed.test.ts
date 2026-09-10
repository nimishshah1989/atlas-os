// src/lib/__tests__/basketSeed.test.ts — seeding a basket from a list, and the one piece of
// arithmetic that has to be exact.
//
// `basket_constituents` carries a Σ=1 trigger, so a basket whose weights sum to 999,999
// micro-fractions is refused by the database, not rounded by it. Three names cannot be weighted
// equally in fixed point — 333,333 × 3 is one short — so the remainder has to land somewhere and
// the choice has to be stated rather than discovered. It lands on the first row.
//
// Every symbol asserted on below is a real US-listed instrument already used as a fixture
// elsewhere in this suite (src/lib/__tests__/thresholds.test.ts, from the live board's payload).
import { describe, expect, it } from 'vitest'
import { equalWeights, seedRows } from '@/lib/basketDraft'

const MICRO = 1_000_000

describe('equal weights are exact, not approximately exact', () => {
  it('sums to exactly one for every basket size the builder allows', () => {
    for (let n = 1; n <= 50; n++) {
      const w = equalWeights(n)
      expect(w).toHaveLength(n)
      expect(w.reduce((a, b) => a + b, 0), `n=${n}`).toBe(MICRO)
    }
  })

  it('puts the indivisible remainder on the FIRST row, and only there', () => {
    // Three names: 333,333 each leaves 1 micro-fraction over. The first name carries 33.3334%.
    expect(equalWeights(3)).toEqual([333_334, 333_333, 333_333])
    // Seven names: 142,857 each leaves 1. Same rule.
    const seven = equalWeights(7)
    expect(seven[0] - seven[1]).toBe(1)
    expect(new Set(seven.slice(1)).size).toBe(1)
  })

  it('divides evenly when it can, with no remainder anywhere', () => {
    expect(equalWeights(4)).toEqual([250_000, 250_000, 250_000, 250_000])
    expect(equalWeights(1)).toEqual([MICRO])
  })

  it('has nothing to weight when there is nothing in the list', () => {
    expect(equalWeights(0)).toEqual([])
  })
})

describe('a ?symbols= list becomes the builder’s opening rows', () => {
  it('carries real symbols through, equal-weighted, in the order given', () => {
    expect(seedRows('SPY,IWM,XPH')).toEqual([
      { symbol: 'SPY', weightPct: '33.3334' },
      { symbol: 'IWM', weightPct: '33.3333' },
      { symbol: 'XPH', weightPct: '33.3333' },
    ])
  })

  it('upper-cases and trims, because a link is written by a person', () => {
    expect(seedRows(' spy , iwm ').map((r) => r.symbol)).toEqual(['SPY', 'IWM'])
  })

  it('keeps a symbol once — a fund listed twice is one position, not two', () => {
    expect(seedRows('FDD,FDD,XMLV').map((r) => r.symbol)).toEqual(['FDD', 'XMLV'])
  })

  it('drops what cannot be a symbol rather than carrying it into a form that will refuse it', () => {
    // BRK.B and ABR$D are real instrument_master spellings; the rest cannot be symbols.
    expect(seedRows('BRK.B,,<script>,ABR$D,a-very-long-thing-indeed').map((r) => r.symbol)).toEqual([
      'BRK.B',
      'ABR$D',
    ])
  })

  it('is empty for an absent parameter, which is the normal way the page is opened', () => {
    expect(seedRows(null)).toEqual([])
    expect(seedRows(undefined)).toEqual([])
    expect(seedRows('')).toEqual([])
  })

  it('bounds the list, so a hand-edited URL cannot open a form with a thousand rows', () => {
    const many = Array.from({ length: 80 }, (_, i) => `AA${String(i).padStart(2, '0')}`).join(',')
    expect(seedRows(many)).toHaveLength(50)
    expect(seedRows(many, 5)).toHaveLength(5)
  })
})
