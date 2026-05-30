// allow-large: stocks query module — multiple cohesive queries (getAllStocks, getTopPicks, RSLeaders, stock detail, history) share the same SELECT shape and benefit from co-location for grep + refactor
import 'server-only'
import sql from '@/lib/db'
import type { StockRow } from './sector-deep-dive'

export type StockRowWithSector = StockRow & {
  sector: string
  above_30w_ma: boolean | null
  ret_1w: string | null
  extension_pct: string | null
  vol_63: string | null
  drawdown: string | null
  days_in_state: number | null
  // Gate columns — used by screener legend, sector quality panel, stocks table.
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
  risk_gate: boolean | null
  volume_gate: boolean | null
  sector_gate: boolean | null
  market_gate: boolean | null
  above_50d_ma: boolean | null
  above_200d_ma: boolean | null
  ret_12m: string | null
  ret_1d: string | null
  rs_pctile_1w: string | null
  realized_vol_63: string | null
  avg_volume_20: string | null
  alpha_3m: string | null
  alpha_6m: string | null
  rs_pctile_1m: string | null
  vol_ratio_63: string | null
  max_drawdown_252: string | null
  volume_expansion: string | null
  effort_ratio_63: string | null
  ema_20_ratio: string | null
  ma_30w_slope_4w: string | null
  atr_21: string | null
  // IC-validated state engine surface (from atlas_stock_signal_unified):
  engine_state: string | null
  within_state_rank: number | null
  rs_rank_12m: number | null
  dwell_days: number | null
  urgency_score: string | null
}

export type FullStockRow = StockRowWithSector

export type MetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  ema_10_ratio: string | null
  drawdown_ratio_252: string | null
  avg_volume_20: string | null
  extension_pct: string | null
  atr_21: string | null
  ema_20_ratio: string | null
  vol_ratio_63: string | null
  max_drawdown_252: string | null
  // Alpha vs Nifty 500 (excess return = stock ret − Nifty 500 ret, same window).
  // 1w/1m/3m reuse the precomputed rs_*_nifty500 columns; 6m/12m derived from
  // atlas_index_metrics_daily (index_code 'NIFTY 500').
  alpha_1w: string | null
  alpha_1m: string | null
  alpha_3m: string | null
  alpha_6m: string | null
  alpha_12m: string | null
}

export type StateHistoryRow = {
  date: Date
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
}

export interface GetAllStocksParams {
  sectorFilter?: string
  indexFilter?: string
}

