// Query-layer tests for /calls (Page 08) — realized-excess unit normalization.
//
// mv_calls_performance stores realized_excess_pct in PERCENTAGE POINTS
// (round(realized * 100, 2)), while predicted_excess is a decimal fraction and
// the whole UI renders excess via fmtSignedPct (×100, expecting a fraction).
// Passing the MV's pp value straight through overstated realized excess by 100×
// (e.g. +0.69% rendered as +69%). These tests lock the pp→fraction normalization.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getCallsLedger, getCallsHero, getMatrix24Cells, getCumulativeExcessSeries } from '../calls'

beforeEach(() => {
  sqlMock.mockReset()
})

describe('getCallsLedger — realized_excess unit normalization', () => {
  it('converts MV realized_excess_pct (percentage points) to a decimal fraction; leaves predicted_excess untouched', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        signal_call_id: 'abc12345',
        symbol: 'RELIANCE',
        company_name: 'Reliance Industries',
        cap_tier: 'Large',
        tenure: '1m',
        action: 'POSITIVE',
        cell_name: null,
        entry_date: '2026-05-20',
        days_in_position: '9',
        predicted_excess: '-0.0312', // decimal fraction (must pass through unchanged)
        realized_excess_pct: '0.69', // percentage points in the MV
        is_hit: true,
        status: 'in_flight',
      },
    ])
    const [row] = await getCallsLedger(10)
    expect(row.realized_excess_pct).toBeCloseTo(0.0069, 6) // 0.69 pp → 0.0069 fraction
    expect(row.predicted_excess).toBeCloseTo(-0.0312, 6) // predicted untouched
  })

  it('keeps null realized as null (no 0/NaN)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        signal_call_id: 'def67890',
        symbol: 'TCS',
        company_name: 'TCS',
        cap_tier: 'Large',
        tenure: '3m',
        action: 'NEGATIVE',
        cell_name: null,
        entry_date: '2026-05-28',
        days_in_position: '2',
        predicted_excess: null,
        realized_excess_pct: null,
        is_hit: null,
        status: 'in_flight',
      },
    ])
    const [row] = await getCallsLedger(10)
    expect(row.realized_excess_pct).toBeNull()
    expect(row.predicted_excess).toBeNull()
  })
})

describe('getCallsHero — realized normalization', () => {
  it('normalizes avg_realized_excess pp→fraction but leaves overall_hit_rate (already a fraction)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        total_calls: '636',
        open_calls: '636',
        closed_calls: '0',
        buy_calls: '109',
        avoid_calls: '527',
        avg_realized_excess: '1.23', // pp
        overall_hit_rate: '0.49', // already a fraction
        data_as_of: '2026-05-29',
      },
    ])
    const hero = await getCallsHero()
    expect(hero.avg_realized_excess).toBeCloseTo(0.0123, 6)
    expect(hero.overall_hit_rate).toBeCloseTo(0.49, 6)
  })
})

describe('getMatrix24Cells / getCumulativeExcessSeries — realized normalization', () => {
  it('normalizes avg_realized_excess pp→fraction in the matrix', async () => {
    sqlMock.mockResolvedValueOnce([
      { cap_tier: 'Large', tenure: '1m', action: 'POSITIVE', call_count: '12', hit_rate: '0.58', avg_realized_excess: '0.84' },
    ])
    const cells = await getMatrix24Cells()
    expect(cells[0].avg_realized_excess).toBeCloseTo(0.0084, 6)
    expect(cells[0].hit_rate).toBeCloseTo(0.58, 6)
  })

  it('normalizes the cumulative excess series pp→fraction', async () => {
    sqlMock.mockResolvedValueOnce([
      { entry_date: '2026-05-29', avg_realized_excess: '2.5' },
    ])
    const series = await getCumulativeExcessSeries()
    expect(series[0].avg_realized_excess).toBeCloseTo(0.025, 6)
  })
})
