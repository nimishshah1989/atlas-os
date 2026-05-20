import 'server-only'
import sql from '@/lib/db'

export type ETFRow = {
  ticker: string
  etf_name: string | null
  theme: string
  linked_sector: string | null
  linked_index: string | null
  inception_date: string | null
  asset_class: string | null
  fund_house: string | null
  data_as_of: string | null
  // Metrics
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
  rs_3m_benchmark: string | null
  ema_10_ratio: string | null
  extension_pct: string | null
  vol_63: string | null
  drawdown: string | null
  volume_expansion: string | null
  avg_volume_20: string | null
  effort_ratio_63: string | null
  above_30w_ma: boolean | null
  ema_10_at_20d_high: boolean | null
  days_in_state: number | null
  // States from atlas_etf_signal_unified
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  weinstein_gate_pass: boolean | null
  // Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
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
  breakout_trigger: boolean | null
  transition_trigger: boolean | null
  // Exit triggers — NULL pending Phase 8 removal.
  exit_market_riskoff: boolean | null
  exit_sector_avoid: boolean | null
  exit_rs_deteriorate: boolean | null
  exit_momentum_collapse: boolean | null
  exit_stop_loss: boolean | null
  // Stage: dominant_state from atlas_etf_signal_unified (engine_state column)
  engine_state: string | null
  // Phase 8: bubble chart axes — from atlas_etf_signal_unified
  mean_rs_rank_12m: number | null
  mean_within_state_rank: number | null
  // Trend strength inputs: pct_stage_2 - pct_stage_4 = trend_strength (range -1 to +1).
  // Positive = stage 2 breadth dominant (uptrend), negative = stage 4 dominant (downtrend).
  // X axis on ETFBubbleChart. Populated by atlas_etf_state_v2 via atlas_etf_signal_unified
  // after migration 089 is applied.
  pct_stage_2: number | null
  pct_stage_4: number | null
}

export type ETFMetricHistoryRow = {
  date: Date
  rs_pctile_3m: string | null
  rs_3m_benchmark: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  ema_10_ratio: string | null
  ema_20_ratio: string | null
  extension_pct: string | null
  vol_63: string | null
  drawdown: string | null
  volume_expansion: string | null
  above_30w_ma: boolean | null
}

export type ETFStateHistoryRow = {
  date: Date
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
}

// Shared SELECT columns for all ETF list queries (getAllETFs, getETFByTicker, getLinkedETFsForSector).
// Phase 7: rewired to atlas_etf_signal_unified.
// atlas_etf_signal_unified exposes: etf_ticker, date, engine_state, dominant_share,
//   n_holdings, mean_rs_rank_12m, pct_stage_2, pct_stage_3, pct_stage_4.
// rs_state / momentum_state / weinstein_gate_pass derived here from mean_rs_rank_12m / pct_stage_2.
// risk_state not in view — returns NULL.
// is_investable derived from pct_stage_4 < 0.5.
// Gate columns return TRUE; exit triggers return NULL.
// days_in_state: atlas_etf_state_v2 has no state_since_date; use NULL (dwell not yet computed for ETFs).

export async function getAllETFs(): Promise<ETFRow[]> {
  return sql<ETFRow[]>`
    WITH latest AS (
      SELECT ticker, MAX(date) AS d
      FROM atlas.atlas_etf_metrics_daily
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1w::text                AS ret_1w,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.ret_12m::text               AS ret_12m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.rs_3m_benchmark::text       AS rs_3m_benchmark,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      m.volume_expansion::text      AS volume_expansion,
      m.avg_volume_20::text         AS avg_volume_20,
      m.effort_ratio_63::text       AS effort_ratio_63,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      NULL::int                     AS days_in_state,
      -- rs_state derived from mean_rs_rank_12m (mirrors atlas_stock_signal_unified tier logic)
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                           AS rs_state,
      -- momentum_state derived from pct_stage_2 / pct_stage_4
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                           AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                           AS risk_state,
      -- weinstein_gate_pass: pct_stage_2 dominant
      (eu.pct_stage_2 IS NOT NULL AND eu.pct_stage_2 >= 0.50) AS weinstein_gate_pass,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE                          AS history_gate_pass,
      TRUE                          AS liquidity_gate_pass,
      -- is_investable: ETF stage_4 < 50% of holdings
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) AS is_investable,
      TRUE                          AS strength_gate,
      TRUE                          AS direction_gate,
      TRUE                          AS risk_gate,
      TRUE                          AS sector_gate,
      TRUE                          AS market_gate,
      NULL::text                    AS position_size_pct,
      TRUE                          AS breakout_trigger,
      TRUE                          AS transition_trigger,
      NULL::boolean                 AS exit_market_riskoff,
      NULL::boolean                 AS exit_sector_avoid,
      NULL::boolean                 AS exit_rs_deteriorate,
      NULL::boolean                 AS exit_momentum_collapse,
      NULL::boolean                 AS exit_stop_loss,
      -- Stage badge: engine_state from atlas_etf_signal_unified
      eu.engine_state,
      -- Phase 8: bubble chart axes
      eu.mean_rs_rank_12m::float8   AS mean_rs_rank_12m,
      eu.mean_within_state_rank::float8 AS mean_within_state_rank,
      eu.pct_stage_2::float8        AS pct_stage_2,
      eu.pct_stage_4::float8        AS pct_stage_4
    FROM atlas.atlas_universe_etfs u
    LEFT JOIN latest l ON l.ticker = u.ticker
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_signal_unified eu
      ON eu.etf_ticker = u.ticker AND eu.date = l.d
    WHERE u.effective_to IS NULL
    ORDER BY
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `
}