export async function getAllStocks(params?: GetAllStocksParams): Promise<StockRowWithSector[]> {
  const sector = params?.sectorFilter ?? null
  const indexName = params?.indexFilter ?? null
  return sql<StockRowWithSector[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    benchmark AS (
      SELECT
        cur.nifty500_close                          AS n500_now,
        m3.nifty500_close                           AS n500_3m,
        m6.nifty500_close                           AS n500_6m
      FROM atlas.atlas_market_regime_daily cur
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '63 days'
        ORDER BY date DESC LIMIT 1
      ) m3
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '126 days'
        ORDER BY date DESC LIMIT 1
      ) m6
      WHERE cur.date = (SELECT d FROM latest)
    )
    SELECT
      u.instrument_id::text           AS instrument_id,
      u.symbol,
      u.company_name,
      u.sector,
      u.in_nifty_50,
      u.in_nifty_100,
      u.in_nifty_500,
      m.ret_1m::text                  AS ret_1m,
      m.ret_3m::text                  AS ret_3m,
      m.ret_6m::text                  AS ret_6m,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      su.weinstein_gate_pass,
      m.ret_1w::text                       AS ret_1w,
      m.extension_pct::text                AS extension_pct,
      m.realized_vol_63::text              AS vol_63,
      m.realized_vol_63::text              AS realized_vol_63,
      m.avg_volume_20::text                AS avg_volume_20,
      m.ret_12m::text                      AS ret_12m,
      m.ret_1d::text                       AS ret_1d,
      m.rs_pctile_1w::text                 AS rs_pctile_1w,
      m.rs_pctile_1m::text                 AS rs_pctile_1m,
      m.vol_ratio_63::text                 AS vol_ratio_63,
      m.max_drawdown_252::text             AS max_drawdown_252,
      m.volume_expansion::text             AS volume_expansion,
      m.effort_ratio_63::text              AS effort_ratio_63,
      m.ema_20_ratio::text                 AS ema_20_ratio,
      m.ma_30w_slope_4w::text              AS ma_30w_slope_4w,
      m.atr_21::text                       AS atr_21,
      (m.extension_pct IS NOT NULL AND m.extension_pct > 0) AS above_200d_ma,
      (
        m.ema_200_stock IS NOT NULL
        AND m.extension_pct IS NOT NULL
        AND m.ema_50_stock IS NOT NULL
        AND m.ema_200_stock * (1 + m.extension_pct) > m.ema_50_stock
      )                                    AS above_50d_ma,
      m.drawdown_ratio_252::text           AS drawdown,
      su.dwell_days                        AS days_in_state,
      -- Gate columns: hardcoded TRUE (real gate logic moved to atlas_stock_signal_unified).
      TRUE                                 AS history_gate_pass,
      TRUE                                 AS liquidity_gate_pass,
      TRUE                                 AS strength_gate,
      TRUE                                 AS direction_gate,
      TRUE                                 AS risk_gate,
      TRUE                                 AS volume_gate,
      TRUE                                 AS sector_gate,
      TRUE                                 AS market_gate,
      su.rs_state,
      su.momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low'
        WHEN 2 THEN 'Normal'
        WHEN 3 THEN 'Elevated'
        WHEN 4 THEN 'High'
      END                                  AS risk_state,
      NULL::text                           AS volume_state,
      su.is_investable,
      su.engine_state,
      su.within_state_rank::float8         AS within_state_rank,
      su.rs_rank_12m::float8               AS rs_rank_12m,
      su.dwell_days,
      su.urgency_score,
      CASE
        WHEN m.ret_3m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_3m IS NOT NULL AND b.n500_3m > 0
        THEN (m.ret_3m - (b.n500_now - b.n500_3m) / b.n500_3m)::text
        ELSE NULL
      END AS alpha_3m,
      CASE
        WHEN m.ret_6m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_6m IS NOT NULL AND b.n500_6m > 0
        THEN (m.ret_6m - (b.n500_now - b.n500_6m) / b.n500_6m)::text
        ELSE NULL
      END AS alpha_6m
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    CROSS JOIN benchmark b
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id AND su.date = l.d
    WHERE u.effective_to IS NULL
      AND (${sector}::text IS NULL OR u.sector = ${sector}::text)
      AND (
        ${indexName}::text IS NULL
        OR (${indexName} = 'Nifty 50'  AND u.in_nifty_50  = TRUE)
        OR (${indexName} = 'Nifty 100' AND u.in_nifty_100 = TRUE)
        OR (${indexName} = 'Nifty 500' AND u.in_nifty_500 = TRUE)
      )
    ORDER BY
      su.is_investable DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `
}

export async function getTopPicksAcrossSectors(): Promise<StockRowWithSector[]> {
  return sql<StockRowWithSector[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    )
    SELECT
      u.instrument_id::text           AS instrument_id,
      u.symbol,
      u.company_name,
      u.sector,
      u.in_nifty_50,
      u.in_nifty_100,
      u.in_nifty_500,
      m.ret_1m::text                  AS ret_1m,
      m.ret_3m::text                  AS ret_3m,
      m.ret_6m::text                  AS ret_6m,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      su.weinstein_gate_pass,
      m.ret_1w::text                       AS ret_1w,
      m.extension_pct::text                AS extension_pct,
      m.realized_vol_63::text              AS vol_63,
      m.realized_vol_63::text              AS realized_vol_63,
      m.avg_volume_20::text                AS avg_volume_20,
      m.ret_12m::text                      AS ret_12m,
      m.ret_1d::text                       AS ret_1d,
      m.rs_pctile_1w::text                 AS rs_pctile_1w,
      m.rs_pctile_1m::text                 AS rs_pctile_1m,
      m.vol_ratio_63::text                 AS vol_ratio_63,
      m.max_drawdown_252::text             AS max_drawdown_252,
      m.volume_expansion::text             AS volume_expansion,
      m.effort_ratio_63::text              AS effort_ratio_63,
      m.ema_20_ratio::text                 AS ema_20_ratio,
      m.ma_30w_slope_4w::text              AS ma_30w_slope_4w,
      m.atr_21::text                       AS atr_21,
      (m.extension_pct IS NOT NULL AND m.extension_pct > 0) AS above_200d_ma,
      (
        m.ema_200_stock IS NOT NULL
        AND m.extension_pct IS NOT NULL
        AND m.ema_50_stock IS NOT NULL
        AND m.ema_200_stock * (1 + m.extension_pct) > m.ema_50_stock
      )                                    AS above_50d_ma,
      m.drawdown_ratio_252::text           AS drawdown,
      su.dwell_days                        AS days_in_state,
      -- Gate columns: hardcoded TRUE (real gate logic moved to atlas_stock_signal_unified).
      TRUE                                 AS history_gate_pass,
      TRUE                                 AS liquidity_gate_pass,
      TRUE                                 AS strength_gate,
      TRUE                                 AS direction_gate,
      TRUE                                 AS risk_gate,
      TRUE                                 AS volume_gate,
      TRUE                                 AS sector_gate,
      TRUE                                 AS market_gate,
      su.rs_state,
      su.momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low'
        WHEN 2 THEN 'Normal'
        WHEN 3 THEN 'Elevated'
        WHEN 4 THEN 'High'
      END                                  AS risk_state,
      NULL::text                           AS volume_state,
      su.is_investable,
      su.engine_state,
      su.within_state_rank::float8         AS within_state_rank,
      su.rs_rank_12m::float8               AS rs_rank_12m,
      su.dwell_days,
      su.urgency_score,
      NULL::text AS alpha_3m,
      NULL::text AS alpha_6m
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id AND su.date = l.d
    WHERE u.effective_to IS NULL
      AND su.is_investable = true
      AND su.rs_state IN ('Leader', 'Strong')
    ORDER BY m.rs_pctile_3m DESC NULLS LAST
    LIMIT 20
  `
}

