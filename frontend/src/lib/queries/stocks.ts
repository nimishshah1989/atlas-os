import 'server-only'
import sql from '@/lib/db'
import type { StockRow } from './sector-deep-dive'

export type StockRowWithSector = StockRow & {
  sector: string
  above_30w_ma: boolean | null
}

export type FullStockRow = StockRowWithSector & {
  ret_12m?: string | null
  avg_volume_20?: string | null
  realized_vol_63?: string | null
}

export type MetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  rs_3m_nifty500: string | null
  ret_3m: string | null
  ema_10_ratio: string | null
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
      m.rs_3m_tier::text              AS rs_3m_nifty500,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.rs_3m_tier_gold::text         AS rs_3m_tier_gold,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      m.weinstein_gate_pass,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      d.position_size_pct::text       AS position_size_pct
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id AND s.date = l.d
    LEFT JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
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
      m.rs_3m_tier::text              AS rs_3m_nifty500,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.rs_3m_tier_gold::text         AS rs_3m_tier_gold,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      m.weinstein_gate_pass,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      d.position_size_pct::text       AS position_size_pct
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
      m.rs_3m_tier::text              AS rs_3m_nifty500,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.rs_3m_tier_gold::text         AS rs_3m_tier_gold,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      m.weinstein_gate_pass,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      d.position_size_pct::text       AS position_size_pct
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id AND s.date = l.d
    LEFT JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
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
      rs_pctile_3m::text   AS rs_pctile_3m,
      rs_3m_tier::text     AS rs_3m_nifty500,
      ret_3m::text         AS ret_3m,
      ema_10_ratio::text   AS ema_10_ratio
    FROM atlas.atlas_stock_metrics_daily
    WHERE instrument_id = ${instrumentId}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
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
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}
