// Smoke tests for getMarketsRsPage.
//
// Mocks @/lib/db so no live Postgres connection is needed.
// Verifies: row mapping, hero readout derivation, grade computation.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import {
  getMarketsRsPage,
  deriveHeroReadouts,
  deriveIndiaRsGrade,
} from '../markets_rs'
import {
  baselineStalenessDays,
  MARKETS_RS_STALE_THRESHOLD_DAYS,
} from '@/lib/v6/markets-staleness'

// ---------------------------------------------------------------------------
// Fixture: 9-row grid (realistic subset — all 9 baselines)
// ---------------------------------------------------------------------------

function makeRow(overrides: Record<string, unknown>) {
  return {
    rank_order: 1,
    baseline_name: 'Nifty 50',
    latest_close_inr: '24000.00',
    ret_1w:   '0.006',
    ret_1m:   '0.004',
    ret_3m:   '0.052',
    ret_6m:   '0.126',
    ret_12m:  '0.198',
    rank_1w:  3,
    rank_1m:  5,
    rank_3m:  3,
    rank_6m:  2,
    rank_12m: 2,
    as_of_date: '2026-05-26',
    refreshed_at: '2026-05-26T20:05:00Z',
    ...overrides,
  }
}

const NINE_ROWS = [
  makeRow({ rank_order: 1, baseline_name: 'Nifty 50',           ret_1w: '0.006', ret_3m: '0.052', rank_1w: 3, rank_1m: 5, rank_3m: 3, rank_6m: 2 }),
  makeRow({ rank_order: 2, baseline_name: 'Nifty 100',          ret_1w: '0.005', ret_3m: '0.048', rank_1w: 4, rank_1m: 6, rank_3m: 4, rank_6m: 3 }),
  makeRow({ rank_order: 3, baseline_name: 'Nifty Midcap 150',   ret_1w: '-0.013', ret_3m: '-0.042', rank_1w: 7, rank_1m: 8, rank_3m: 7, rank_6m: 5 }),
  makeRow({ rank_order: 4, baseline_name: 'Nifty Smallcap 250', ret_1w: '-0.021', ret_3m: '-0.087', rank_1w: 8, rank_1m: 9, rank_3m: 9, rank_6m: 7 }),
  makeRow({ rank_order: 5, baseline_name: 'Nifty 500',          ret_1w: '-0.009', ret_1m: '-0.018', ret_3m: '-0.004', ret_6m: '0.096', rank_1w: 6, rank_1m: 7, rank_3m: 6, rank_6m: 4 }),
  makeRow({ rank_order: 6, baseline_name: 'Gold (GOLDBEES)',    ret_1w: '0.024',  ret_3m: '0.094',  rank_1w: 1, rank_1m: 1, rank_3m: 1, rank_6m: 1 }),
  makeRow({ rank_order: 7, baseline_name: 'S&P 500',            ret_1w: '0.014',  ret_3m: '0.068',  rank_1w: 2, rank_1m: 2, rank_3m: 2, rank_6m: 4 }),
  makeRow({ rank_order: 8, baseline_name: 'MSCI World (URTH)',  ret_1w: '0.008',  ret_3m: '0.043',  rank_1w: 5, rank_1m: 4, rank_3m: 5, rank_6m: 6 }),
  makeRow({ rank_order: 9, baseline_name: 'MSCI EM (VWO proxy)',ret_1w: '0.004',  ret_3m: '0.027',  rank_1w: 6, rank_1m: 3, rank_3m: 5, rank_6m: 7 }),
]

// ---------------------------------------------------------------------------
// Tests: getMarketsRsPage
// ---------------------------------------------------------------------------

