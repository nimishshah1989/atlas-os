// frontend/src/lib/queries/v6/fund-deepdive.ts
//
// Reads atlas.mv_fund_deepdive for a single scheme_code. Returns scalars +
// 4 JSONB sections (top_holdings, sub_metrics, nav_12m, recent_decisions_90d).
//
// MV refreshed nightly via pg_cron (Phase D).

import 'server-only'
import sql from '@/lib/db'

export type FundHolding = {
  symbol: string
  weight_pct: number
  verdict: string | null
  instrument_id: string | null
}

export type FundNavPoint = {
  month: string
  nav: number
}

export type FundRecentDecision = {
  date: string
  recommendation: string
  is_investable: boolean
}

export type FundSubMetrics = {
  alpha: number | null
  sharpe: number | null
  sortino: number | null
  calmar: number | null
  max_dd: number | null
  up_capture: number | null
  down_capture: number | null
  fund_age_years: number | null
  n_observations: number | null
  ter_pct: number | null
  aum_cr: number | null
  manager_tenure_years: number | null
}

export type FundDeepdive = {
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
  inception_date: string | null
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
  nav_as_of: string | null
  holdings_as_of: string | null
  peer_quartile: string | null
  recommendation: string | null
  consistency_months: number | null
  latest_nav: number | null
  expense_ratio: number | null
  eli5: string | null
  top_holdings: FundHolding[]
  sub_metrics: FundSubMetrics | null
  nav_12m: FundNavPoint[]
  recent_decisions_90d: FundRecentDecision[]
  as_of_date: string | null
  refreshed_at: string | null
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
  inception_date: string | null
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
  nav_as_of: string | null
  holdings_as_of: string | null
  peer_quartile: string | null
  recommendation: string | null
  consistency_months: number | string | null
  latest_nav: string | null
  expense_ratio: string | null
  eli5: string | null
  top_holdings: FundHolding[] | null
  sub_metrics: FundSubMetrics | null
  nav_12m: FundNavPoint[] | null
  recent_decisions_90d: FundRecentDecision[] | null
  as_of_date: string | null
  refreshed_at: string | null
}

function toNumber(s: string | number | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

function toIntOrNull(s: number | string | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

export async function getFundDeepdive(scheme_code: string): Promise<FundDeepdive | null> {
  const rows = await sql<Row[]>`
    SELECT
      scheme_code, isin, fund_name, amc, fund_category, fund_style,
      broad_category, plan_type, benchmark_code,
      aum_cr::text                       AS aum_cr,
      inception_date::text               AS inception_date,
      composite_score::text              AS composite_score,
      risk_adjusted_return_score::text   AS risk_adjusted_return_score,
      holdings_conviction_score::text    AS holdings_conviction_score,
      style_sector_score::text           AS style_sector_score,
      cost_manager_score::text           AS cost_manager_score,
      rank_in_category, category_size,
      is_atlas_leader, is_avoid, confidence_low, holdings_unjoinable,
      survivorship_exposure_pct::text    AS survivorship_exposure_pct,
      nav_as_of::text                    AS nav_as_of,
      holdings_as_of::text               AS holdings_as_of,
      peer_quartile, recommendation, consistency_months,
      latest_nav::text                   AS latest_nav,
      expense_ratio::text                AS expense_ratio,
      eli5,
      top_holdings, sub_metrics, nav_12m, recent_decisions_90d,
      as_of_date::text                   AS as_of_date,
      refreshed_at::text                 AS refreshed_at
    FROM atlas.mv_fund_deepdive
    WHERE scheme_code = ${scheme_code}
    LIMIT 1
  `
  const r = rows[0]
  if (!r) return null

  return {
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
    inception_date: r.inception_date,
    composite_score: toNumber(r.composite_score),
    risk_adjusted_return_score: toNumber(r.risk_adjusted_return_score),
    holdings_conviction_score: toNumber(r.holdings_conviction_score),
    style_sector_score: toNumber(r.style_sector_score),
    cost_manager_score: toNumber(r.cost_manager_score),
    rank_in_category: toIntOrNull(r.rank_in_category),
    category_size: toIntOrNull(r.category_size),
    is_atlas_leader: r.is_atlas_leader,
    is_avoid: r.is_avoid,
    confidence_low: r.confidence_low,
    holdings_unjoinable: r.holdings_unjoinable,
    survivorship_exposure_pct: toNumber(r.survivorship_exposure_pct),
    nav_as_of: r.nav_as_of,
    holdings_as_of: r.holdings_as_of,
    peer_quartile: r.peer_quartile,
    recommendation: r.recommendation,
    consistency_months: toIntOrNull(r.consistency_months),
    latest_nav: toNumber(r.latest_nav),
    expense_ratio: toNumber(r.expense_ratio),
    eli5: r.eli5,
    top_holdings: r.top_holdings ?? [],
    sub_metrics: r.sub_metrics,
    nav_12m: r.nav_12m ?? [],
    recent_decisions_90d: r.recent_decisions_90d ?? [],
    as_of_date: r.as_of_date,
    refreshed_at: r.refreshed_at,
  }
}
