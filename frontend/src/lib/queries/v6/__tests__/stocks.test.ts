// Smoke test for getStocksForDate.
//
// The function fires TWO queries — universe+metrics, then conviction rows.
// We mock the sql template to return both result sets in order.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getStocksForDate } from '../stocks'

describe('getStocksForDate', () => {
  beforeEach(() => sqlMock.mockReset())

  it('builds a 4-tenure ConvictionTape from conviction rows', async () => {
    sqlMock
      // first call: stock universe + metrics + signal_unified
      .mockResolvedValueOnce([
        {
          iid: 'iid-1',
          symbol: 'RELIANCE',
          company_name: 'Reliance Industries',
          sector: 'Energy',
          tier: 'Large',
          rs_state: 'Leader',
          engine_state: 'Stage 2',
          is_investable: true,
          ret_1m: '0.03',
          ret_3m: '0.10',
          ret_6m: '0.15',
          ret_12m: '0.22',
          rs_pctile_3m: '0.94',
        },
      ])
      // second call: conviction_daily rows
      .mockResolvedValueOnce([
        { iid: 'iid-1', tenure: '1m', verdict: 'POSITIVE', ic: '0.05', best_rule_id: 'rule-A' },
        { iid: 'iid-1', tenure: '3m', verdict: 'NEUTRAL',  ic: null,   best_rule_id: null },
        { iid: 'iid-1', tenure: '6m', verdict: 'NEGATIVE', ic: '-0.02', best_rule_id: 'rule-B' },
        { iid: 'iid-1', tenure: '12m', verdict: 'POSITIVE', ic: '0.04', best_rule_id: 'rule-C' },
      ])
    const out = await getStocksForDate('2026-05-22')
    expect(out).toHaveLength(1)
    const s = out[0]
    expect(s.iid).toBe('iid-1')
    expect(s.symbol).toBe('RELIANCE')
    expect(s.tier).toBe('Large')
    expect(s.stage).toBe('Stage 2')
    expect(s.conviction_tape['1m']).toMatchObject({ direction: 'POSITIVE', top_rule_id: 'rule-A' })
    expect(s.conviction_tape['3m']).toMatchObject({ direction: 'NEUTRAL', top_rule_id: null })
    expect(s.conviction_tape['6m']).toMatchObject({ direction: 'NEGATIVE' })
    expect(s.conviction_tape['12m'].ic).toBeCloseTo(0.04)
  })

  it('returns [] without firing second query when universe is empty', async () => {
    sqlMock.mockResolvedValueOnce([])
    const out = await getStocksForDate('1999-01-01')
    expect(out).toEqual([])
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  it('falls back to all-NEUTRAL tape when no conviction rows for the iid', async () => {
    sqlMock
      .mockResolvedValueOnce([
        {
          iid: 'iid-2',
          symbol: 'TCS',
          company_name: 'TCS',
          sector: 'IT',
          tier: 'Large',
          rs_state: null,
          engine_state: null,
          is_investable: null,
          ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
          rs_pctile_3m: null,
        },
      ])
      .mockResolvedValueOnce([]) // no conviction rows
    const out = await getStocksForDate('2026-05-22')
    expect(out[0].conviction_tape['1m'].direction).toBe('NEUTRAL')
    expect(out[0].conviction_tape['12m'].direction).toBe('NEUTRAL')
    // null is_investable defaults to true (page filters that count it)
    expect(out[0].is_investable).toBe(true)
  })
})