export async function getStockBySymbol(symbol: string): Promise<StockRowWithSector | null> {
  const rows = await sql<StockRowWithSector[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    benchmark AS (
      SELECT
        cur.nifty500_close                          AS n500_now,
        m3.nifty500_close                           AS n500_3m,
        m6.nifty500_close                           AS n500_6m
      FROM atlas.atlas_market_regime_daily cur
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '63 days'
        ORDER BY date DESC LIMIT 1
      ) m3
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '126 days'
        ORDER BY date DESC LIMIT 1
      ) m6
      WHERE cur.date = (SELECT d FROM latest)
    )
    SELECT
      u.instrument_id::text           AS instrument_id,
      u.symbol,
      u.company_name,
      u.sector,
      u.in_nifty_50,
      u.in_nifty_100,
      u.in_nifty_500,
      m.ret_1m::text                  AS ret_1m,
      m.ret_3m::text                  AS ret_3m,
      m.ret_6m::text                  AS ret_6m,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      su.weinstein_gate_pass,
      m.ret_1w::text                       AS ret_1w,
      m.extension_pct::text                AS extension_pct,
      m.realized_vol_63::text              AS vol_63,
      m.realized_vol_63::text              AS realized_vol_63,
      m.avg_volume_20::text                AS avg_volume_20,
      m.ret_12m::text                      AS ret_12m,
      m.ret_1d::text                       AS ret_1d,
      m.rs_pctile_1w::text                 AS rs_pctile_1w,
      m.rs_pctile_1m::text                 AS rs_pctile_1m,
      m.vol_ratio_63::text                 AS vol_ratio_63,
      m.max_drawdown_252::text             AS max_drawdown_252,
      m.volume_expansion::text             AS volume_expansion,
      m.effort_ratio_63::text              AS effort_ratio_63,
      m.ema_20_ratio::text                 AS ema_20_ratio,
      m.ma_30w_slope_4w::text              AS ma_30w_slope_4w,
      m.atr_21::text                       AS atr_21,
      (m.extension_pct IS NOT NULL AND m.extension_pct > 0) AS above_200d_ma,
      (
        m.ema_200_stock IS NOT NULL
        AND m.extension_pct IS NOT NULL
        AND m.ema_50_stock IS NOT NULL
        AND m.ema_200_stock * (1 + m.extension_pct) > m.ema_50_stock
      )                                    AS above_50d_ma,
      m.drawdown_ratio_252::text           AS drawdown,
      su.dwell_days                        AS days_in_state,
      -- Gate columns: hardcoded TRUE (real gate logic moved to atlas_stock_signal_unified).
      TRUE                                 AS history_gate_pass,
      TRUE                                 AS liquidity_gate_pass,
      TRUE                                 AS strength_gate,
      TRUE                                 AS direction_gate,
      TRUE                                 AS risk_gate,
      TRUE                                 AS volume_gate,
      TRUE                                 AS sector_gate,
      TRUE                                 AS market_gate,
      su.rs_state,
      su.momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low'
        WHEN 2 THEN 'Normal'
        WHEN 3 THEN 'Elevated'
        WHEN 4 THEN 'High'
      END                                  AS risk_state,
      NULL::text                           AS volume_state,
      su.is_investable,
      su.engine_state,
      su.within_state_rank::float8         AS within_state_rank,
      su.rs_rank_12m::float8               AS rs_rank_12m,
      su.dwell_days,
      su.urgency_score,
      CASE
        WHEN m.ret_3m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_3m IS NOT NULL AND b.n500_3m > 0
        THEN (m.ret_3m - (b.n500_now - b.n500_3m) / b.n500_3m)::text
        ELSE NULL
      END AS alpha_3m,
      CASE
        WHEN m.ret_6m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_6m IS NOT NULL AND b.n500_6m > 0
        THEN (m.ret_6m - (b.n500_now - b.n500_6m) / b.n500_6m)::text
        ELSE NULL
      END AS alpha_6m
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    CROSS JOIN benchmark b
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id AND su.date = l.d
    WHERE u.symbol = ${symbol}
      AND u.effective_to IS NULL
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getStockMetricHistory(
  instrumentId: string,
  days = 180,
): Promise<MetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<MetricHistoryRow[]>`
    SELECT
      m.date,
      m.rs_pctile_3m::text        AS rs_pctile_3m,
      m.ret_1w::text              AS ret_1w,
      m.ret_1m::text              AS ret_1m,
      m.ret_3m::text              AS ret_3m,
      m.ret_6m::text              AS ret_6m,
      m.ret_12m::text             AS ret_12m,
      m.ema_10_ratio::text        AS ema_10_ratio,
      m.drawdown_ratio_252::text  AS drawdown_ratio_252,
      m.avg_volume_20::text       AS avg_volume_20,
      m.extension_pct::text       AS extension_pct,
      m.atr_21::text              AS atr_21,
      m.ema_20_ratio::text        AS ema_20_ratio,
      m.vol_ratio_63::text        AS vol_ratio_63,
      m.max_drawdown_252::text    AS max_drawdown_252,
      -- Alpha vs Nifty 500 (excess return, same window as ret_X).
      -- 1w/1m/3m: precomputed rs_*_nifty500 (= ret − Nifty500 ret).
      m.rs_1w_nifty500::text      AS alpha_1w,
      m.rs_1m_nifty500::text      AS alpha_1m,
      m.rs_3m_nifty500::text      AS alpha_3m,
      -- 6m/12m: derive from the Nifty 500 index's own ret_6m/12m on the same date.
      CASE WHEN m.ret_6m IS NOT NULL AND idx.ret_6m IS NOT NULL
        THEN (m.ret_6m - idx.ret_6m)::text END   AS alpha_6m,
      CASE WHEN m.ret_12m IS NOT NULL AND idx.ret_12m IS NOT NULL
        THEN (m.ret_12m - idx.ret_12m)::text END AS alpha_12m
    FROM atlas.atlas_stock_metrics_daily m
    LEFT JOIN atlas.atlas_index_metrics_daily idx
      ON idx.index_code = 'NIFTY 500' AND idx.date = m.date
    WHERE m.instrument_id = ${instrumentId}
      AND m.date >= CURRENT_DATE - INTERVAL '1 day' * ${days}
    ORDER BY m.date ASC
  `
}

