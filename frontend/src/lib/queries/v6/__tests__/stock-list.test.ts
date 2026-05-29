// Smoke test for getStockListPage — locks shape from atlas.mv_stock_list_v6.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getStockListPage } from '../stock-list'

describe('getStockListPage', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns empty array + null as_of_date when no rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const p = await getStockListPage()
    expect(p.rows).toEqual([])
    expect(p.as_of_date).toBeNull()
  })

  it('coerces numeric strings to numbers, passes through text fields', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        instrument_id: '11111111-1111-1111-1111-111111111111',
        symbol: 'RELIANCE',
        company_name: 'Reliance Industries Limited',
        sector: 'Energy',
        tier: 'Large',
        in_nifty_50: true,
        in_nifty_100: true,
        in_nifty_500: true,
        composite_score: '7.85',
        confidence_band: 'HIGH',
        backing_ic: '0.072500',
        action: 'POSITIVE',
        best_cell_name: 'Large 6m BUY signal',
        predicted_excess: '0.124500',
        cross_cell_depth: 3,
        tape_1m: 'POS',
        tape_3m: 'POS',
        tape_6m: 'POS',
        tape_12m: 'POS',
        ret_1m: '0.0420',
        ret_3m: '0.1100',
        ret_6m: '0.1850',
        ret_12m: '0.3200',
        rs_1m_nifty500: '0.0210',
        rs_3m_nifty500: '0.0540',
        rs_pctile_3m: '0.8800',
        realized_vol_63: '0.2120',
        max_drawdown_252: '-0.0850',
        family_trend: 'UPTREND',
        family_volatility: 'NORMAL',
        family_volume: 'EXPANDING',
        family_path: 'SMOOTH',
        family_sector: 'LEADING',
        as_of_date: '2026-05-22',
        refreshed_at: '2026-05-23T14:30:00Z',
      },
    ])
    const p = await getStockListPage()
    expect(p.as_of_date).toBe('2026-05-22')
    expect(p.rows).toHaveLength(1)
    const r = p.rows[0]
    expect(r.symbol).toBe('RELIANCE')
    expect(r.tier).toBe('Large')
    expect(r.in_nifty_50).toBe(true)
    expect(r.composite_score).toBeCloseTo(7.85)
    expect(r.backing_ic).toBeCloseTo(0.0725)
    expect(r.predicted_excess).toBeCloseTo(0.1245)
    expect(r.cross_cell_depth).toBe(3)
    expect(r.action).toBe('POSITIVE')
    expect(r.confidence_band).toBe('HIGH')
    expect(r.tape_3m).toBe('POS')
    expect(r.ret_3m).toBeCloseTo(0.11)
    expect(r.rs_pctile_3m).toBeCloseTo(0.88)
    expect(r.realized_vol_63).toBeCloseTo(0.212)
    expect(r.max_drawdown_252).toBeCloseTo(-0.085)
    expect(r.family_trend).toBe('UPTREND')
    expect(r.family_sector).toBe('LEADING')
  })

  it('handles null numeric columns without throwing', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        instrument_id: '22222222-2222-2222-2222-222222222222',
        symbol: 'NEWSTOCK',
        company_name: 'New Stock Ltd',
        sector: null,
        tier: 'Micro',
        in_nifty_50: false,
        in_nifty_100: false,
        in_nifty_500: false,
        composite_score: null,
        confidence_band: 'LOW',
        backing_ic: null,
        action: 'NEUTRAL',
        best_cell_name: null,
        predicted_excess: null,
        cross_cell_depth: 0,
        tape_1m: 'NEU', tape_3m: 'NEU', tape_6m: 'NEU', tape_12m: 'NEU',
        ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
        rs_1m_nifty500: null, rs_3m_nifty500: null, rs_pctile_3m: null,
        realized_vol_63: null, max_drawdown_252: null,
        family_trend: null, family_volatility: null, family_volume: null,
        family_path: null, family_sector: null,
        as_of_date: '2026-05-22', refreshed_at: null,
      },
    ])
    const p = await getStockListPage()
    expect(p.rows[0].composite_score).toBeNull()
    expect(p.rows[0].predicted_excess).toBeNull()
    expect(p.rows[0].ret_3m).toBeNull()
    expect(p.rows[0].sector).toBeNull()
    expect(p.rows[0].action).toBe('NEUTRAL')
  })
})
