// frontend/src/lib/queries/v6/funds_holding_stock.ts
//
// Query: "which funds hold this stock?" — consumed by the stock detail page
// (§6.4 "Funds holding this stock" section).
//
// Source: foundation_staging.atlas_fund_scorecard.top_holdings JSONB
//
// JSONB shape (per atlas/inference/fund_scorecard.py drilldown builder):
//   [
//     { "instrument_id": "<uuid>", "symbol": "<ticker>",
//       "weight_pct": 4.25,  "verdict": "POSITIVE|NEUTRAL|NEGATIVE|null" },
//     ...
//   ]
//
// AUM: the scorecard's sub_metrics->>'aum_cr' is empty in live data, so AUM is
// sourced from foundation_staging.atlas_universe_funds.aum_cr (single-schema). As of
// the 1b consolidation that column holds TRUE ₹ crore (ingest_fund_master.py writes
// fund size in ₹ / 1e7, fresh from Morningstar) — used directly, no scaling.
//
// Snapshot staleness: we always use MAX(snapshot_date). If that snapshot is
// older than 7 days the frontend should surface a "data as of" badge; that
// staleness check lives in the component layer (not here). This function
// returns whatever the latest snapshot has.

import 'server-only'
import sql from '@/lib/db'

export type FundHolding = {
  fund_code: string   // atlas_fund_scorecard.scheme_code
  fund_name: string   // atlas_fund_scorecard.fund_name
  aum_cr: string      // stringified Decimal — INR crore (from sub_metrics->>'aum_cr')
  weight_pct: string  // stringified Decimal — fund's weight in this stock
  atlas_grade: string // derived from composite_score: AAA/AA/A/BBB/BB/B
}

type Row = {
  fund_code: string
  fund_name: string | null
  aum_cr: string | null
  weight_pct: string | null
  atlas_grade: string
}

/**
 * Returns up to 10 funds that hold the given instrument_id in their
 * top_holdings JSONB, where weight_pct >= 0.5%.
 *
 * Results are pinned to the latest snapshot_date and sorted by AUM descending.
 *
 * @param iid  instrument_id UUID (atlas_universe_stocks.instrument_id)
 * @returns    FundHolding[] — empty array when no fund holds this stock
 */
export async function getFundsHoldingStock(iid: string): Promise<FundHolding[]> {
  // Sourced from RAW holdings (foundation_staging.de_mf_holdings, Atlas-owned weekly
  // snapshot) — NOT the retired M4 fund scorecard. "Which funds hold this stock" is a raw
  // holdings lookup; AUM/name come from the curated universe. The composite-grade badge was
  // dropped with the scorecard methodology (the simplified product ranks by AUM/weight).
  const rows = await sql<Row[]>`
    SELECT
      h.mstar_id                                       AS fund_code,
      COALESCE(uf.scheme_name, h.mstar_id)             AS fund_name,
      uf.aum_cr::text                                  AS aum_cr,
      h.weight_pct::text                               AS weight_pct,
      ''                                               AS atlas_grade
    FROM foundation_staging.de_mf_holdings h
    JOIN foundation_staging.atlas_universe_funds uf ON uf.mstar_id = h.mstar_id
    WHERE h.as_of_date = (SELECT MAX(as_of_date) FROM foundation_staging.de_mf_holdings)
      AND h.instrument_id = ${iid}::uuid
      AND h.weight_pct >= 0.5
      -- Regular plans only — drop the Direct duplicates of the same scheme ("Dir Gr" / "Direct")
      AND uf.scheme_name NOT ILIKE '%Dir Gr%'
      AND uf.scheme_name NOT ILIKE '%Direct%'
      AND uf.scheme_name NOT ILIKE '%IDCW%'
    ORDER BY uf.aum_cr DESC NULLS LAST
    LIMIT 10
  `

  return rows
    .filter((r): r is Row & { weight_pct: string } => r.weight_pct != null)
    .map((r): FundHolding => ({
      fund_code: r.fund_code,
      fund_name: r.fund_name ?? r.fund_code,
      aum_cr: r.aum_cr ?? '0',
      weight_pct: r.weight_pct,
      atlas_grade: r.atlas_grade,
    }))
}