export async function getETFByTicker(ticker: string): Promise<ETFRow | null> {
  const rows = await sql<ETFRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
      WHERE ticker = ${ticker}
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1w::text                AS ret_1w,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.ret_12m::text               AS ret_12m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.rs_3m_benchmark::text       AS rs_3m_benchmark,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      m.volume_expansion::text      AS volume_expansion,
      m.avg_volume_20::text         AS avg_volume_20,
      m.effort_ratio_63::text       AS effort_ratio_63,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      NULL::int                     AS days_in_state,
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                           AS rs_state,
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                           AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                           AS risk_state,
      (eu.pct_stage_2 IS NOT NULL AND eu.pct_stage_2 >= 0.50) AS weinstein_gate_pass,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE                          AS history_gate_pass,
      TRUE                          AS liquidity_gate_pass,
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) AS is_investable,
      TRUE                          AS strength_gate,
      TRUE                          AS direction_gate,
      TRUE                          AS risk_gate,
      TRUE                          AS sector_gate,
      TRUE                          AS market_gate,
      NULL::text                    AS position_size_pct,
      TRUE                          AS breakout_trigger,
      TRUE                          AS transition_trigger,
      NULL::boolean                 AS exit_market_riskoff,
      NULL::boolean                 AS exit_sector_avoid,
      NULL::boolean                 AS exit_rs_deteriorate,
      NULL::boolean                 AS exit_momentum_collapse,
      NULL::boolean                 AS exit_stop_loss,
      -- Stage badge: engine_state from atlas_etf_signal_unified
      eu.engine_state,
      -- Phase 8: bubble chart axes
      eu.mean_rs_rank_12m::float8   AS mean_rs_rank_12m,
      eu.mean_within_state_rank::float8 AS mean_within_state_rank,
      eu.pct_stage_2::float8        AS pct_stage_2,
      eu.pct_stage_4::float8        AS pct_stage_4
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_signal_unified eu
      ON eu.etf_ticker = u.ticker AND eu.date = l.d
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
      rs_pctile_3m::text        AS rs_pctile_3m,
      rs_3m_benchmark::text     AS rs_3m_benchmark,
      ret_1m::text              AS ret_1m,
      ret_3m::text              AS ret_3m,
      ret_6m::text              AS ret_6m,
      ret_12m::text             AS ret_12m,
      ema_10_ratio::text        AS ema_10_ratio,
      ema_20_ratio::text        AS ema_20_ratio,
      extension_pct::text       AS extension_pct,
      realized_vol_63::text     AS vol_63,
      drawdown_ratio_252::text  AS drawdown,
      volume_expansion::text    AS volume_expansion,
      above_30w_ma
    FROM atlas.atlas_etf_metrics_daily
    WHERE ticker = ${ticker}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}

// Phase 7: getETFStateHistory rewired to atlas_etf_signal_unified.
// risk_state derived from atlas_etf_metrics_daily.realized_vol_63 via NTILE quartile.
export async function getETFStateHistory(
  ticker: string,
  days = 180,
): Promise<ETFStateHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<ETFStateHistoryRow[]>`
    WITH vol_window AS (
      SELECT date, realized_vol_63
      FROM atlas.atlas_etf_metrics_daily
      WHERE ticker = ${ticker}
        AND date >= CURRENT_DATE - (${days} || ' days')::interval
    )
    SELECT
      eu.date,
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                       AS rs_state,
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                       AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY vw.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                       AS risk_state
    FROM atlas.atlas_etf_signal_unified eu
    LEFT JOIN vol_window vw ON vw.date = eu.date
    WHERE eu.etf_ticker = ${ticker}
      AND eu.date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY eu.date ASC
  `
}

