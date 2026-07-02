import { describe, it, expect } from 'vitest'
import { pctBand, stableDays, rankSwing, type RankSlice } from '../rankHistory'

// REAL daily rank series (atlas_foundation.fund_rank_daily) for the #1 India Small-Cap
// fund, ascending by date — NO synthetic data (rule #0). It sits at rank 1 except a single
// dip to rank 2 on 2026-06-22, so it exercises the trailing-stability + swing logic.
const SMALLCAP_LEADER: RankSlice[] = [
  { d: '2026-06-11', r: 1, s: 41 }, { d: '2026-06-12', r: 1, s: 41 },
  { d: '2026-06-15', r: 1, s: 41 }, { d: '2026-06-16', r: 1, s: 41 },
  { d: '2026-06-17', r: 1, s: 41 }, { d: '2026-06-18', r: 1, s: 41 },
  { d: '2026-06-19', r: 1, s: 41 }, { d: '2026-06-22', r: 2, s: 41 },
  { d: '2026-06-23', r: 1, s: 41 }, { d: '2026-06-24', r: 1, s: 41 },
  { d: '2026-06-25', r: 1, s: 41 }, { d: '2026-06-29', r: 1, s: 40 },
]

describe('pctBand', () => {
  it('classifies within-category percentile (best fund is always Top 10%)', () => {
    expect(pctBand(1, 1)).toBe('Top 10%')
    expect(pctBand(1, 40)).toBe('Top 10%')
    expect(pctBand(5, 50)).toBe('Top 10%') // (5-1)/50 = 0.08
    expect(pctBand(6, 50)).toBe('Top 20%') // 0.10 -> next band
    expect(pctBand(10, 50)).toBe('Top 20%')
    expect(pctBand(11, 50)).toBe('Top 50%') // 0.20 -> next band
    expect(pctBand(25, 50)).toBe('Top 50%')
    expect(pctBand(26, 50)).toBe('Bottom 50%') // 0.50 -> next band
    expect(pctBand(50, 50)).toBe('Bottom 50%')
  })
  it('is null when unranked or cohort empty', () => {
    expect(pctBand(null, 40)).toBeNull()
    expect(pctBand(3, 0)).toBeNull()
  })
})

describe('stableDays', () => {
  it('counts the trailing run of the latest rank (days held at current rank)', () => {
    // latest rank 1; held since 2026-06-23 (after the 06-22 dip) -> 4 observations.
    expect(stableDays(SMALLCAP_LEADER)).toBe(4)
  })
  it('is 1 when the rank just changed on the latest day', () => {
    expect(stableDays([{ d: 'a', r: 5, s: 9 }, { d: 'b', r: 3, s: 9 }])).toBe(1)
  })
  it('counts the whole series when the rank never changed', () => {
    expect(stableDays([{ d: 'a', r: 2, s: 9 }, { d: 'b', r: 2, s: 9 }, { d: 'c', r: 2, s: 9 }])).toBe(3)
  })
  it('is 0 for an empty series', () => {
    expect(stableDays([])).toBe(0)
  })
})

describe('rankSwing', () => {
  it('returns max-min rank over the trailing N calendar days', () => {
    // Full 90d window includes the rank-2 dip -> swing of 1.
    expect(rankSwing(SMALLCAP_LEADER, 90)).toBe(1)
  })
  it('shrinks the window: last 5 days excludes the 06-22 dip -> swing 0', () => {
    // From 2026-06-29, >= 2026-06-24: ranks [1,1,1] -> 0.
    expect(rankSwing(SMALLCAP_LEADER, 5)).toBe(0)
  })
  it('is null for an empty series', () => {
    expect(rankSwing([], 30)).toBeNull()
  })
})
