// Smoke test for getMarketsRsPage — locks shape + hero derivations.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getMarketsRsPage } from '../markets-rs'

describe('getMarketsRsPage', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns empty baselines + null hero when no rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const p = await getMarketsRsPage()
    expect(p.baselines).toEqual([])
    expect(p.as_of_date).toBeNull()
    expect(p.hero.today_leader).toBeNull()
    expect(p.hero.india_rank_1m).toBeNull()
    expect(p.hero.large_vs_midsmall_spread_3m).toBeNull()
    expect(p.hero.india_rs_grade).toBeNull()
  })

  it('parses string-numerics, derives 1w leader, india_rank_1m, spread, and grade', async () => {
    sqlMock.mockResolvedValueOnce([
      // Nifty 500 ranks 1m=3, 3m=2, 6m=2 → avg=2.33 → grade A
      {
        rank_order: 1, baseline_name: 'Nifty 500',
        latest_close_inr: '24500.50', as_of_date: '2026-05-22',
        ret_1w: '0.02', ret_1m: '0.05', ret_3m: '0.08', ret_6m: '0.12', ret_12m: '0.20',
        rank_1w: 2, rank_1m: 3, rank_3m: 2, rank_6m: 2, rank_12m: 3,
      },
      // Nifty 100 = large
      {
        rank_order: 2, baseline_name: 'Nifty 100',
        latest_close_inr: '23000.00', as_of_date: '2026-05-22',
        ret_1w: '0.01', ret_1m: '0.04', ret_3m: '0.10', ret_6m: '0.11', ret_12m: '0.18',
        rank_1w: 3, rank_1m: 4, rank_3m: 3, rank_6m: 3, rank_12m: 4,
      },
      // Midcap
      {
        rank_order: 3, baseline_name: 'Nifty Midcap 150',
        latest_close_inr: '20000.00', as_of_date: '2026-05-22',
        ret_1w: '0.03', ret_1m: '0.06', ret_3m: '0.06', ret_6m: '0.10', ret_12m: '0.22',
        rank_1w: 1, rank_1m: 2, rank_3m: 4, rank_6m: 4, rank_12m: 2,
      },
      // Smallcap
      {
        rank_order: 4, baseline_name: 'Nifty Smallcap 250',
        latest_close_inr: '18000.00', as_of_date: '2026-05-22',
        ret_1w: '0.04', ret_1m: '0.07', ret_3m: '0.04', ret_6m: '0.09', ret_12m: '0.25',
        rank_1w: 4, rank_1m: 1, rank_3m: 5, rank_6m: 5, rank_12m: 1,
      },
    ])

    const p = await getMarketsRsPage()
    expect(p.as_of_date).toBe('2026-05-22')
    expect(p.baselines).toHaveLength(4)
    // numeric coercion
    expect(p.baselines[0].ret_1m).toBeCloseTo(0.05)
    expect(p.baselines[0].latest_close_inr).toBeCloseTo(24500.5)
    // hero derivations
    expect(p.hero.today_leader).toBe('Nifty Midcap 150') // rank_1w === 1
    expect(p.hero.india_rank_1m).toBe(3) // Nifty 500's rank_1m
    // spread_3m = (0.10 - (0.06+0.04)/2) * 100 = (0.10 - 0.05) * 100 = 5
    expect(p.hero.large_vs_midsmall_spread_3m).toBeCloseTo(5.0)
    // avg rank = (3+2+2)/3 = 2.33 → A
    expect(p.hero.india_rs_grade).toBe('A')
  })

  it('coerces null numerics to null without throwing', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        rank_order: 1, baseline_name: 'Nifty 500',
        latest_close_inr: null, as_of_date: '2026-05-22',
        ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
        rank_1w: null, rank_1m: null, rank_3m: null, rank_6m: null, rank_12m: null,
      },
    ])
    const p = await getMarketsRsPage()
    expect(p.baselines[0].latest_close_inr).toBeNull()
    expect(p.baselines[0].ret_1m).toBeNull()
    expect(p.hero.today_leader).toBeNull()
    expect(p.hero.india_rs_grade).toBeNull()
  })
})