export type ETFHoldingRow = {
  symbol: string | null
  company_name: string | null
  weight: string | null
  sector: string | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  ret_1m: string | null
  ret_3m: string | null
  holdings_date: string | null
}

export async function getLinkedETFsForSector(sectorName: string): Promise<ETFRow[]> {
  return sql<ETFRow[]>`
    WITH latest AS (
      SELECT ticker, MAX(date) AS d
      FROM atlas.atlas_etf_metrics_daily
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1w::text                AS ret_1w,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.ret_12m::text               AS ret_12m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.rs_3m_benchmark::text       AS rs_3m_benchmark,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      m.volume_expansion::text      AS volume_expansion,
      m.avg_volume_20::text         AS avg_volume_20,
      m.effort_ratio_63::text       AS effort_ratio_63,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      NULL::int                     AS days_in_state,
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                           AS rs_state,
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                           AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                           AS risk_state,
      (eu.pct_stage_2 IS NOT NULL AND eu.pct_stage_2 >= 0.50) AS weinstein_gate_pass,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE                          AS history_gate_pass,
      TRUE                          AS liquidity_gate_pass,
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) AS is_investable,
      TRUE                          AS strength_gate,
      TRUE                          AS direction_gate,
      TRUE                          AS risk_gate,
      TRUE                          AS sector_gate,
      TRUE                          AS market_gate,
      NULL::text                    AS position_size_pct,
      TRUE                          AS breakout_trigger,
      TRUE                          AS transition_trigger,
      NULL::boolean                 AS exit_market_riskoff,
      NULL::boolean                 AS exit_sector_avoid,
      NULL::boolean                 AS exit_rs_deteriorate,
      NULL::boolean                 AS exit_momentum_collapse,
      NULL::boolean                 AS exit_stop_loss,
      -- Stage badge: engine_state from atlas_etf_signal_unified
      eu.engine_state,
      -- Phase 8: bubble chart axes
      eu.mean_rs_rank_12m::float8   AS mean_rs_rank_12m,
      eu.mean_within_state_rank::float8 AS mean_within_state_rank,
      eu.pct_stage_2::float8        AS pct_stage_2,
      eu.pct_stage_4::float8        AS pct_stage_4
    FROM atlas.atlas_universe_etfs u
    LEFT JOIN latest l ON l.ticker = u.ticker
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_signal_unified eu
      ON eu.etf_ticker = u.ticker AND eu.date = l.d
    WHERE u.linked_sector = ${sectorName}
      AND u.effective_to IS NULL
    ORDER BY m.rs_pctile_3m DESC NULLS LAST
  `
}

// Phase 7: getETFHoldings rewired — stock states from atlas_stock_signal_unified.
export async function getETFHoldings(ticker: string, limit = 20): Promise<ETFHoldingRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error(`limit must be between 1 and 100, got: ${limit}`)
  }
  return sql<ETFHoldingRow[]>`
    WITH latest_holdings AS (
      SELECT MAX(as_of_date) AS as_of_date
      FROM public.de_etf_holdings
      WHERE ticker = ${ticker}
    ),
    latest_states_date AS (
      SELECT MAX(date) AS d
      FROM atlas.atlas_stock_signal_unified
      WHERE date <= COALESCE((SELECT as_of_date FROM latest_holdings), CURRENT_DATE)
    )
    SELECT
      u.symbol,
      u.company_name,
      h.weight::text            AS weight,
      u.sector,
      su.rs_state,
      su.momentum_state,
      NULL::text                AS risk_state,
      m.ret_1m::text            AS ret_1m,
      m.ret_3m::text            AS ret_3m,
      lh.as_of_date::text       AS holdings_date
    FROM public.de_etf_holdings h
    JOIN latest_holdings lh ON h.ticker = ${ticker}
      AND h.as_of_date = lh.as_of_date
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = h.instrument_id
      AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id
      AND su.date = (SELECT d FROM latest_states_date)
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
      AND m.date = (SELECT d FROM latest_states_date)
    WHERE h.ticker = ${ticker}
    ORDER BY h.weight DESC
    LIMIT ${limit}
  `
}