describe('getMarketsRsPage', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns 9 rows with all numeric fields coerced', async () => {
    sqlMock.mockResolvedValueOnce(NINE_ROWS)
    const result = await getMarketsRsPage()
    expect(result.grid).toHaveLength(9)
    const gold = result.grid.find(r => r.baseline_name.includes('Gold'))
    expect(gold).toBeDefined()
    expect(typeof gold!.ret_1w).toBe('number')
    expect(gold!.ret_1w).toBeCloseTo(0.024)
    expect(gold!.rank_1w).toBe(1)
  })

  it('derives today_leader from rank_1w === 1', async () => {
    sqlMock.mockResolvedValueOnce(NINE_ROWS)
    const result = await getMarketsRsPage()
    expect(result.hero.today_leader).toBe('Gold (GOLDBEES)')
  })

  it('derives india_rank_1m from Nifty 500 row', async () => {
    sqlMock.mockResolvedValueOnce(NINE_ROWS)
    const result = await getMarketsRsPage()
    expect(result.hero.india_rank_1m).toBe(7)
  })

  it('computes large_vs_midsmall_spread_3m correctly', async () => {
    sqlMock.mockResolvedValueOnce(NINE_ROWS)
    const result = await getMarketsRsPage()
    // Nifty 100 ret_3m = 0.048; avg(Midcap150=-0.042, Smallcap250=-0.087) = -0.0645
    // spread = (0.048 - (-0.0645)) * 100 = 11.25pp
    expect(result.hero.large_vs_midsmall_spread_3m_pp).toBeCloseTo(11.25, 1)
  })

  it('derives india_rs_grade from Nifty 500 rank avg', async () => {
    sqlMock.mockResolvedValueOnce(NINE_ROWS)
    const result = await getMarketsRsPage()
    // Nifty 500: rank_1m=7, rank_3m=6, rank_6m=4 → avg=5.67 → C
    expect(result.hero.india_rs_grade).toBe('C')
  })

  it('returns empty grid when DB returns 0 rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const result = await getMarketsRsPage()
    expect(result.grid).toHaveLength(0)
    expect(result.hero.today_leader).toBeNull()
  })

  it('handles null ret_ values gracefully', async () => {
    const rowWithNulls = makeRow({ ret_1w: null, rank_1w: null })
    sqlMock.mockResolvedValueOnce([rowWithNulls])
    const result = await getMarketsRsPage()
    expect(result.grid[0].ret_1w).toBeNull()
    expect(result.grid[0].rank_1w).toBeNull()
  })

  it('reports the freshest (max) as_of_date, not the first row when a baseline lags', async () => {
    // Prod reality: MSCI EM proxy lags the NSE close by weeks. The header stamp
    // must reflect the freshest baseline, never an arbitrary (e.g. first) row.
    const rows = [
      makeRow({ rank_order: 1, baseline_name: 'Nifty 50',            as_of_date: '2026-05-26' }),
      makeRow({ rank_order: 2, baseline_name: 'Nifty 100',           as_of_date: '2026-05-29' }),
      makeRow({ rank_order: 9, baseline_name: 'MSCI EM (VWO proxy)', as_of_date: '2026-04-24' }),
    ]
    sqlMock.mockResolvedValueOnce(rows)
    const result = await getMarketsRsPage()
    expect(result.as_of_date).toBe('2026-05-29')
  })
})

// ---------------------------------------------------------------------------
// Tests: baselineStalenessDays (per-baseline staleness honesty)
// ---------------------------------------------------------------------------

describe('baselineStalenessDays', () => {
  it('returns the calendar-day lag of a baseline behind the freshest', () => {
    expect(baselineStalenessDays('2026-04-24', '2026-05-29')).toBe(35)
  })

  it('returns 0 for the freshest baseline itself', () => {
    expect(baselineStalenessDays('2026-05-29', '2026-05-29')).toBe(0)
  })

  it('returns 1 for the normal US 1-day timezone lag', () => {
    expect(baselineStalenessDays('2026-05-28', '2026-05-29')).toBe(1)
  })

  it('returns null when either date is missing or unparseable', () => {
    expect(baselineStalenessDays(null, '2026-05-29')).toBeNull()
    expect(baselineStalenessDays('2026-05-29', null)).toBeNull()
    expect(baselineStalenessDays('not-a-date', '2026-05-29')).toBeNull()
  })

  it('threshold flags the weeks-stale EM proxy but not the 1-day US lag', () => {
    expect(baselineStalenessDays('2026-04-24', '2026-05-29')! > MARKETS_RS_STALE_THRESHOLD_DAYS).toBe(true)
    expect(baselineStalenessDays('2026-05-28', '2026-05-29')! > MARKETS_RS_STALE_THRESHOLD_DAYS).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Tests: deriveIndiaRsGrade (unit)
// ---------------------------------------------------------------------------

describe('deriveIndiaRsGrade', () => {
  it('returns A when avg rank ≤ 2.5', () => {
    expect(deriveIndiaRsGrade(1, 2, 2)).toBe('A')
    expect(deriveIndiaRsGrade(2, 2, 3)).toBe('A')
  })

  it('returns B when avg rank ≤ 4.5', () => {
    expect(deriveIndiaRsGrade(3, 4, 5)).toBe('B')
    expect(deriveIndiaRsGrade(4, 4, 4)).toBe('B')
  })

  it('returns C when avg rank ≤ 6.5', () => {
    expect(deriveIndiaRsGrade(7, 6, 4)).toBe('C')
    expect(deriveIndiaRsGrade(5, 7, 7)).toBe('C')
  })

  it('returns D when avg rank > 6.5', () => {
    expect(deriveIndiaRsGrade(8, 8, 7)).toBe('D')
    expect(deriveIndiaRsGrade(9, 9, 9)).toBe('D')
  })

  it('returns null when any rank is null', () => {
    expect(deriveIndiaRsGrade(null, 5, 4)).toBeNull()
    expect(deriveIndiaRsGrade(3, null, 4)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Tests: deriveHeroReadouts (unit)
// ---------------------------------------------------------------------------

describe('deriveHeroReadouts', () => {
  it('returns all nulls for empty grid', () => {
    const hero = deriveHeroReadouts([])
    expect(hero.today_leader).toBeNull()
    expect(hero.india_rank_1m).toBeNull()
    expect(hero.large_vs_midsmall_spread_3m_pp).toBeNull()
    expect(hero.india_rs_grade).toBeNull()
  })
})
