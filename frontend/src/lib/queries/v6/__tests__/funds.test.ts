// Smoke test for getFundsForDate.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getFundsForDate } from '../funds'

describe('getFundsForDate', () => {
  beforeEach(() => sqlMock.mockReset())

  it('maps a scorecard row, derives style box, converts aum_cr to ₹', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        iid: 'F00001RZRD',
        code: 'F00001RZRD',
        name: 'Capitalmind Flexi Cap Dir Gr',
        category: 'India Fund Flexi Cap',
        amc: 'Capitalmind Asset Management',
        fund_style: null,
        aum_cr: '500.00',
        composite_score: '69.44',
        risk_adjusted_return_score: '75.65',
        holdings_conviction_score: '66.14',
        style_sector_score: '70.00',
        cost_manager_score: '45.80',
        rank_in_category: 1,
        category_size: 89,
        is_atlas_leader: false,
        is_avoid: false,
        confidence_low: true,
        eli5: 'Limited track record.',
        ret_1m: '0.020',
        ret_3m: '0.060',
        ret_6m: '0.120',
        ret_12m: '0.180',
        rs_pctile_3m: '0.55',
      },
    ])
    const out = await getFundsForDate('2026-05-22')
    expect(out).toHaveLength(1)
    const f = out[0]
    expect(f.code).toBe('F00001RZRD')
    // 500 crore → 500 * 1e7 ₹
    expect(f.aum_inr).toBe(5e9)
    expect(f.style_box).toEqual({ size: 'Large', style: 'Blend' }) // "flexi" → Large/Blend
    // Average band (0.30 <= 0.55 < 0.70)
    expect(f.rs_state).toBe('Average')
    expect(f.conviction_tape).toBeNull()
  })

  it('returns [] when no rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    expect(await getFundsForDate('1999-01-01')).toEqual([])
  })
})
