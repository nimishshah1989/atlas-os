// frontend/src/lib/queries/v6/etfs.ts
//
// Direct Supabase query for the v6 ETFs page. Replaces the api/v1 client
// path that was trying to hit a non-running localhost:8002.
//
// Joins:
//   atlas_etf_scorecard  ← composite + sub-scores + ELI5
//   atlas_universe_etfs  ← ticker / etf_name / category enrichment
//   atlas_etf_metrics_daily ← ret_1m / ret_3m / ret_6m / ret_12m + rs_pctile_3m
//
// Returns the same shape ScreenEtf the page already consumes — conviction_tape
// is a NEUTRAL placeholder because ETFs don't have conviction rows today.

import 'server-only'
import sql from '@/lib/db'
import type { ScreenEtf, ConvictionTape } from '@/lib/api/v1'

const NEUTRAL_TAPE: ConvictionTape = {
  '1m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '3m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '6m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '12m': { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
}

type Row = {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  composite_score: string | null
  matrix_conviction_score: string | null
  sector_strength_score: string | null
  tracking_quality_score: string | null
  aum_bracket_score: string | null
  liquidity_score: string | null
  expense_ratio_score: string | null
  rank_in_category: number | null
  category_size: number | null
  is_atlas_leader: boolean | null
  eli5: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
}

/**
 * Return all ETF scorecard rows for a snapshot_date, sorted by composite_score
 * desc. Shapes the rows into ScreenEtf (consumed by /v6/etfs page) plus a
 * neutral conviction tape — ETFs don't have conviction rows yet.
 */
export async function getEtfsForDate(snapshotDate: string): Promise<ScreenEtf[]> {
  const rows = await sql<Row[]>`
    SELECT
      s.instrument_id::text          AS iid,
      s.ticker,
      COALESCE(s.etf_name, u.etf_name) AS name,
      s.etf_category                 AS category,
      s.composite_score::text        AS composite_score,
      s.matrix_conviction_score::text AS matrix_conviction_score,
      s.sector_strength_score::text  AS sector_strength_score,
      s.tracking_quality_score::text AS tracking_quality_score,
      s.aum_bracket_score::text      AS aum_bracket_score,
      s.liquidity_score::text        AS liquidity_score,
      s.expense_ratio_score::text    AS expense_ratio_score,
      s.rank_in_category,
      s.category_size,
      s.is_atlas_leader,
      s.eli5,
      m.ret_1m::text                 AS ret_1m,
      m.ret_3m::text                 AS ret_3m,
      m.ret_6m::text                 AS ret_6m,
      m.ret_12m::text                AS ret_12m,
      m.rs_pctile_3m::text           AS rs_pctile_3m
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

  return rows.map((r): ScreenEtf => ({
    iid: r.iid,
    ticker: r.ticker,
    name: r.name,
    category: r.category,
    // AUM not in scorecard row directly — pull from raw_metrics if needed later
    aum_inr: null,
    conviction_tape: NEUTRAL_TAPE,
    ret_1m: r.ret_1m != null ? Number(r.ret_1m) : null,
    ret_3m: r.ret_3m != null ? Number(r.ret_3m) : null,
    ret_6m: r.ret_6m != null ? Number(r.ret_6m) : null,
    ret_12m: r.ret_12m != null ? Number(r.ret_12m) : null,
    // rs_state shape is "Leader/Strong/Average/Weak/Laggard" — derive from rs_pctile_3m
    rs_state: rsStateFromPctile(r.rs_pctile_3m),
  }))
}

function rsStateFromPctile(p: string | null): string | null {
  if (p == null) return null
  const v = Number(p)
  if (Number.isNaN(v)) return null
  if (v >= 0.90) return 'Leader'
  if (v >= 0.70) return 'Strong'
  if (v >= 0.30) return 'Average'
  if (v >= 0.10) return 'Weak'
  return 'Laggard'
}
