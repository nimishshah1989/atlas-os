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
}

function toNumber(s: string | number | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

function toInt(s: number | string | null | undefined): number {
  if (s == null) return 0
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : 0
}

export async function getFundListPage(): Promise<FundListPage> {
  const rows = await sql<Row[]>`
    SELECT
      scheme_code, isin, fund_name, amc, fund_category, fund_style,
      broad_category, plan_type, benchmark_code,
      aum_cr::text                       AS aum_cr,
      composite_score::text              AS composite_score,
      risk_adjusted_return_score::text   AS risk_adjusted_return_score,
      holdings_conviction_score::text    AS holdings_conviction_score,
      style_sector_score::text           AS style_sector_score,
      cost_manager_score::text           AS cost_manager_score,
      rank_in_category, category_size,
      is_atlas_leader, is_avoid, confidence_low, holdings_unjoinable,
      survivorship_exposure_pct::text    AS survivorship_exposure_pct,
      peer_quartile, recommendation, consistency_months,
      nav::text                          AS nav,
      expense_ratio::text                AS expense_ratio,
      top_holdings, sub_metrics, eli5,
      amc_total_funds, amc_q1_count, amc_q4_count,
      amc_avg_composite::text            AS amc_avg_composite,
      as_of_date::text                   AS as_of_date,
      refreshed_at::text                 AS refreshed_at
    FROM atlas.mv_fund_list_v6
    ORDER BY
      is_atlas_leader DESC,
      composite_score DESC NULLS LAST,
      fund_name
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
  }))

  return { as_of_date: out[0]?.as_of_date ?? null, rows: out }
}