export async function getStockStateHistory(
  instrumentId: string,
  days = 180,
): Promise<StateHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  // Phase 7: rewired to atlas_stock_signal_unified.
  // risk_state and volume_state are deprecated gate columns; returned as NULL.
  return sql<StateHistoryRow[]>`
    SELECT
      date,
      rs_state,
      momentum_state,
      NULL::text AS risk_state,
      NULL::text AS volume_state
    FROM atlas.atlas_stock_signal_unified
    WHERE instrument_id = ${instrumentId}
      AND date >= CURRENT_DATE - INTERVAL '1 day' * ${days}
    ORDER BY date ASC
  `
}

export interface OBVPoint {
  date: string
  close: number
  volume: number
  obv: number
}

/**
 * 50-day OBV series. Computed in SQL:
 *   obv = cumulative sum of (volume × sign(daily_return))
 * Returns the trailing N days for sparkline display.
 */
export async function getStockOBVSeries(
  instrumentId: string, days = 50,
): Promise<OBVPoint[]> {
  return sql<OBVPoint[]>`
    WITH base AS (
      SELECT date::text, COALESCE(close_adj, close)::float8 AS close,
             volume::float8 AS volume,
             LAG(COALESCE(close_adj, close)) OVER (ORDER BY date) AS prev_close
      FROM public.de_equity_ohlcv
      WHERE instrument_id = ${instrumentId}::uuid
      ORDER BY date DESC
      LIMIT ${days + 1}
    ),
    signed_vol AS (
      SELECT date, close, volume,
             CASE
               WHEN prev_close IS NULL THEN 0
               WHEN close > prev_close THEN volume
               WHEN close < prev_close THEN -volume
               ELSE 0
             END AS signed_volume
      FROM base
    )
    SELECT date, close, volume,
           SUM(signed_volume) OVER (ORDER BY date)::float8 AS obv
    FROM signed_vol
    ORDER BY date ASC
  `
}

