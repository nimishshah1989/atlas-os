// frontend/src/lib/queries/v6/etfs.ts
//
// Direct Supabase query for the v6 ETFs page.
//
// Joins:
//   atlas_etf_scorecard  ← composite + sub-scores + ELI5 + raw_metrics (JSONB)
//   atlas_universe_etfs  ← ticker / etf_name / category enrichment
//   atlas_etf_metrics_daily ← ret_1m / ret_3m / ret_6m / ret_12m + rs_pctile_3m
//
// Returns EtfV6Row (extended shape) sorted by composite_score DESC.
// conviction_tape is a NEUTRAL placeholder — ETFs don't have tape rows today.

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'
import type { ConvictionTape } from '@/lib/api/v1'

const NEUTRAL_TAPE: ConvictionTape = {
  '1m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '3m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '6m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '12m': { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
}

// ---------------------------------------------------------------------------
// Public extended row type consumed by ETFsList client component
// ---------------------------------------------------------------------------

export type EtfV6Row = {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  aum_cr: string | null           // from raw_metrics->>'aum_cr' (Cr)
  expense_ratio: string | null    // from raw_metrics->>'ter_pct' (%)
  tracking_error: string | null   // from raw_metrics->>'tracking_error_252d' (%)
  is_atlas_leader: boolean | null
  composite_score: string | null
  conviction_tape: ConvictionTape
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_state: string | null
}

// ---------------------------------------------------------------------------
// Internal DB row type
// ---------------------------------------------------------------------------

type Row = {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  composite_score: string | null
  is_atlas_leader: boolean | null
  aum_cr: string | null
  expense_ratio: string | null
  tracking_error: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
}

// ---------------------------------------------------------------------------
// Public query
// ---------------------------------------------------------------------------

/**
 * Return all ETF scorecard rows for a snapshot_date, sorted by composite_score
 * desc. Returns EtfV6Row (extended shape with expense_ratio, tracking_error,
 * aum_cr). conviction_tape is NEUTRAL placeholder (ETF tape is v6.1 work).
 */
export async function getEtfsForDate(snapshotDate: string): Promise<EtfV6Row[]> {
  const rows = await sql<Row[]>`
    SELECT
      s.instrument_id::text                            AS iid,
      s.ticker,
      COALESCE(s.etf_name, u.etf_name)                AS name,
      s.etf_category                                   AS category,
      s.composite_score::text                          AS composite_score,
      s.is_atlas_leader,
      (s.raw_metrics->>'aum_cr')::text                 AS aum_cr,
      (s.raw_metrics->>'ter_pct')::text                AS expense_ratio,
      (s.raw_metrics->>'tracking_error_252d')::text    AS tracking_error,
      m.ret_1m::text                                   AS ret_1m,
      m.ret_3m::text                                   AS ret_3m,
      m.ret_6m::text                                   AS ret_6m,
      m.ret_12m::text                                  AS ret_12m,
      m.rs_pctile_3m::text                             AS rs_pctile_3m
    FROM atlas.atlas_etf_scorecard s
    LEFT JOIN atlas.atlas_universe_etfs u
      ON u.ticker = s.ticker
     AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = s.ticker
     AND m.date   = s.snapshot_date
    WHERE s.snapshot_date = ${snapshotDate}
    ORDER BY s.composite_score DESC NULLS LAST
  `

  return rows.map((r): EtfV6Row => ({
    iid: r.iid,
    ticker: r.ticker,
    name: r.name,
    category: r.category,
    aum_cr: r.aum_cr ?? null,
    expense_ratio: r.expense_ratio ?? null,
    tracking_error: r.tracking_error ?? null,
    is_atlas_leader: r.is_atlas_leader ?? null,
    composite_score: r.composite_score ?? null,
    conviction_tape: NEUTRAL_TAPE,
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_state: rsStateFromPctile(r.rs_pctile_3m),
  }))
}

// ---------------------------------------------------------------------------
// Single-ETF detail query (D.8)
// ---------------------------------------------------------------------------

