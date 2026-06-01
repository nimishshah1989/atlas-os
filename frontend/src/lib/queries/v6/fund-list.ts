// frontend/src/lib/queries/v6/fund-list.ts
//
// Reads atlas.mv_fund_list_v6 — one row per mutual fund scheme with
// composite score, sub-pillars, AMC stats, and top holdings JSONB.
// ~587 funds total.
//
// MV refreshed nightly via pg_cron (Phase D).

import 'server-only'
import sql from '@/lib/db'

export type FundListRow = {
  scheme_code: string
  isin: string | null
  fund_name: string
  amc: string
  fund_category: string | null
  fund_style: string | null
  broad_category: string | null
  plan_type: string | null
  benchmark_code: string | null
  aum_cr: number | null
  composite_score: number | null
  risk_adjusted_return_score: number | null
  holdings_conviction_score: number | null
  style_sector_score: number | null
  cost_manager_score: number | null
  rank_in_category: number | null
  category_size: number | null
  is_atlas_leader: boolean
  is_avoid: boolean
  confidence_low: boolean
  holdings_unjoinable: boolean
  survivorship_exposure_pct: number | null
  peer_quartile: string | null
  recommendation: string | null
  consistency_months: number | null
  nav: number | null
  expense_ratio: number | null
  top_holdings: Array<Record<string, unknown>>
  sub_metrics: Record<string, unknown> | null
  eli5: string | null
  amc_total_funds: number
  amc_q1_count: number
  amc_q4_count: number
  amc_avg_composite: number | null
  as_of_date: string | null
  refreshed_at: string | null
  // Period returns + RS percentile, joined from atlas_fund_metrics_daily
  // (latest nav_date) by mstar_id = scheme_code. ~520/587 covered.
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_pctile_3m: number | null
  realized_vol_63: string | null
}

export type FundListPage = {
  as_of_date: string | null
  rows: FundListRow[]
}

type Row = {
  scheme_code: string
  isin: string | null
  fund_name: string
  amc: string
  fund_category: string | null
  fund_style: string | null
  broad_category: string | null
  plan_type: string | null
  benchmark_code: string | null
  aum_cr: string | null
  composite_score: string | null
  risk_adjusted_return_score: string | null
  holdings_conviction_score: string | null
  style_sector_score: string | null
  cost_manager_score: string | null
  rank_in_category: number | string | null
  category_size: number | string | null
  is_atlas_leader: boolean
  is_avoid: boolean
  confidence_low: boolean
  holdings_unjoinable: boolean
  survivorship_exposure_pct: string | null
  peer_quartile: string | null
  recommendation: string | null
  consistency_months: number | string | null
  nav: string | null
  expense_ratio: string | null
  top_holdings: Array<Record<string, unknown>> | null
  sub_metrics: Record<string, unknown> | null
  eli5: string | null
  amc_total_funds: number | string
  amc_q1_count: number | string
  amc_q4_count: number | string
  amc_avg_composite: string | null
  as_of_date: string | null
  refreshed_at: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
  realized_vol_63: string | null
}

function toNumber(s: string | number | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : parseFloat(s)
  return Number.isFinite(n) ? n : null
}

function toInt(s: number | string | null | undefined): number {
  if (s == null) return 0
  const n = typeof s === 'number' ? s : parseInt(s, 10)
  return Number.isFinite(n) ? n : 0
}