export interface ATRContraction {
  atr_14_current: number
  atr_14_252d_avg: number
  ratio: number
}

/**
 * Current ATR contraction ratio = atr_14 / atr_14_252d_avg.
 * Returns null if insufficient history.
 */
export async function getStockATRContraction(
  instrumentId: string,
): Promise<ATRContraction | null> {
  const rows = await sql<ATRContraction[]>`
    WITH ohlcv AS (
      SELECT date, COALESCE(close_adj, close)::float8 AS close,
             high::float8 AS high, low::float8 AS low,
             LAG(COALESCE(close_adj, close)) OVER (ORDER BY date) AS prev_close
      FROM public.de_equity_ohlcv
      WHERE instrument_id = ${instrumentId}::uuid
      ORDER BY date DESC
      LIMIT 280
    ),
    tr AS (
      SELECT date,
             GREATEST(high - low, ABS(high - prev_close), ABS(low - prev_close)) AS true_range
      FROM ohlcv
      WHERE prev_close IS NOT NULL
    ),
    atr14 AS (
      SELECT date,
             AVG(true_range) OVER (
               ORDER BY date
               ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
             ) AS atr_14
      FROM tr
    )
    SELECT
      (SELECT atr_14 FROM atr14 ORDER BY date DESC LIMIT 1)::float8 AS atr_14_current,
      (SELECT AVG(atr_14) FROM atr14)::float8 AS atr_14_252d_avg,
      ((SELECT atr_14 FROM atr14 ORDER BY date DESC LIMIT 1)::float8
       / NULLIF((SELECT AVG(atr_14) FROM atr14)::float8, 0))::float8 AS ratio
    WHERE EXISTS (SELECT 1 FROM atr14)
  `
  return rows[0] ?? null
}

export interface StockFooterMetrics {
  obv_slope: number | null
  atr_ratio: number | null
  realized_vol_tier: string | null
}

/**
 * Footer metrics for ComponentScorecard.
 * - obv_slope: TODO: column needs migration; not yet stored in atlas_stock_metrics_daily
 * - atr_ratio: derived from getStockATRContraction()
 * - realized_vol_tier: NTILE(4) over realized_vol_63 for the day cohort -> Low/Normal/Elevated/High
 */
export async function getStockFooterMetrics(
  instrumentId: string,
): Promise<StockFooterMetrics> {
  // TODO: column needs migration; currently not stored in atlas_stock_metrics_daily
  const obv_slope: number | null = null

  // ATR ratio: derive from existing function
  const atrData = await getStockATRContraction(instrumentId)
  const atr_ratio = atrData?.ratio ?? null

  // Realized vol tier: NTILE(4) within today's cohort
  const rows = await sql<{ tier: number | null }[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    ranked AS (
      SELECT
        instrument_id,
        NTILE(4) OVER (ORDER BY realized_vol_63 ASC NULLS LAST) AS tier
      FROM atlas.atlas_stock_metrics_daily
      WHERE date = (SELECT d FROM latest)
        AND realized_vol_63 IS NOT NULL
    )
    SELECT tier
    FROM ranked
    WHERE instrument_id = ${instrumentId}::uuid
    LIMIT 1
  `

  const tierMap: Record<number, string> = { 1: 'Low', 2: 'Normal', 3: 'Elevated', 4: 'High' }
  const tierNum = rows[0]?.tier ?? null
  const realized_vol_tier = tierNum != null ? (tierMap[tierNum] ?? null) : null

  return { obv_slope, atr_ratio, realized_vol_tier }
}
