// frontend/src/lib/queries/rotation.ts
// Reads from mv_sector_rotation_state and mv_current_market_regime.
// Both views are refreshed nightly at 20:00 IST by pg_cron.
// All NUMERIC columns returned as `string | null` — parse at display time.
import 'server-only'
import sql from '@/lib/db'

export type RRGQuadrant = 'Leading' | 'Improving' | 'Lagging' | 'Weakening'

export type SectorRotationRow = {
  sector_name: string
  date: Date
  rs_level: string | null               // NUMERIC — bottomup_rs_3m_nifty500
  rs_velocity: string | null            // NUMERIC — 4-week RoC of rs_level
  rs_pctile_cross_sector: string | null // NUMERIC — 0–1 cross-sector percentile
  constituent_count: number | null
  sector_state: string | null           // 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid'
  bottomup_rs_state: string | null
  bottomup_momentum_state: string | null
  participation_rs_pct: string | null   // NUMERIC
  rrg_quadrant: RRGQuadrant | null
}

export type MarketRegimeRow = {
  date: Date
  regime_state: string
  deployment_multiplier: string | null  // NUMERIC — parse for display
  dislocation_active: boolean
  dislocation_started: Date | null
  nifty500_close: string | null
  nifty500_above_ema_50: boolean | null
  nifty500_above_ema_200: boolean | null
  pct_above_ema_50: string | null
  pct_above_ema_200: string | null
  pct_in_strong_states: string | null
  india_vix: string | null
  advances_count: number | null
  declines_count: number | null
  net_new_highs: number | null
  ad_ratio: string | null
  mcclellan_oscillator: string | null
}

/**
 * Returns all sectors with their RRG quadrant assignment for the current date.
 * Ordered by rs_pctile_cross_sector DESC (Leading sectors first).
 */
export async function getSectorRotationState(): Promise<SectorRotationRow[]> {
  return sql<SectorRotationRow[]>`
    SELECT
      sector_name,
      date,
      rs_level::text                AS rs_level,
      rs_velocity::text             AS rs_velocity,
      rs_pctile_cross_sector::text  AS rs_pctile_cross_sector,
      constituent_count,
      sector_state,
      bottomup_rs_state,
      bottomup_momentum_state,
      participation_rs_pct::text    AS participation_rs_pct,
      rrg_quadrant
    FROM atlas.mv_sector_rotation_state
    ORDER BY rs_pctile_cross_sector DESC NULLS LAST
  `
}

/**
 * Returns the current market regime (exactly one row from
 * mv_current_market_regime). Returns null if the view is empty
 * (e.g. database not yet populated).
 */
export async function getCurrentMarketRegime(): Promise<MarketRegimeRow | null> {
  const rows = await sql<MarketRegimeRow[]>`
    SELECT
      date,
      regime_state,
      deployment_multiplier::text  AS deployment_multiplier,
      dislocation_active,
      dislocation_started,
      nifty500_close::text         AS nifty500_close,
      nifty500_above_ema_50,
      nifty500_above_ema_200,
      pct_above_ema_50::text       AS pct_above_ema_50,
      pct_above_ema_200::text      AS pct_above_ema_200,
      pct_in_strong_states::text   AS pct_in_strong_states,
      india_vix::text              AS india_vix,
      advances_count,
      declines_count,
      net_new_highs,
      ad_ratio::text               AS ad_ratio,
      mcclellan_oscillator::text   AS mcclellan_oscillator
    FROM atlas.mv_current_market_regime
    LIMIT 1
  `
  return rows[0] ?? null
}
