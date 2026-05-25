// Smoke test for getSectorsForDate.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getSectorsForDate } from '../sectors'

describe('getSectorsForDate', () => {
  beforeEach(() => sqlMock.mockReset())

  it('maps rows and assigns rank by row order', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        sector_name: 'Capital Goods',
        sector_state: 'Overweight',
        bottomup_state: 'Overweight',
        topdown_state: 'Neutral',
        bottomup_rs_state: 'Overweight_RS',
        bottomup_momentum_state: 'Improving',
        participation_rs_pct: '18.75',
        bottomup_ret_1m: '0.04',
        bottomup_ret_3m: '0.11',
        bottomup_rs_3m_nifty500: '0.18',
        participation_50: '62.5',
        constituent_count: 16,
      },
      {
        sector_name: 'Banking',
        sector_state: 'Avoid',
        bottomup_state: 'Avoid',
        topdown_state: 'Avoid',
        bottomup_rs_state: 'Avoid_RS',
        bottomup_momentum_state: 'Deteriorating',
        participation_rs_pct: '0.00',
        bottomup_ret_1m: '-0.02',
        bottomup_ret_3m: '-0.05',
        bottomup_rs_3m_nifty500: '-0.06',
        participation_50: '5.0',
        constituent_count: 20,
      },
    ])
    const out = await getSectorsForDate('2026-05-22')
    expect(out).toHaveLength(2)
    expect(out[0].sector_name).toBe('Capital Goods')
    expect(out[0].rank).toBe(1)
    expect(out[0].sector_state).toBe('Overweight')
    // participation_50 is 0..100; divide by 100 for breadth_pct_stage_2
    expect(out[0].breadth_pct_stage_2).toBeCloseTo(0.625)
    expect(out[1].rank).toBe(2)
    expect(out[1].sector_state).toBe('Avoid')
  })

  it('returns [] when nothing in DB', async () => {
    sqlMock.mockResolvedValueOnce([])
    expect(await getSectorsForDate('1999-01-01')).toEqual([])
  })
})
