// frontend/src/lib/queries/funds_holding_stock.ts
//
// Query: "which funds hold this stock?" — consumed by the stock detail page
// (§6.4 "Funds holding this stock" section).
//
// Source: atlas_foundation.de_mf_holdings (Atlas-owned weekly Morningstar snapshot),
// joined to atlas_universe_funds for the scheme name + AUM. NOT the retired M4
// atlas_fund_scorecard (dropped FM 2026-07-03 with the scorecard methodology) — this
// is a raw holdings look-up; the composite-grade badge was dropped with it.
//
// AUM: atlas_foundation.atlas_universe_funds.aum_cr — TRUE ₹ crore (ingest_fund_master.py
// writes fund size in ₹ / 1e7, fresh from Morningstar), used directly, no scaling.
//
// Snapshot staleness: we always use MAX(as_of_date) of de_mf_holdings.

import 'server-only'
import sql from '@/lib/db'

export type FundHolding = {
  fund_code: string   // de_mf_holdings.mstar_id
  fund_name: string   // atlas_universe_funds.scheme_name
  aum_cr: string      // stringified Decimal — INR crore (atlas_universe_funds.aum_cr)
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
  // Sourced from RAW holdings (atlas_foundation.de_mf_holdings, Atlas-owned weekly
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
    FROM atlas_foundation.de_mf_holdings h
    JOIN atlas_foundation.atlas_universe_funds uf ON uf.mstar_id = h.mstar_id
    WHERE h.as_of_date = (SELECT MAX(as_of_date) FROM atlas_foundation.de_mf_holdings)
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
