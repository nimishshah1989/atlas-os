// frontend/src/lib/queries/v6/stock_technicals.ts
//
// Unpack atlas_scorecard_daily.features JSONB into a typed StockTechnicals
// record for the Deep Dive Technicals tab.
//
// Key mapping (scorecard_writer canonical → StockTechnicals field):
//   dist_above_sma50      → ema_distance_20 (closest SMA proxy)
//   dist_above_sma50      → ema_distance_50
//   dist_above_sma200     → ema_distance_200
//   rsi_14                → rsi_14
//   rs_residual_6m (col)  → rs_pct_nifty500
//   realized_vol_252d     → vol_252d
//   obv_slope_60d         → obv_20d
//   atr_pct_14            → atr_14
//   dd_from_52w_high      → pct_from_52w_high
//   dist_from_52w_low     → pct_from_52w_low
//   log_med_tv_60d (col)  → log_med_tv_60d
//   formation_max_dd (col)→ drawdown_from_peak

import 'server-only'
import sql from '@/lib/db'

export type StockTechnicals = {
  iid: string
  date: string
  // EMA / SMA distances (% above/below benchmark SMA)
  ema_distance_20: string | null
  ema_distance_50: string | null
  ema_distance_200: string | null
  // Momentum
  rsi_14: string | null
  rs_pct_nifty500: string | null
  // Volatility + flow
  vol_252d: string | null
  obv_20d: string | null
  atr_14: string | null
  // 52-week range
  pct_from_52w_high: string | null
  pct_from_52w_low: string | null
  // Liquidity (first-class column — log median traded value 60d)
  log_med_tv_60d: string | null
  // Drawdown (first-class column — max drawdown in formation window)
  drawdown_from_peak: string | null
}

type RawRow = {
  iid: string
  date: string
  ema_distance_20: string | null
  ema_distance_50: string | null
  ema_distance_200: string | null
  rsi_14: string | null
  rs_pct_nifty500: string | null
  vol_252d: string | null
  obv_20d: string | null
  atr_14: string | null
  pct_from_52w_high: string | null
  pct_from_52w_low: string | null
  log_med_tv_60d: string | null
  drawdown_from_peak: string | null
}

/**
 * Return the technical feature snapshot for a single instrument.
 *
 * @param iid  - Instrument UUID string.
 * @param date - ISO date string (YYYY-MM-DD). Omit to get the latest snapshot.
 * @returns StockTechnicals, or null if the instrument has no scorecard rows.
 *
 * All numeric values are returned as decimal strings (Postgres NUMERIC →
 * string via `::text`). JSONB keys absent from the features dict return null —
 * the rendering layer must handle nulls with an em-dash fallback.
 */
export async function getStockTechnicals(
  iid: string,
  date?: string,
): Promise<StockTechnicals | null> {
  const dateParam = date ?? null

  const rows = await sql<RawRow[]>`
    SELECT
      instrument_id::text                               AS iid,
      date::text,
      -- JSONB unpack: dist_above_sma50 is the closest proxy for EMA-20/50
      (features->>'dist_above_sma50')::text            AS ema_distance_20,
      (features->>'dist_above_sma50')::text            AS ema_distance_50,
      (features->>'dist_above_sma200')::text           AS ema_distance_200,
      (features->>'rsi_14')::text                      AS rsi_14,
      -- rs_residual_6m is a first-class column (not in JSONB)
      rs_residual_6m::text                             AS rs_pct_nifty500,
      (features->>'realized_vol_252d')::text           AS vol_252d,
      (features->>'obv_slope_60d')::text               AS obv_20d,
      (features->>'atr_pct_14')::text                  AS atr_14,
      (features->>'dd_from_52w_high')::text            AS pct_from_52w_high,
      (features->>'dist_from_52w_low')::text           AS pct_from_52w_low,
      -- first-class columns
      log_med_tv_60d::text                             AS log_med_tv_60d,
      formation_max_dd::text                           AS drawdown_from_peak
    FROM atlas.atlas_scorecard_daily
    WHERE instrument_id = ${iid}::uuid
      AND date = COALESCE(
        ${dateParam}::date,
        (
          SELECT MAX(date)
          FROM atlas.atlas_scorecard_daily
          WHERE instrument_id = ${iid}::uuid
        )
      )
    LIMIT 1
  `

  if (rows.length === 0) return null

  return rows[0]
}
