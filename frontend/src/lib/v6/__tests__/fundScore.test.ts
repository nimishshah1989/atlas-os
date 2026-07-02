import { describe, it, expect } from 'vitest'
import { fundComposite, fundCompositeContributions, rankFundsInCategory } from '../fundScore'

// Fund composite = the SAME glass-box blend used for sectors/stocks
// (0.30·Tech + 0.25·Fund + 0.25·Flow + 0.20·Cat, renormalised over present lenses),
// applied to the fund's holdings-weighted lens vector. Fixtures below are REAL
// holdings-weighted lens vectors pulled from atlas_foundation (snapshot 2026-06-26)
// for three India Multi-Cap funds — NO synthetic inputs (rule #0).
const BANK_OF_INDIA = { v_tech: 62.09, v_fund: 54.47, v_flow: 25.25, v_cat: 48.9 }
const GROWW = { v_tech: 68.61, v_fund: 63.8, v_flow: 23.52, v_cat: 47.95 }
const HSBC = { v_tech: 66.47, v_fund: 59.92, v_flow: 23.64, v_cat: 48.41 }

describe('fundComposite', () => {
  it('blends the lens vector with sector weights (all lenses present → plain weighted sum)', () => {
    // 0.30*62.09 + 0.25*54.47 + 0.25*25.25 + 0.20*48.90 = 48.34
    expect(fundComposite(BANK_OF_INDIA)).toBeCloseTo(48.34, 2)
    expect(fundComposite(GROWW)).toBeCloseTo(52.0, 2)
    expect(fundComposite(HSBC)).toBeCloseTo(50.514, 2)
  })

  it('ranks HSBC above Bank of India — the transparent composite matches what the table shows', () => {
    // The legacy scorecard ranked Bank of India #1 on a hidden NAV-based score; the
    // native composite correctly reflects the visible lenses where HSBC is stronger.
    expect(fundComposite(HSBC)!).toBeGreaterThan(fundComposite(BANK_OF_INDIA)!)
    expect(fundComposite(GROWW)!).toBeGreaterThan(fundComposite(HSBC)!)
  })

  it('renormalises weights over present lenses when one is missing', () => {
    // Flow missing → weights renormalise over tech/fund/cat (0.30/0.25/0.20, tw=0.75).
    const v = { v_tech: 60, v_fund: 40, v_flow: null, v_cat: 50 }
    const expected = (0.3 * 60 + 0.25 * 40 + 0.2 * 50) / 0.75
    expect(fundComposite(v)).toBeCloseTo(expected, 6)
  })

  it('returns null when no conviction lens is present', () => {
    expect(fundComposite({ v_tech: null, v_fund: null, v_flow: null, v_cat: null })).toBeNull()
  })
})

describe('fundCompositeContributions', () => {
  it('contributions sum to the composite and are ordered Tech, Fund, Flow, Cat', () => {
    const contribs = fundCompositeContributions(HSBC)
    expect(contribs.map((c) => c.short)).toEqual(['Tech', 'Fund', 'Flow', 'Cat'])
    const sum = contribs.reduce((a, c) => a + c.contrib, 0)
    expect(sum).toBeCloseTo(fundComposite(HSBC)!, 6)
  })
})

describe('rankFundsInCategory', () => {
  const mk = (mstar_id: string, v: typeof HSBC, breadth = 0) => ({
    mstar_id, category: 'India Fund Multi-Cap', breadth, composite: fundComposite(v),
  })

  it('ranks within category by composite desc with N/M over the scored cohort', () => {
    const ranked = rankFundsInCategory([mk('boi', BANK_OF_INDIA), mk('groww', GROWW), mk('hsbc', HSBC)])
    const byId = Object.fromEntries(ranked.map((r) => [r.mstar_id, r]))
    expect(byId.groww.cat_rank).toBe(1)
    expect(byId.hsbc.cat_rank).toBe(2)
    expect(byId.boi.cat_rank).toBe(3)
    expect(ranked.every((r) => r.cat_size === 3)).toBe(true)
  })

  it('assigns unique sequential ranks — no two funds share rank 1', () => {
    const ranked = rankFundsInCategory([mk('a', HSBC), mk('b', HSBC)]) // identical composite
    const ranks = ranked.map((r) => r.cat_rank).sort()
    expect(ranks).toEqual([1, 2])
  })

  it('breaks composite ties by breadth desc', () => {
    const ranked = rankFundsInCategory([mk('low', HSBC, 0.1), mk('high', HSBC, 0.9)])
    expect(ranked.find((r) => r.mstar_id === 'high')!.cat_rank).toBe(1)
  })

  it('leaves unscored funds without a rank but still counts the scored cohort size', () => {
    const unscored = { mstar_id: 'x', category: 'India Fund Multi-Cap', breadth: 0, composite: null }
    const ranked = rankFundsInCategory([mk('hsbc', HSBC), unscored])
    const byId = Object.fromEntries(ranked.map((r) => [r.mstar_id, r]))
    expect(byId.x.cat_rank).toBeNull()
    expect(byId.hsbc.cat_rank).toBe(1)
    expect(byId.hsbc.cat_size).toBe(1)
  })
})
