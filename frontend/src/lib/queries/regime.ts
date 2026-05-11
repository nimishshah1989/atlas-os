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
  const rows = await sql<MarketRegimeRow[]>`
    SELECT
      date,
      nifty500_close, nifty500_ema_50, nifty500_ema_200,
      nifty500_above_ema_50, nifty500_above_ema_200,
      nifty500_ema_50_slope, nifty500_ema_200_slope,
      pct_above_ema_20, pct_above_ema_50, pct_above_ema_200,
      advances_count, declines_count, unchanged_count,
      ad_ratio, ad_line, ad_line_slope_21,
      mcclellan_oscillator, mcclellan_summation,
      new_52w_highs, new_52w_lows, net_new_highs, new_high_low_ratio,
      pct_in_strong_states, pct_weinstein_pass,
      india_vix, realized_vol_5d_nifty500, vol_252_median_nifty500,
      regime_state, deployment_multiplier, dislocation_active, dislocation_started
    FROM atlas.atlas_market_regime_daily
    ORDER BY date DESC
    LIMIT 1
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
    FROM atlas.atlas_market_regime_daily
    WHERE date >= NOW() - (${days} || ' days')::INTERVAL
    ORDER BY date ASC
  `
}