export async function getFundListPage(): Promise<FundListPage> {
  const rows = await sql<Row[]>`
    WITH latest_fm AS (SELECT MAX(nav_date) AS d FROM atlas.atlas_fund_metrics_daily)
    SELECT
      fl.scheme_code, fl.isin, fl.fund_name, fl.amc, fl.fund_category, fl.fund_style,
      fl.broad_category, fl.plan_type, fl.benchmark_code,
      fl.aum_cr::text                       AS aum_cr,
      fl.composite_score::text              AS composite_score,
      fl.risk_adjusted_return_score::text   AS risk_adjusted_return_score,
      fl.holdings_conviction_score::text    AS holdings_conviction_score,
      fl.style_sector_score::text           AS style_sector_score,
      fl.cost_manager_score::text           AS cost_manager_score,
      fl.rank_in_category, fl.category_size,
      fl.is_atlas_leader, fl.is_avoid, fl.confidence_low, fl.holdings_unjoinable,
      fl.survivorship_exposure_pct::text    AS survivorship_exposure_pct,
      fl.peer_quartile, fl.recommendation, fl.consistency_months,
      fl.nav::text                          AS nav,
      fl.expense_ratio::text                AS expense_ratio,
      fl.top_holdings, fl.sub_metrics, fl.eli5,
      fl.amc_total_funds, fl.amc_q1_count, fl.amc_q4_count,
      fl.amc_avg_composite::text            AS amc_avg_composite,
      fl.as_of_date::text                   AS as_of_date,
      fl.refreshed_at::text                 AS refreshed_at,
      fm.ret_1m::text                       AS ret_1m,
      fm.ret_3m::text                       AS ret_3m,
      fm.ret_6m::text                       AS ret_6m,
      fm.ret_12m::text                      AS ret_12m,
      fm.rs_pctile_3m::text                 AS rs_pctile_3m,
      fm.realized_vol_63::text              AS realized_vol_63
    FROM atlas.mv_fund_list_v6 fl
    -- Join each fund's OWN latest metrics row within a 7-day window of the
    -- global max nav_date. A flat equality to MAX(nav_date) dropped returns for
    -- ~10 funds whose NAV publishes 1 day behind the leader (normal AMC lag)
    -- even though fresh data exists. The 7-day guard recovers those without
    -- resurrecting genuinely dead funds (weeks/months stale → stay NULL).
    -- DISTINCT ON scans the recent window once (~3k rows) and dedups to the
    -- latest per fund: ~105ms vs ~235ms for a per-fund correlated LATERAL
    -- (measured via EXPLAIN ANALYZE on prod, 1.05M-row table) — same result set.
    LEFT JOIN (
      SELECT DISTINCT ON (mstar_id)
        mstar_id, ret_1m, ret_3m, ret_6m, ret_12m, rs_pctile_3m, realized_vol_63
      FROM atlas.atlas_fund_metrics_daily
      WHERE nav_date >= (SELECT d FROM latest_fm) - INTERVAL '7 days'
      ORDER BY mstar_id, nav_date DESC
    ) fm ON fm.mstar_id = fl.scheme_code
    ORDER BY
      fl.is_atlas_leader DESC,
      fl.composite_score DESC NULLS LAST,
      fl.fund_name
  `

  const out: FundListRow[] = rows.map(r => ({
    scheme_code: r.scheme_code,
    isin: r.isin,
    fund_name: r.fund_name,
    amc: r.amc,
    fund_category: r.fund_category,
    fund_style: r.fund_style,
    broad_category: r.broad_category,
    plan_type: r.plan_type,
    benchmark_code: r.benchmark_code,
    aum_cr: toNumber(r.aum_cr),
    composite_score: toNumber(r.composite_score),
    risk_adjusted_return_score: toNumber(r.risk_adjusted_return_score),
    holdings_conviction_score: toNumber(r.holdings_conviction_score),
    style_sector_score: toNumber(r.style_sector_score),
    cost_manager_score: toNumber(r.cost_manager_score),
    rank_in_category: r.rank_in_category == null ? null : toInt(r.rank_in_category),
    category_size: r.category_size == null ? null : toInt(r.category_size),
    is_atlas_leader: r.is_atlas_leader,
    is_avoid: r.is_avoid,
    confidence_low: r.confidence_low,
    holdings_unjoinable: r.holdings_unjoinable,
    survivorship_exposure_pct: toNumber(r.survivorship_exposure_pct),
    peer_quartile: r.peer_quartile,
    recommendation: r.recommendation,
    consistency_months: r.consistency_months == null ? null : toInt(r.consistency_months),
    nav: toNumber(r.nav),
    expense_ratio: toNumber(r.expense_ratio),
    top_holdings: r.top_holdings ?? [],
    sub_metrics: r.sub_metrics,
    eli5: r.eli5,
    amc_total_funds: toInt(r.amc_total_funds),
    amc_q1_count: toInt(r.amc_q1_count),
    amc_q4_count: toInt(r.amc_q4_count),
    amc_avg_composite: toNumber(r.amc_avg_composite),
    as_of_date: r.as_of_date,
    refreshed_at: r.refreshed_at,
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_pctile_3m: toNumber(r.rs_pctile_3m),
    realized_vol_63: r.realized_vol_63 ?? null,
  }))

  return { as_of_date: out[0]?.as_of_date ?? null, rows: out }
}
