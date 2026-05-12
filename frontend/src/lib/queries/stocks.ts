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
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
  risk_gate: boolean | null
  volume_gate: boolean | null
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
  sector_gate: boolean | null
  market_gate: boolean | null
  transition_trigger: boolean | null
  breakout_trigger: boolean | null
  exit_market_riskoff: boolean | null
  exit_sector_avoid: boolean | null
  exit_rs_deteriorate: boolean | null
  exit_momentum_collapse: boolean | null
  exit_volume_distrib: boolean | null
  exit_stop_loss: boolean | null
  stage: number | null
  is_ppc: boolean | null
  is_npc: boolean | null
  is_contraction: boolean | null
  trigger_level: string | null
  ppc_strength: string | null
  signal_date: string | null
}

export type FullStockRow = StockRowWithSector

export type MetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  ret_3m: string | null
  ema_10_ratio: string | null
  drawdown_ratio_252: string | null
  avg_volume_20: string | null
  extension_pct: string | null
  atr_21: string | null
  ema_20_ratio: string | null
  vol_ratio_63: string | null
  max_drawdown_252: string | null
}

export type StateHistoryRow = {
  date: Date
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
}

export async function getAllStocks(): Promise<StockRowWithSector[]> {
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
      m.weinstein_gate_pass,
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
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.volume_gate,
      d.sector_gate,
      d.market_gate,
      d.transition_trigger,
      d.breakout_trigger,
      d.exit_market_riskoff,
      d.exit_sector_avoid,
      d.exit_rs_deteriorate,
      d.exit_momentum_collapse,
      d.exit_volume_distrib,
      d.exit_stop_loss,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      CASE
        WHEN m.ret_3m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_3m IS NOT NULL AND b.n500_3m > 0
        THEN (m.ret_3m - (b.n500_now - b.n500_3m) / b.n500_3m)::text
        ELSE NULL
      END AS alpha_3m,
      CASE
        WHEN m.ret_6m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_6m IS NOT NULL AND b.n500_6m > 0
        THEN (m.ret_6m - (b.n500_now - b.n500_6m) / b.n500_6m)::text
        ELSE NULL
      END AS alpha_6m,
      cts.stage,
      cts.is_ppc,
      cts.is_npc,
      cts.is_contraction,
      cts.trigger_level::text  AS trigger_level,
      cts.ppc_strength::text   AS ppc_strength,
      cts.date::text           AS signal_date
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    CROSS JOIN benchmark b
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id AND s.date = l.d
    LEFT JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
    LEFT JOIN atlas.atlas_cts_signals_daily cts
      ON cts.instrument_id = u.instrument_id
      AND cts.date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
    WHERE u.effective_to IS NULL
    ORDER BY
      d.is_investable DESC NULLS LAST,
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
      m.weinstein_gate_pass,
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
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.volume_gate,
      d.sector_gate,
      d.market_gate,
      d.transition_trigger,
      d.breakout_trigger,
      d.exit_market_riskoff,
      d.exit_sector_avoid,
      d.exit_rs_deteriorate,
      d.exit_momentum_collapse,
      d.exit_volume_distrib,
      d.exit_stop_loss,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      NULL::text AS alpha_3m,
      NULL::text AS alpha_6m
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id AND s.date = l.d
    JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
    WHERE u.effective_to IS NULL
      AND d.is_investable = true
      AND s.rs_state IN ('Leader', 'Strong')
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
      m.weinstein_gate_pass,
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
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.volume_gate,
      d.sector_gate,
      d.market_gate,
      d.transition_trigger,
      d.breakout_trigger,
      d.exit_market_riskoff,
      d.exit_sector_avoid,
      d.exit_rs_deteriorate,
      d.exit_momentum_collapse,
      d.exit_volume_distrib,
      d.exit_stop_loss,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      CASE
        WHEN m.ret_3m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_3m IS NOT NULL AND b.n500_3m > 0
        THEN (m.ret_3m - (b.n500_now - b.n500_3m) / b.n500_3m)::text
        ELSE NULL
      END AS alpha_3m,
      CASE
        WHEN m.ret_6m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_6m IS NOT NULL AND b.n500_6m > 0
        THEN (m.ret_6m - (b.n500_now - b.n500_6m) / b.n500_6m)::text
        ELSE NULL
      END AS alpha_6m,
      cts.stage,
      cts.is_ppc,
      cts.is_npc,
      cts.is_contraction,
      cts.trigger_level::text  AS trigger_level,
      cts.ppc_strength::text   AS ppc_strength,
      cts.date::text           AS signal_date
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    CROSS JOIN benchmark b
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id AND s.date = l.d
    LEFT JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
    LEFT JOIN atlas.atlas_cts_signals_daily cts
      ON cts.instrument_id = u.instrument_id
      AND cts.date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
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
      date,
      rs_pctile_3m::text        AS rs_pctile_3m,
      ret_3m::text              AS ret_3m,
      ema_10_ratio::text        AS ema_10_ratio,
      drawdown_ratio_252::text  AS drawdown_ratio_252,
      avg_volume_20::text       AS avg_volume_20,
      extension_pct::text       AS extension_pct,
      atr_21::text              AS atr_21,
      ema_20_ratio::text        AS ema_20_ratio,
      vol_ratio_63::text        AS vol_ratio_63,
      max_drawdown_252::text    AS max_drawdown_252
    FROM atlas.atlas_stock_metrics_daily
    WHERE instrument_id = ${instrumentId}
      AND date >= CURRENT_DATE - INTERVAL '1 day' * ${days}
    ORDER BY date ASC
  `
}

export async function getStockStateHistory(
  instrumentId: string,
  days = 180,
): Promise<StateHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<StateHistoryRow[]>`
    SELECT
      date,
      rs_state,
      momentum_state,
      risk_state,
      volume_state
    FROM atlas.atlas_stock_states_daily
    WHERE instrument_id = ${instrumentId}
      AND date >= CURRENT_DATE - INTERVAL '1 day' * ${days}
    ORDER BY date ASC
  `
}
