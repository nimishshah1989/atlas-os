// Smoke test for getFundListPage — locks shape from atlas.mv_fund_list_v6.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getFundListPage } from '../fund-list'

describe('getFundListPage', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns empty rows + null as_of when no rows', async () => {
    sqlMock.mockResolvedValueOnce([])
    const p = await getFundListPage()
    expect(p.rows).toEqual([])
    expect(p.as_of_date).toBeNull()
  })

  it('coerces numerics, passes through booleans and text', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        scheme_code: 'F00001RZRD',
        isin: 'INF1234X0123',
        fund_name: 'Capitalmind Flexi Cap Dir Gr',
        amc: 'Capitalmind',
        fund_category: 'India Fund Flexi Cap',
        fund_style: 'Growth',
        broad_category: 'Equity',
        plan_type: 'Regular',
        benchmark_code: 'NIFTY500',
        aum_cr: '1250.50',
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
        peer_quartile: 'Q1',
        recommendation: 'HOLD',
        consistency_months: 18,
        nav: '125.4500',
        expense_ratio: '0.0095',
        top_holdings: [{ symbol: 'RELIANCE', pct: 8.5 }],
        sub_metrics: { sharpe_3y: 0.85 },
        eli5: 'Solid flexi cap.',
        amc_total_funds: 12,
        amc_q1_count: 5,
        amc_q4_count: 1,
        amc_avg_composite: '62.5',
        as_of_date: '2026-05-22',
        refreshed_at: '2026-05-23T14:30:00Z',
        ret_1m: '0.0123',
        ret_3m: '0.0456',
        ret_6m: '0.0890',
        ret_12m: '0.2411',
        rs_pctile_3m: '0.7647',
      },
    ])
    const p = await getFundListPage()
    expect(p.as_of_date).toBe('2026-05-22')
    expect(p.rows).toHaveLength(1)
    const r = p.rows[0]
    expect(r.scheme_code).toBe('F00001RZRD')
    expect(r.aum_cr).toBeCloseTo(1250.5)
    expect(r.composite_score).toBeCloseTo(69.44)
    expect(r.expense_ratio).toBeCloseTo(0.0095)
    expect(r.rank_in_category).toBe(3)
    expect(r.peer_quartile).toBe('Q1')
    expect(r.is_atlas_leader).toBe(false)
    expect(r.recommendation).toBe('HOLD')
    expect(r.top_holdings).toEqual([{ symbol: 'RELIANCE', pct: 8.5 }])
    expect(r.amc_total_funds).toBe(12)
    expect(r.amc_avg_composite).toBeCloseTo(62.5)
    // Period returns + RS percentile joined from atlas_fund_metrics_daily
    expect(r.ret_12m).toBeCloseTo(0.2411)
    expect(r.rs_pctile_3m).toBeCloseTo(0.7647)
  })

  it('leaves returns null when the metrics join misses (uncovered fund)', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        scheme_code: 'F0NOMETRICS', isin: null, fund_name: 'No Metrics Fund',
        amc: 'AMC', fund_category: null, fund_style: null, broad_category: null,
        plan_type: null, benchmark_code: null, aum_cr: null, composite_score: '55.0',
        risk_adjusted_return_score: null, holdings_conviction_score: null,
        style_sector_score: null, cost_manager_score: null, rank_in_category: null,
        category_size: null, is_atlas_leader: false, is_avoid: false,
        confidence_low: false, holdings_unjoinable: false, survivorship_exposure_pct: null,
        peer_quartile: null, recommendation: null, consistency_months: null, nav: null,
        expense_ratio: null, top_holdings: null, sub_metrics: null, eli5: null,
        amc_total_funds: 1, amc_q1_count: 0, amc_q4_count: 0, amc_avg_composite: null,
        as_of_date: '2026-05-29', refreshed_at: null,
        ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, rs_pctile_3m: null,
      },
    ])
    const p = await getFundListPage()
    expect(p.rows[0].composite_score).toBeCloseTo(55.0)
    expect(p.rows[0].ret_12m).toBeNull()
    expect(p.rows[0].rs_pctile_3m).toBeNull()
  })

  it('joins each fund\'s own latest metrics within a recency window, not the exact global-max date', async () => {
    // Bug: pinning the returns join to fm.nav_date = MAX(nav_date) dropped
    // returns for ~10 funds whose latest NAV publishes 1 day behind the global
    // max (a normal AMC publishing lag), even though fresh data exists.
    // Fix: DISTINCT ON over a 7-day window (one scan, ~2x faster than a
    // per-fund correlated lateral — verified via EXPLAIN ANALYZE on prod).
    sqlMock.mockResolvedValueOnce([])
    await getFundListPage()
    const strings = sqlMock.mock.calls[0][0] as readonly string[]
    const text = strings.join('?')
    expect(text).toMatch(/DISTINCT ON \(mstar_id\)/i)
    expect(text).toMatch(/7 days/)
    // Must NOT pin returns to exact equality with the global max (the bug).
    expect(text).not.toMatch(/fm\.nav_date\s*=\s*\(\s*SELECT d FROM latest_fm\s*\)/)
  })

  it('handles null JSONB + nullable numerics', async () => {
    sqlMock.mockResolvedValueOnce([
      {
        scheme_code: 'X000NULL',
        isin: null, fund_name: 'New Fund', amc: 'AMC', fund_category: null,
        fund_style: null, broad_category: 'Equity', plan_type: null,
        benchmark_code: null, aum_cr: null,
        composite_score: null, risk_adjusted_return_score: null,
        holdings_conviction_score: null, style_sector_score: null,
        cost_manager_score: null,
        rank_in_category: null, category_size: null,
        is_atlas_leader: false, is_avoid: false, confidence_low: true,
        holdings_unjoinable: true, survivorship_exposure_pct: null,
        peer_quartile: null, recommendation: null, consistency_months: null,
        nav: null, expense_ratio: null,
        top_holdings: null, sub_metrics: null, eli5: null,
        amc_total_funds: 1, amc_q1_count: 0, amc_q4_count: 0,
        amc_avg_composite: null,
        as_of_date: '2026-05-22', refreshed_at: null,
      },
    ])
    const p = await getFundListPage()
    expect(p.rows[0].composite_score).toBeNull()
    expect(p.rows[0].rank_in_category).toBeNull()
    expect(p.rows[0].top_holdings).toEqual([])
    expect(p.rows[0].sub_metrics).toBeNull()
  })
})
