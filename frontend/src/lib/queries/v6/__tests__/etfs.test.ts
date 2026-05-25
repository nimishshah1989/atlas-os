// Smoke test for getEtfsForDate.
//
// We mock @/lib/db so the module loads without a live Postgres connection.
// The mock returns a fixed row set; we then assert the shape mapper builds
// the right ScreenEtf output (numeric coercion, neutral conviction tape,
// rs_state derivation).

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

const sqlMock = vi.fn()
// postgres-js exposes its tagged template as a callable default export.
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getEtfsForDate } from '../etfs'

describe('getEtfsForDate', () => {
  beforeEach(() => sqlMock.mockReset())

  it('maps a scorecard row into ScreenEtf with neutral conviction tape', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        iid: '00000000-0000-0000-0000-000000000001',
        ticker: 'HEALTHIETF',
        name: 'Nippon India ETF Nifty Healthcare',
        category: 'sector',
        composite_score: '61.64',
        matrix_conviction_score: '50.00',
        sector_strength_score: '96.55',
        tracking_quality_score: '50.00',
        aum_bracket_score: '50.00',
        liquidity_score: '50.00',
        expense_ratio_score: '50.00',
        rank_in_category: 1,
        category_size: 16,
        is_atlas_leader: true,
        eli5: 'Top sector ETF — Healthcare leading.',
        ret_1m: '0.034',
        ret_3m: '0.121',
        ret_6m: '0.205',
        ret_12m: '0.331',
        rs_pctile_3m: '0.93',
      },
    ])

    const out = await getEtfsForDate('2026-05-22')
    expect(out).toHaveLength(1)
    const e = out[0]
    expect(e.iid).toBe('00000000-0000-0000-0000-000000000001')
    expect(e.ticker).toBe('HEALTHIETF')
    expect(e.ret_1m).toBeCloseTo(0.034)
    expect(e.ret_12m).toBeCloseTo(0.331)
    // Leader because rs_pctile_3m=0.93 >= 0.90
    expect(e.rs_state).toBe('Leader')
    // ETFs don't have conviction rows yet → all neutral
    expect(e.conviction_tape['1m'].direction).toBe('NEUTRAL')
    expect(e.conviction_tape['12m'].direction).toBe('NEUTRAL')
  })

  it('returns empty array when no scorecard rows exist for the date', async () => {
    sqlMock.mockResolvedValueOnce([])
    const out = await getEtfsForDate('2099-01-01')
    expect(out).toEqual([])
  })

  it('maps null rs_pctile_3m to null rs_state', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        iid: 'x',
        ticker: 'X',
        name: null,
        category: null,
        composite_score: null,
        matrix_conviction_score: null,
        sector_strength_score: null,
        tracking_quality_score: null,
        aum_bracket_score: null,
        liquidity_score: null,
        expense_ratio_score: null,
        rank_in_category: null,
        category_size: null,
        is_atlas_leader: null,
        eli5: null,
        ret_1m: null,
        ret_3m: null,
        ret_6m: null,
        ret_12m: null,
        rs_pctile_3m: null,
      },
    ])
    const out = await getEtfsForDate('2026-05-22')
    expect(out[0].rs_state).toBeNull()
    expect(out[0].ret_1m).toBeNull()
  })
})
