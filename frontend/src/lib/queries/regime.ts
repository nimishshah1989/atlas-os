// src/lib/queries/regime.ts
import 'server-only'
import sql from '@/lib/db'

// postgres returns NUMERIC as string — keep as string, parse at display time
export type MarketRegimeRow = {
  date: Date
  nifty500_close: string | null
  nifty500_ema_50: string | null
  nifty500_ema_200: string | null
  nifty500_above_ema_50: boolean
  nifty500_above_ema_200: boolean
  nifty500_ema_50_slope: string | null
  nifty500_ema_200_slope: string | null
  pct_above_ema_20: string | null
  pct_above_ema_50: string | null
  pct_above_ema_200: string | null
  advances_count: number | null
  declines_count: number | null
  unchanged_count: number | null
  ad_ratio: string | null
  ad_line: string | null
  ad_line_slope_21: string | null
  mcclellan_oscillator: string | null
  mcclellan_summation: string | null
  new_52w_highs: number | null
  new_52w_lows: number | null
  net_new_highs: number | null
  new_high_low_ratio: string | null
  pct_in_strong_states: string | null
  pct_weinstein_pass: string | null
  india_vix: string | null
  realized_vol_5d_nifty500: string | null
  vol_252_median_nifty500: string | null
  regime_state: string
  deployment_multiplier: string
  dislocation_active: boolean
  dislocation_started: Date | null
}

export type RegimeHistoryRow = {
  date: Date
  regime_state: string
  deployment_multiplier: string
  nifty500_close: string | null
  pct_above_ema_20: string | null
  pct_above_ema_50: string | null
  pct_above_ema_200: string | null
  ad_ratio: string | null
  ad_line: string | null
  mcclellan_oscillator: string | null
  mcclellan_summation: string | null
  new_52w_highs: number | null
  new_52w_lows: number | null
  net_new_highs: number | null
  new_high_low_ratio: string | null
  pct_in_strong_states: string | null
  pct_weinstein_pass: string | null
  india_vix: string | null
  nifty500_ema_50_slope: string | null
  nifty500_ema_200_slope: string | null
}

export async function getCurrentRegime(): Promise<MarketRegimeRow | null> {
  // Two-anchor fallback: regime_state + VIX + deployment_multiplier from the
  // latest row; stock-derived columns (pct_above_ema_*, advances_count,
  // mcclellan, new_52w_*, pct_in_strong_states, pct_weinstein_pass) from the
  // latest row where pct_above_ema_50 IS NOT NULL.
  //
  // Why: the nightly stock+regime compute writes the breadth columns from
  // atlas_stock_metrics_daily. When that upstream is empty (subprocess
  // timeout in jip-data-engine pipeline_trigger.py line 339 — fixed
  // separately), today's row exists with regime_state populated but breadth
  // columns NULL, and the page rendered "BREADTH n/a" while showing valid
  // TREND / MOMENTUM / PARTICIPATION — confusing.
  //
  // The COALESCE pattern surfaces the last good breadth read with the rest
  // of today's regime intact. Same anchor pattern used in mv_sector_cards.
  const rows = await sql<MarketRegimeRow[]>`
    WITH latest_full AS (
      SELECT *
      FROM atlas_foundation.atlas_market_regime_daily
      WHERE pct_above_ema_50 IS NOT NULL
      ORDER BY date DESC
      LIMIT 1
    ),
    latest_any AS (
      SELECT *
      FROM atlas_foundation.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 1
    )
    SELECT
      la.date,
      la.nifty500_close, la.nifty500_ema_50, la.nifty500_ema_200,
      la.nifty500_above_ema_50, la.nifty500_above_ema_200,
      la.nifty500_ema_50_slope, la.nifty500_ema_200_slope,
      COALESCE(la.pct_above_ema_20,  lf.pct_above_ema_20)  AS pct_above_ema_20,
      COALESCE(la.pct_above_ema_50,  lf.pct_above_ema_50)  AS pct_above_ema_50,
      COALESCE(la.pct_above_ema_200, lf.pct_above_ema_200) AS pct_above_ema_200,
      COALESCE(la.advances_count,    lf.advances_count)    AS advances_count,
      COALESCE(la.declines_count,    lf.declines_count)    AS declines_count,
      COALESCE(la.unchanged_count,   lf.unchanged_count)   AS unchanged_count,
      COALESCE(la.ad_ratio,          lf.ad_ratio)          AS ad_ratio,
      COALESCE(la.ad_line,           lf.ad_line)           AS ad_line,
      COALESCE(la.ad_line_slope_21,  lf.ad_line_slope_21)  AS ad_line_slope_21,
      COALESCE(la.mcclellan_oscillator, lf.mcclellan_oscillator) AS mcclellan_oscillator,
      COALESCE(la.mcclellan_summation,  lf.mcclellan_summation)  AS mcclellan_summation,
      COALESCE(la.new_52w_highs,     lf.new_52w_highs)     AS new_52w_highs,
      COALESCE(la.new_52w_lows,      lf.new_52w_lows)      AS new_52w_lows,
      COALESCE(la.net_new_highs,     lf.net_new_highs)     AS net_new_highs,
      COALESCE(la.new_high_low_ratio, lf.new_high_low_ratio) AS new_high_low_ratio,
      COALESCE(la.pct_in_strong_states, lf.pct_in_strong_states) AS pct_in_strong_states,
      COALESCE(la.pct_weinstein_pass,   lf.pct_weinstein_pass)   AS pct_weinstein_pass,
      la.india_vix, la.realized_vol_5d_nifty500, la.vol_252_median_nifty500,
      la.regime_state, la.deployment_multiplier, la.dislocation_active, la.dislocation_started
    FROM latest_any la
    LEFT JOIN latest_full lf ON true
  `
  return rows[0] ?? null
}

export async function getRegimeHistory(days: number): Promise<RegimeHistoryRow[]> {
  return sql<RegimeHistoryRow[]>`
    SELECT
      date,
      regime_state,
      deployment_multiplier,
      nifty500_close,
      pct_above_ema_20,
      pct_above_ema_50,
      pct_above_ema_200,
      ad_ratio,
      ad_line,
      mcclellan_oscillator,
      mcclellan_summation,
      new_52w_highs,
      new_52w_lows,
      net_new_highs,
      new_high_low_ratio,
      pct_in_strong_states,
      pct_weinstein_pass,
      india_vix,
      nifty500_ema_50_slope,
      nifty500_ema_200_slope
    FROM atlas_foundation.atlas_market_regime_daily
    WHERE date >= NOW() - (${days} || ' days')::INTERVAL
    ORDER BY date ASC
  `
}
