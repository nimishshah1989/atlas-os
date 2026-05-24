// frontend/src/lib/queries/conviction.ts
// Phase 7: atlas_stock_conviction_daily is deprecated.
// conviction_score → within_state_rank from atlas_stock_signal_unified.
// tier → derived from rs_rank_12m using the same CASE expression as the view.
// confidence_label → hardcoded to 'descriptive_only' (no IC table equivalent).
// ConvictionBreakdown (contributing_signals JSON) has no equivalent in the view; stub returns null.
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

// Phase 7: rewired from atlas_stock_conviction_daily → atlas_stock_signal_unified.
// conviction_score returns within_state_rank (float8, 0-1 range).
// tier derived from rs_rank_12m thresholds (Leader/Strong/Average/Weak/Laggard).
export async function getStockConviction(
  instrumentId: string,
): Promise<ConvictionRow | null> {
  const rows = await sql<ConvictionRow[]>`
    SELECT
      su.instrument_id::text  AS instrument_id,
      u.symbol,
      u.sector,
      CASE
        WHEN su.rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN su.rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN su.rs_rank_12m >= 0.30 THEN 'Average'
        WHEN su.rs_rank_12m >= 0.10 THEN 'Weak'
        ELSE 'Laggard'
      END                           AS tier,
      su.within_state_rank::text    AS conviction_score,
      'descriptive_only'::text      AS confidence_label,
      NULL::text                    AS backing_ic,
      su.date::timestamp            AS computed_at
    FROM atlas.atlas_stock_signal_unified su
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = su.instrument_id
    WHERE su.instrument_id = ${instrumentId}::uuid
      AND su.date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
  `
  return rows[0] ?? null
}

// Phase 7: ConvictionBreakdown has no equivalent in atlas_stock_signal_unified.
// Returns null — callers already guard against null (Phase 6 cleanup).
export async function getConvictionBreakdown(
  _instrumentId: string,
): Promise<Record<string, ConvictionBreakdown> | null> {
  return null
}

// Phase 7: getConvictionMap rewired from mv_top_conviction_daily → atlas_stock_signal_unified.
// Returns the current snapshot keyed by instrument_id.
export async function getConvictionMap(): Promise<Record<string, ConvictionMapRow>> {
  const rows = await sql<ConvictionMapRow[]>`
    SELECT
      instrument_id::text       AS instrument_id,
      within_state_rank::text   AS conviction_score,
      'descriptive_only'::text  AS confidence_label,
      CASE
        WHEN rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN rs_rank_12m >= 0.30 THEN 'Average'
        WHEN rs_rank_12m >= 0.10 THEN 'Weak'
        ELSE 'Laggard'
      END                       AS tier,
      NULL::text                AS backing_ic
    FROM atlas.atlas_stock_signal_unified
    WHERE date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
  `
  const map: Record<string, ConvictionMapRow> = {}
  for (const r of rows) map[r.instrument_id] = r
  return map
}

// Phase 7: getTopConvictionByTier rewired from mv_top_conviction_daily → atlas_stock_signal_unified.
// tier maps to the rs_rank_12m CASE expression.
export async function getTopConvictionByTier(
  tier: string,
  n: number = 10,
): Promise<ConvictionRow[]> {
  return await sql<ConvictionRow[]>`
    SELECT
      su.instrument_id::text  AS instrument_id,
      u.symbol,
      u.sector,
      CASE
        WHEN su.rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN su.rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN su.rs_rank_12m >= 0.30 THEN 'Average'
        WHEN su.rs_rank_12m >= 0.10 THEN 'Weak'
        ELSE 'Laggard'
      END                           AS tier,
      su.within_state_rank::text    AS conviction_score,
      'descriptive_only'::text      AS confidence_label,
      NULL::text                    AS backing_ic,
      su.date::timestamp            AS computed_at
    FROM atlas.atlas_stock_signal_unified su
    LEFT JOIN atlas.atlas_universe_stocks u
           ON u.instrument_id = su.instrument_id
    WHERE su.date = (SELECT MAX(date) FROM atlas.atlas_stock_signal_unified)
      AND CASE
            WHEN su.rs_rank_12m >= 0.90 THEN 'Leader'
            WHEN su.rs_rank_12m >= 0.70 THEN 'Strong'
            WHEN su.rs_rank_12m >= 0.30 THEN 'Average'
            WHEN su.rs_rank_12m >= 0.10 THEN 'Weak'
            ELSE 'Laggard'
          END = ${tier}
    ORDER BY su.within_state_rank DESC NULLS LAST
    LIMIT ${n}
  `
}
