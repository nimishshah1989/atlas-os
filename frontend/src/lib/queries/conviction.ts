// frontend/src/lib/queries/conviction.ts
// SP04 Stage 3 — read-only queries against the conviction tables.
// NUMERIC columns are returned as strings to preserve Decimal precision
// across the JS boundary; format at display time only.
import 'server-only'
import sql from '@/lib/db'

export type ConfidenceLabel = 'industry_grade' | 'baseline' | 'descriptive_only'

export type ConvictionRow = {
  instrument_id: string
  symbol: string | null
  sector: string | null
  tier: string
  conviction_score: string
  confidence_label: ConfidenceLabel
  backing_ic: string | null
  computed_at: Date
}

export type ConvictionBreakdown = {
  weight: number
  flipped: boolean
  percentile_rank: number
  contribution: number
  was_neutral_fill: boolean
}

export type ConvictionMapRow = {
  instrument_id: string
  conviction_score: string
  confidence_label: ConfidenceLabel
  tier: string
  backing_ic: string | null
}

export async function getStockConviction(
  instrumentId: string,
): Promise<ConvictionRow | null> {
  const rows = await sql<ConvictionRow[]>`
    SELECT
      c.instrument_id::text  AS instrument_id,
      u.symbol,
      u.sector,
      c.tier,
      c.conviction_score::text  AS conviction_score,
      c.confidence_label,
      c.backing_ic::text        AS backing_ic,
      c.computed_at
    FROM atlas.atlas_stock_conviction_daily c
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = c.instrument_id
    WHERE c.instrument_id = ${instrumentId}::uuid
      AND c.date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
  `
  return rows[0] ?? null
}

export async function getConvictionBreakdown(
  instrumentId: string,
): Promise<Record<string, ConvictionBreakdown> | null> {
  const rows = await sql<{ contributing_signals: Record<string, ConvictionBreakdown> }[]>`
    SELECT contributing_signals
    FROM atlas.atlas_stock_conviction_daily
    WHERE instrument_id = ${instrumentId}::uuid
      AND date = (SELECT MAX(date) FROM atlas.atlas_stock_conviction_daily)
  `
  return rows[0]?.contributing_signals ?? null
}

export async function getConvictionMap(): Promise<Record<string, ConvictionMapRow>> {
  const rows = await sql<ConvictionMapRow[]>`
    SELECT
      instrument_id::text       AS instrument_id,
      conviction_score::text    AS conviction_score,
      confidence_label,
      tier,
      backing_ic::text          AS backing_ic
    FROM atlas.mv_top_conviction_daily
  `
  const map: Record<string, ConvictionMapRow> = {}
  for (const r of rows) map[r.instrument_id] = r
  return map
}

export async function getTopConvictionByTier(
  tier: string,
  n: number = 10,
): Promise<ConvictionRow[]> {
  return await sql<ConvictionRow[]>`
    SELECT
      c.instrument_id::text  AS instrument_id,
      u.symbol,
      u.sector,
      c.tier,
      c.conviction_score::text AS conviction_score,
      c.confidence_label,
      c.backing_ic::text     AS backing_ic,
      NOW() AS computed_at
    FROM atlas.mv_top_conviction_daily c
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = c.instrument_id
    WHERE c.tier = ${tier}
    ORDER BY c.conviction_score DESC
    LIMIT ${n}
  `
}
