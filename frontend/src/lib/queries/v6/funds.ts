// frontend/src/lib/queries/v6/funds.ts
//
// Direct Supabase query for the v6 Funds page.
//
// Joins:
//   atlas_fund_scorecard      ← composite + sub-scores + ELI5 + top_holdings
//   atlas_universe_funds      ← scheme_name / amc / category enrichment + aum_cr
//   atlas_fund_metrics_daily  ← ret_1m / 3m / 6m / 12m + rs_pctile_3m (latest NAV)
//
// Returns ScreenFund shape consumed by /v6/funds page. Style box and
// conviction tape are placeholders pending v6.1 work — the fund scorecard
// doesn't yet expose tape rows for funds (only stocks).

import 'server-only'
import sql from '@/lib/db'
import type { ScreenFund, StyleSize, StyleAxis } from '@/lib/api/v1'

type Row = {
  iid: string
  code: string
  name: string
  category: string | null
  amc: string | null
  fund_style: string | null
  aum_cr: string | null
  composite_score: string | null
  risk_adjusted_return_score: string | null
  holdings_conviction_score: string | null
  style_sector_score: string | null
  cost_manager_score: string | null
  rank_in_category: number | null
  category_size: number | null
  is_atlas_leader: boolean | null
  is_avoid: boolean | null
  confidence_low: boolean | null
  eli5: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
}

/**
 * Return all fund scorecard rows for a snapshot_date, sorted by composite_score
 * desc. Shapes into ScreenFund. Returns NULL conviction_tape — fund-level
 * tape is v6.1 work.
 */
export async function getFundsForDate(snapshotDate: string): Promise<ScreenFund[]> {
  // Funds NAVs lag by 1–3 days vs the scorecard. Pin to a single most-recent
  // nav_date <= snapshot_date via subquery (fast index-only scan) rather than
  // a DISTINCT ON across all NAV rows (full-table sort — was timing out).
  const rows = await sql<Row[]>`
    SELECT
      s.scheme_code                  AS iid,
      s.scheme_code                  AS code,
      COALESCE(s.fund_name, u.scheme_name) AS name,
      s.fund_category                AS category,
      s.amc                          AS amc,
      s.fund_style                   AS fund_style,
      u.aum_cr::text                 AS aum_cr,
      s.composite_score::text        AS composite_score,
      s.risk_adjusted_return_score::text AS risk_adjusted_return_score,
      s.holdings_conviction_score::text  AS holdings_conviction_score,
      s.style_sector_score::text     AS style_sector_score,
      s.cost_manager_score::text     AS cost_manager_score,
      s.rank_in_category,
      s.category_size,
      s.is_atlas_leader,
      s.is_avoid,
      s.confidence_low,
      s.eli5,
      lm.ret_1m::text                AS ret_1m,
      lm.ret_3m::text                AS ret_3m,
      lm.ret_6m::text                AS ret_6m,
      lm.ret_12m::text               AS ret_12m,
      lm.rs_pctile_3m::text          AS rs_pctile_3m
    FROM atlas.atlas_fund_scorecard s
    LEFT JOIN atlas.atlas_universe_funds u
      ON u.mstar_id = s.scheme_code
     AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_fund_metrics_daily lm
      ON lm.mstar_id = s.scheme_code
     AND lm.nav_date = (
       SELECT MAX(nav_date)
       FROM atlas.atlas_fund_metrics_daily
       WHERE nav_date <= ${snapshotDate}
     )
    WHERE s.snapshot_date = ${snapshotDate}
    ORDER BY s.composite_score DESC NULLS LAST
  `

  return rows.map((r): ScreenFund => ({
    iid: r.iid,
    code: r.code,
    name: r.name,
    category: r.category,
    // aum_cr is in ₹ crore — convert to ₹ for formatINR consumers.
    aum_inr: r.aum_cr != null ? Number(r.aum_cr) * 1e7 : null,
    style_box: styleBoxFromCategory(r.fund_style, r.category),
    conviction_tape: null,
    ret_1m: r.ret_1m != null ? Number(r.ret_1m) : null,
    ret_3m: r.ret_3m != null ? Number(r.ret_3m) : null,
    ret_6m: r.ret_6m != null ? Number(r.ret_6m) : null,
    ret_12m: r.ret_12m != null ? Number(r.ret_12m) : null,
    rs_state: rsStateFromPctile(r.rs_pctile_3m),
  }))
}

/**
 * Heuristic style-box assignment for Indian funds.
 * `fund_style` is the explicit field if populated; otherwise we infer
 * size from category keywords. v6.1 will replace this with a proper
 * style-box classifier.
 */
function styleBoxFromCategory(
  fundStyle: string | null,
  category: string | null,
): { size: StyleSize; style: StyleAxis } | null {
  const cat = (category ?? '').toLowerCase()
  let size: StyleSize | null = null
  if (cat.includes('large') || cat.includes('bluechip')) size = 'Large'
  else if (cat.includes('mid')) size = 'Mid'
  else if (cat.includes('small')) size = 'Small'
  else if (cat.includes('flexi') || cat.includes('multi')) size = 'Large'

  if (size == null) return null

  const style: StyleAxis =
    fundStyle === 'Value' ? 'Value' :
    fundStyle === 'Growth' ? 'Growth' :
    'Blend'
  return { size, style }
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