export type EtfDetailRow = EtfV6Row & {
  rank_in_category: number | null
  category_size: number | null
  matrix_conviction_score: string | null
  sector_strength_score: string | null
  tracking_quality_score: string | null
  aum_bracket_score: string | null
  liquidity_score: string | null
  expense_ratio_score: string | null
  eli5: string | null
  top_holdings: ETFTopHolding[] | null
}

export type ETFTopHolding = {
  ticker: string
  weight_pct: string | null
  sector: string | null
}

type DetailRow = Row & {
  rank_in_category: number | null
  category_size: number | null
  matrix_conviction_score: string | null
  sector_strength_score: string | null
  tracking_quality_score: string | null
  aum_bracket_score: string | null
  liquidity_score: string | null
  expense_ratio_score: string | null
  eli5: string | null
  top_holdings: ETFTopHolding[] | null
}

/**
 * Return full scorecard detail for a single ETF by instrument_id (UUID).
 * Returns null when not found (triggers notFound() in page).
 */
export async function getEtfDetail(
  iid: string,
  snapshotDate: string,
): Promise<EtfDetailRow | null> {
  const rows = await sql<DetailRow[]>`
    SELECT
      s.instrument_id::text                              AS iid,
      s.ticker,
      COALESCE(s.etf_name, u.etf_name)                  AS name,
      s.etf_category                                     AS category,
      s.composite_score::text                            AS composite_score,
      s.is_atlas_leader,
      s.rank_in_category,
      s.category_size,
      s.matrix_conviction_score::text                    AS matrix_conviction_score,
      s.sector_strength_score::text                      AS sector_strength_score,
      s.tracking_quality_score::text                     AS tracking_quality_score,
      s.aum_bracket_score::text                          AS aum_bracket_score,
      s.liquidity_score::text                            AS liquidity_score,
      s.expense_ratio_score::text                        AS expense_ratio_score,
      s.eli5,
      (s.raw_metrics->>'aum_cr')::text                   AS aum_cr,
      (s.raw_metrics->>'ter_pct')::text                  AS expense_ratio,
      (s.raw_metrics->>'tracking_error_252d')::text      AS tracking_error,
      m.ret_1m::text                                     AS ret_1m,
      m.ret_3m::text                                     AS ret_3m,
      m.ret_6m::text                                     AS ret_6m,
      m.ret_12m::text                                    AS ret_12m,
      m.rs_pctile_3m::text                               AS rs_pctile_3m,
      s.top_holdings                                     AS top_holdings
    FROM atlas.atlas_etf_scorecard s
    LEFT JOIN atlas.atlas_universe_etfs u
      ON u.ticker = s.ticker
     AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker   = s.ticker
     AND m.date     = s.snapshot_date
    WHERE s.instrument_id = ${iid}::uuid
      AND s.snapshot_date = ${snapshotDate}
    LIMIT 1
  `

  const r = rows[0]
  if (!r) return null

  return {
    iid: r.iid,
    ticker: r.ticker,
    name: r.name,
    category: r.category,
    aum_cr: r.aum_cr ?? null,
    expense_ratio: r.expense_ratio ?? null,
    tracking_error: r.tracking_error ?? null,
    is_atlas_leader: r.is_atlas_leader ?? null,
    composite_score: r.composite_score ?? null,
    conviction_tape: NEUTRAL_TAPE,
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_state: rsStateFromPctile(r.rs_pctile_3m),
    rank_in_category: r.rank_in_category ?? null,
    category_size: r.category_size ?? null,
    matrix_conviction_score: r.matrix_conviction_score ?? null,
    sector_strength_score: r.sector_strength_score ?? null,
    tracking_quality_score: r.tracking_quality_score ?? null,
    aum_bracket_score: r.aum_bracket_score ?? null,
    liquidity_score: r.liquidity_score ?? null,
    expense_ratio_score: r.expense_ratio_score ?? null,
    eli5: r.eli5 ?? null,
    top_holdings: (r.top_holdings as ETFTopHolding[] | null) ?? null,
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function rsStateFromPctile(p: string | null): string | null {
  const v = toNumber(p)
  if (v == null) return null
  if (v >= 0.90) return 'Leader'
  if (v >= 0.70) return 'Strong'
  if (v >= 0.30) return 'Average'
  if (v >= 0.10) return 'Weak'
  return 'Laggard'
}
