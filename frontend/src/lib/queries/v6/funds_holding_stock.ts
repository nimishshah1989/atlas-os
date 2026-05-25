// frontend/src/lib/queries/v6/funds_holding_stock.ts
//
// Query: "which funds hold this stock?" — consumed by the stock detail page
// (§6.4 "Funds holding this stock" section).
//
// Source: atlas.atlas_fund_scorecard.top_holdings JSONB
//
// JSONB shape (per atlas/inference/fund_scorecard.py drilldown builder):
//   [
//     { "instrument_id": "<uuid>", "symbol": "<ticker>",
//       "weight_pct": 4.25,  "verdict": "POSITIVE|NEUTRAL|NEGATIVE|null" },
//     ...
//   ]
//
// aum_cr lives in sub_metrics JSONB under key "aum_cr" (NOT a top-level column).
// Confirmed from fund_scorecard.py line 673: sub_metrics["aum_cr"] = fi.aum_cr.
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
  const rows = await sql<Row[]>`
    SELECT
      fs.scheme_code                                  AS fund_code,
      COALESCE(fs.fund_name, fs.scheme_code)          AS fund_name,
      (fs.sub_metrics->>'aum_cr')::text               AS aum_cr,
      (h->>'weight_pct')::text                        AS weight_pct,
      CASE
        WHEN fs.composite_score >= 90 THEN 'AAA'
        WHEN fs.composite_score >= 80 THEN 'AA'
        WHEN fs.composite_score >= 70 THEN 'A'
        WHEN fs.composite_score >= 60 THEN 'BBB'
        WHEN fs.composite_score >= 50 THEN 'BB'
        ELSE 'B'
      END AS atlas_grade
    FROM atlas.atlas_fund_scorecard fs
    CROSS JOIN LATERAL jsonb_array_elements(fs.top_holdings) AS h
    WHERE fs.snapshot_date = (
            SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard
          )
      AND (h->>'instrument_id')::uuid = ${iid}::uuid
      AND (h->>'weight_pct')::numeric >= 0.5
    ORDER BY (fs.sub_metrics->>'aum_cr')::numeric DESC NULLS LAST
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
