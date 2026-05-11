import 'server-only'
import sql from '@/lib/db'

export type ETFRow = {
  ticker: string
  etf_name: string | null
  theme: string
  linked_sector: string | null
  asset_class: string | null
  fund_house: string | null
  // Metrics
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  rs_pctile_3m: string | null
  ema_10_ratio: string | null
  extension_pct: string | null
  ret_1w: string | null
  vol_63: string | null
  drawdown: string | null
  days_in_state: number | null
  // States (3-tuple)
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  weinstein_gate_pass: boolean | null
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  // Decisions
  is_investable: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
  risk_gate: boolean | null
  sector_gate: boolean | null
  market_gate: boolean | null
  position_size_pct: string | null
}

export type ETFMetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  ret_3m: string | null
  ema_10_ratio: string | null
}

export type ETFStateHistoryRow = {
  date: Date
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
}

export async function getAllETFs(): Promise<ETFRow[]> {
  return sql<ETFRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.asset_class,
      u.fund_house,
      m.ret_1m::text          AS ret_1m,
      m.ret_3m::text          AS ret_3m,
      m.ret_6m::text          AS ret_6m,
      m.rs_pctile_3m::text    AS rs_pctile_3m,
      m.ema_10_ratio::text    AS ema_10_ratio,
      m.extension_pct::text   AS extension_pct,
      m.ret_1w::text              AS ret_1w,
      m.realized_vol_63::text     AS vol_63,
      m.drawdown_ratio_252::text  AS drawdown,
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.is_investable,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.sector_gate,
      d.market_gate,
      d.position_size_pct::text AS position_size_pct
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = l.d
    LEFT JOIN atlas.atlas_etf_decisions_daily d
      ON d.ticker = u.ticker AND d.date = l.d
    WHERE u.effective_to IS NULL
    ORDER BY
      d.is_investable DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `
}

export async function getETFByTicker(ticker: string): Promise<ETFRow | null> {
  const rows = await sql<ETFRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.asset_class,
      u.fund_house,
      m.ret_1m::text          AS ret_1m,
      m.ret_3m::text          AS ret_3m,
      m.ret_6m::text          AS ret_6m,
      m.rs_pctile_3m::text    AS rs_pctile_3m,
      m.ema_10_ratio::text    AS ema_10_ratio,
      m.extension_pct::text   AS extension_pct,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.is_investable,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.sector_gate,
      d.market_gate,
      d.position_size_pct::text AS position_size_pct
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = l.d
    LEFT JOIN atlas.atlas_etf_decisions_daily d
      ON d.ticker = u.ticker AND d.date = l.d
    WHERE u.ticker = ${ticker}
      AND u.effective_to IS NULL
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getETFMetricHistory(
  ticker: string,
  days = 180,
): Promise<ETFMetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<ETFMetricHistoryRow[]>`
    SELECT
      date,
      rs_pctile_3m::text  AS rs_pctile_3m,
      ret_3m::text        AS ret_3m,
      ema_10_ratio::text  AS ema_10_ratio
    FROM atlas.atlas_etf_metrics_daily
    WHERE ticker = ${ticker}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}

export async function getETFStateHistory(
  ticker: string,
  days = 180,
): Promise<ETFStateHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<ETFStateHistoryRow[]>`
    SELECT
      date,
      rs_state,
      momentum_state,
      risk_state
    FROM atlas.atlas_etf_states_daily
    WHERE ticker = ${ticker}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}
