// Smoke test for getCallsPerformancePage — locks shape from
// atlas.mv_calls_performance.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getCallsPerformancePage } from '../calls-performance'

describe('getCallsPerformancePage', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns empty arrays + null summary when no calls', async () => {
    sqlMock.mockResolvedValueOnce([])
    const p = await getCallsPerformancePage()
    expect(p.calls).toEqual([])
    expect(p.summary.total).toBe(0)
    expect(p.summary.hit_rate).toBeNull()
    expect(p.summary.avg_realized_excess_pct).toBeNull()
  })

  it('coerces numerics + derives summary (hit_rate, avg excess, status counts)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        signal_call_id: 'c1', instrument_id: 'i1',
        symbol: 'TCS', company_name: 'Tata Consultancy',
        cell_name: 'Large 1m BUY signal', cap_tier: 'Large', tenure: '1m',
        action: 'POSITIVE', entry_date: '2026-04-22',
        confidence_unconditional: '0.7200', predicted_excess: '0.040000',
        stock_ret_pct: '5.2000', bench_ret_pct: '2.0000', realized_excess_pct: '3.2000',
        days_in_position: 30, is_hit: true, status: 'in_flight',
        refreshed_at: '2026-05-23T14:30:00Z',
      },
      {
        signal_call_id: 'c2', instrument_id: 'i2',
        symbol: 'INFY', company_name: 'Infosys',
        cell_name: 'Large 3m AVOID signal', cap_tier: 'Large', tenure: '3m',
        action: 'NEGATIVE', entry_date: '2026-04-01',
        confidence_unconditional: '0.6800', predicted_excess: '-0.030000',
        stock_ret_pct: '-2.5000', bench_ret_pct: '1.0000', realized_excess_pct: '-3.5000',
        days_in_position: 51, is_hit: true, status: 'in_flight',
        refreshed_at: '2026-05-23T14:30:00Z',
      },
      {
        signal_call_id: 'c3', instrument_id: 'i3',
        symbol: 'RELIANCE', company_name: 'Reliance',
        cell_name: 'Large 6m BUY signal', cap_tier: 'Large', tenure: '6m',
        action: 'POSITIVE', entry_date: '2026-01-01',
        confidence_unconditional: '0.5500', predicted_excess: '0.050000',
        stock_ret_pct: '1.0000', bench_ret_pct: '3.0000', realized_excess_pct: '-2.0000',
        days_in_position: 142, is_hit: false, status: 'in_flight',
        refreshed_at: '2026-05-23T14:30:00Z',
      },
    ])
    const p = await getCallsPerformancePage()
    expect(p.calls).toHaveLength(3)
    expect(p.calls[0].symbol).toBe('TCS')
    expect(p.calls[0].predicted_excess).toBeCloseTo(0.04)
    expect(p.calls[0].realized_excess_pct).toBeCloseTo(3.2)
    expect(p.calls[0].is_hit).toBe(true)

    expect(p.summary.total).toBe(3)
    expect(p.summary.hits).toBe(2)
    expect(p.summary.hit_rate).toBeCloseTo(2 / 3)
    // (3.2 + -3.5 + -2.0) / 3 = -0.7666...
    expect(p.summary.avg_realized_excess_pct).toBeCloseTo(-0.7666, 3)
    expect(p.summary.by_status['in_flight']).toBe(3)
  })

  it('handles null realized fields (e.g. brand new calls)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        signal_call_id: 'c1', instrument_id: 'i1',
        symbol: 'NEWCO', company_name: 'NewCo Ltd',
        cell_name: 'Micro 1m BUY signal', cap_tier: 'Micro', tenure: '1m',
        action: 'POSITIVE', entry_date: '2026-05-23',
        confidence_unconditional: null, predicted_excess: null,
        stock_ret_pct: null, bench_ret_pct: null, realized_excess_pct: null,
        days_in_position: 0, is_hit: false, status: 'in_flight',
        refreshed_at: '2026-05-23T14:30:00Z',
      },
    ])
    const p = await getCallsPerformancePage()
    expect(p.calls[0].realized_excess_pct).toBeNull()
    expect(p.calls[0].predicted_excess).toBeNull()
    expect(p.summary.avg_realized_excess_pct).toBeNull()
    // hit_rate is null (not 0) when zero calls have realized data —
    // counting brand-new in-flight calls as misses would be misleading.
    expect(p.summary.hit_rate).toBeNull()
  })
})
