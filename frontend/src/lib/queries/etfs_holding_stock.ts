// frontend/src/lib/queries/etfs_holding_stock.ts
//
// Query: "which ETFs hold this stock?" — the reverse of the ETF holdings drill,
// rendered on the stock detail page alongside "funds holding this stock".
// Single-schema: all reads from atlas_foundation.
//
//   atlas_foundation.de_etf_holdings (ticker, instrument_id, weight)
//   ⨝ de_etf_master (ticker → name)
//   ⨝ atlas_etf_scorecard (latest composite_score → grade), left join
import 'server-only'
import sql from '@/lib/db'

export type EtfHolding = {
  ticker: string
  etf_name: string
  weight_pct: string   // the stock's weight inside the ETF (%)
  atlas_grade: string  // from the ETF's composite_score, or '—' if unscored
}

type Row = {
  ticker: string
  etf_name: string | null
  weight_pct: string | null
  atlas_grade: string
}

/** Up to 10 ETFs holding *iid* (weight ≥ 0.5%), sorted by weight desc. */
export async function getEtfsHoldingStock(iid: string): Promise<EtfHolding[]> {
  const rows = await sql<Row[]>`
    SELECT
      h.ticker                                        AS ticker,
      COALESCE(m.name, sc.etf_name, h.ticker)         AS etf_name,
      -- de_etf_holdings.weight is a FRACTION (0..1) — ×100 to a display percent.
      (h.weight * 100)::text                          AS weight_pct,
      CASE
        WHEN sc.composite_score >= 90 THEN 'AAA'
        WHEN sc.composite_score >= 80 THEN 'AA'
        WHEN sc.composite_score >= 70 THEN 'A'
        WHEN sc.composite_score >= 60 THEN 'BBB'
        WHEN sc.composite_score >= 50 THEN 'BB'
        WHEN sc.composite_score IS NOT NULL THEN 'B'
        ELSE '—'
      END                                             AS atlas_grade
    FROM atlas_foundation.de_etf_holdings h
    LEFT JOIN atlas_foundation.de_etf_master m ON m.ticker = h.ticker
    LEFT JOIN atlas_foundation.atlas_etf_scorecard sc
      ON sc.ticker = h.ticker
     AND sc.snapshot_date = (SELECT MAX(snapshot_date) FROM atlas_foundation.atlas_etf_scorecard)
    WHERE h.instrument_id = ${iid}::uuid
      AND h.weight >= 0.005
    ORDER BY h.weight DESC NULLS LAST
    LIMIT 10
  `
  return rows
    .filter((r): r is Row & { weight_pct: string } => r.weight_pct != null)
    .map((r): EtfHolding => ({
      ticker: r.ticker,
      etf_name: r.etf_name ?? r.ticker,
      weight_pct: r.weight_pct,
      atlas_grade: r.atlas_grade,
    }))
}
