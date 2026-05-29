// Smoke test for getFundDeepdive — locks shape from atlas.mv_fund_deepdive.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getFundDeepdive } from '../fund-deepdive'

describe('getFundDeepdive', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns null when scheme not found', async () => {
    sqlMock.mockResolvedValueOnce([])
    const d = await getFundDeepdive('NOT_A_FUND')
    expect(d).toBeNull()
  })

  it('parses scalars + JSONB sections', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        scheme_code: 'F000000CBK',
        isin: 'INF1234X0001',
        fund_name: 'Sample Equity Fund',
        amc: 'Sample AMC',
        fund_category: 'India Fund Flexi Cap',
        fund_style: 'Growth',
        broad_category: 'Equity',
        plan_type: 'Regular',
        benchmark_code: 'NIFTY500',
        aum_cr: '1250.50',
        inception_date: '2005-01-01',
        composite_score: '69.44',
        risk_adjusted_return_score: '72.00',
        holdings_conviction_score: '65.00',
        style_sector_score: '70.00',
        cost_manager_score: '70.00',
        rank_in_category: 3,
        category_size: 45,
        is_atlas_leader: false,
        is_avoid: false,
        confidence_low: false,
        holdings_unjoinable: false,
        survivorship_exposure_pct: '5.50',
        nav_as_of: '2026-05-22',
        holdings_as_of: '2026-04-30',
        peer_quartile: 'Q1',
        recommendation: 'HOLD',
        consistency_months: 18,
        latest_nav: '142.2640',
        expense_ratio: '0.0095',
        eli5: 'Solid flexi cap.',
        top_holdings: [
          { symbol: 'Coforge Ltd', weight_pct: 3.467, verdict: 'NEUTRAL', instrument_id: '78d24c77-6bb6-4114-8bab-0d2f598a2907' },
        ],
        sub_metrics: {
          alpha: 0, sharpe: 0.534, sortino: 0.478, calmar: 0.240,
          max_dd: 0.657, up_capture: 1, down_capture: 1,
          fund_age_years: 19.52, n_observations: 4799,
        },
        nav_12m: [{ month: '2025-05-01', nav: 142.264 }],
        recent_decisions_90d: [{ date: '2026-05-22', recommendation: 'Reduce', is_investable: false }],
        as_of_date: '2026-05-22',
        refreshed_at: '2026-05-23T14:30:00Z',
      },
    ])
    const d = await getFundDeepdive('F000000CBK')
    expect(d).not.toBeNull()
    if (!d) return
    expect(d.scheme_code).toBe('F000000CBK')
    expect(d.composite_score).toBeCloseTo(69.44)
    expect(d.aum_cr).toBeCloseTo(1250.5)
    expect(d.latest_nav).toBeCloseTo(142.264)
    expect(d.expense_ratio).toBeCloseTo(0.0095)
    expect(d.top_holdings).toHaveLength(1)
    expect(d.top_holdings[0].weight_pct).toBeCloseTo(3.467)
    expect(d.sub_metrics?.sharpe).toBeCloseTo(0.534)
    expect(d.nav_12m).toHaveLength(1)
    expect(d.nav_12m[0].nav).toBeCloseTo(142.264)
    expect(d.recent_decisions_90d).toHaveLength(1)
    expect(d.recent_decisions_90d[0].recommendation).toBe('Reduce')
    expect(d.inception_date).toBe('2005-01-01')
  })

  it('handles null JSONB gracefully', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        scheme_code: 'X000NULL',
        isin: null, fund_name: 'New Fund', amc: 'AMC',
        fund_category: null, fund_style: null, broad_category: null,
        plan_type: null, benchmark_code: null, aum_cr: null, inception_date: null,
        composite_score: null, risk_adjusted_return_score: null,
        holdings_conviction_score: null, style_sector_score: null,
        cost_manager_score: null,
        rank_in_category: null, category_size: null,
        is_atlas_leader: false, is_avoid: false, confidence_low: true,
        holdings_unjoinable: true, survivorship_exposure_pct: null,
        nav_as_of: null, holdings_as_of: null,
        peer_quartile: null, recommendation: null, consistency_months: null,
        latest_nav: null, expense_ratio: null, eli5: null,
        top_holdings: null, sub_metrics: null, nav_12m: null, recent_decisions_90d: null,
        as_of_date: '2026-05-22', refreshed_at: null,
      },
    ])
    const d = await getFundDeepdive('X000NULL')
    expect(d).not.toBeNull()
    if (!d) return
    expect(d.top_holdings).toEqual([])
    expect(d.nav_12m).toEqual([])
    expect(d.recent_decisions_90d).toEqual([])
    expect(d.sub_metrics).toBeNull()
  })
})
