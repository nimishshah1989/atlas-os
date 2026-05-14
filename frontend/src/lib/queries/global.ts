import 'server-only'
import sql from '@/lib/db'


export type GlobalRegimeRow = {
  date: string
  benchmark_close: string | null
  benchmark_ema_50: string | null
  benchmark_ema_200: string | null
  benchmark_ema_50_slope: string | null
  benchmark_ema_200_slope: string | null
  benchmark_above_ema_50: boolean | null
  benchmark_above_ema_200: boolean | null
  realized_vol_5d: string | null
  vol_252_median: string | null
  pct_countries_above_200dma: string | null
  pct_countries_above_50dma: string | null
  regime_state: string | null
  dislocation_flag: boolean
}

export async function getGlobalRegime(): Promise<GlobalRegimeRow | null> {
  const rows = await sql<GlobalRegimeRow[]>`
    SELECT
      date::text,
      benchmark_close::text,
      benchmark_ema_50::text,
      benchmark_ema_200::text,
      benchmark_ema_50_slope::text,
      benchmark_ema_200_slope::text,
      benchmark_above_ema_50,
      benchmark_above_ema_200,
      realized_vol_5d::text,
      vol_252_median::text,
      pct_countries_above_200dma::text,
      pct_countries_above_50dma::text,
      regime_state,
      dislocation_flag
    FROM global_atlas.atlas_market_regime_daily
    ORDER BY date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getCountryRankings(): Promise<CountryRow[]> {
  return sql<CountryRow[]>`
    WITH latest_date AS (
      SELECT MAX(date) AS d FROM global_atlas.atlas_etf_metrics_daily
    ),
    rs_pivot AS (
      SELECT
        ticker,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_acwi,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '12m' THEN rs_quintile END) AS q_12m_vt,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '12m' THEN rs_quintile END) AS q_12m_eem,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_gold,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_pctile   END) AS pctile_3m_vt
      FROM global_atlas.atlas_etf_rs_states
      WHERE date = (SELECT d FROM latest_date)
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.country,
      u.region,
      u.is_developed_market,
      m.ret_1w::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_12m::text,
      m.above_30w_ma,
      m.ema_10_ratio::text,
      m.realized_vol_63::text,
      s.rs_state,
      r.q_1m_acwi,
      r.q_3m_acwi,
      r.q_12m_acwi,
      r.q_1m_vt,
      r.q_3m_vt,
      r.q_12m_vt,
      r.q_1m_eem,
      r.q_3m_eem,
      r.q_12m_eem,
      r.q_1m_gold,
      r.q_3m_gold,
      r.q_12m_gold,
      m.rs_consensus_bullish,
      m.rs_consensus_bearish,
      r.pctile_3m_vt::text,
      (SELECT d FROM latest_date)::text AS data_as_of
    FROM global_atlas.atlas_universe_etfs u
    LEFT JOIN rs_pivot r ON r.ticker = u.ticker
    LEFT JOIN global_atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = (SELECT d FROM latest_date)
    LEFT JOIN global_atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = (SELECT d FROM latest_date)
    WHERE u.is_active = TRUE
    ORDER BY r.pctile_3m_vt DESC NULLS LAST
  `
}

export type GlobalRegimeHistoryRow = {
  date: string
  regime_state: string | null
  benchmark_close: string | null
  benchmark_ema_50_slope: string | null
  benchmark_ema_200_slope: string | null
  benchmark_above_ema_50: boolean | null
  benchmark_above_ema_200: boolean | null
  pct_countries_above_50dma: string | null
  pct_countries_above_200dma: string | null
  realized_vol_5d: string | null
}

export async function getGlobalRegimeHistory(days = 252): Promise<GlobalRegimeHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be between 1 and 3650, got: ${days}`)
  }
  return sql<GlobalRegimeHistoryRow[]>`
    SELECT
      date::text,
      regime_state,
      benchmark_close::text,
      benchmark_ema_50_slope::text,
      benchmark_ema_200_slope::text,
      benchmark_above_ema_50,
      benchmark_above_ema_200,
      pct_countries_above_50dma::text,
      pct_countries_above_200dma::text,
      realized_vol_5d::text
    FROM global_atlas.atlas_market_regime_daily
    WHERE date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}

export type CountryRow = {
  ticker: string
  country: string
  region: string
  is_developed_market: boolean
  // Core returns
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_12m: string | null
  // EMA trend + volatility
  above_30w_ma: boolean | null
  ema_10_ratio: string | null
  realized_vol_63: string | null
  // RS state (derived from quintile)
  rs_state: string | null
  // RS quintiles — 4 benchmarks × 3 key timeframes
  q_1m_acwi: number | null
  q_3m_acwi: number | null
  q_12m_acwi: number | null
  q_1m_vt: number | null
  q_3m_vt: number | null
  q_12m_vt: number | null
  q_1m_eem: number | null
  q_3m_eem: number | null
  q_12m_eem: number | null
  q_1m_gold: number | null
  q_3m_gold: number | null
  q_12m_gold: number | null
  // Consensus (0-20 cells)
  rs_consensus_bullish: number | null
  rs_consensus_bearish: number | null
  // Sort key: VT 3m RS percentile (continuous, for ranking within Q)
  pctile_3m_vt: string | null
  data_as_of: string | null
}

export type CountryDetailRow = CountryRow & {
  ret_6m: string | null
  extension_pct: string | null
  volume_expansion: string | null
  max_drawdown_252: string | null
  momentum_state: string | null
  risk_state: string | null
  weinstein_gate_pass: boolean | null
}

export type CountryMetricHistoryRow = {
  date: string
  pctile_3m_vt: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_12m: string | null
  ema_10_ratio: string | null
  realized_vol_63: string | null
  extension_pct: string | null
  max_drawdown_252: string | null
  volume_expansion: string | null
  above_30w_ma: boolean | null
}

export type CountryStateHistoryRow = {
  date: string
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
}

export async function getCountryByTicker(ticker: string): Promise<CountryDetailRow | null> {
  const rows = await sql<CountryDetailRow[]>`
    WITH latest_date AS (
      SELECT MAX(date) AS d FROM global_atlas.atlas_etf_metrics_daily
    ),
    rs_pivot AS (
      SELECT
        ticker,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_acwi,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '12m' THEN rs_quintile END) AS q_12m_vt,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '12m' THEN rs_quintile END) AS q_12m_eem,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_gold,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_pctile   END) AS pctile_3m_vt
      FROM global_atlas.atlas_etf_rs_states
      WHERE date = (SELECT d FROM latest_date)
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.country,
      u.region,
      u.is_developed_market,
      m.ret_1w::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_6m::text,
      m.ret_12m::text,
      m.above_30w_ma,
      m.ema_10_ratio::text,
      m.realized_vol_63::text,
      m.extension_pct::text,
      m.max_drawdown_252::text,
      m.volume_expansion::text,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      r.q_1m_acwi,
      r.q_3m_acwi,
      r.q_12m_acwi,
      r.q_1m_vt,
      r.q_3m_vt,
      r.q_12m_vt,
      r.q_1m_eem,
      r.q_3m_eem,
      r.q_12m_eem,
      r.q_1m_gold,
      r.q_3m_gold,
      r.q_12m_gold,
      m.rs_consensus_bullish,
      m.rs_consensus_bearish,
      r.pctile_3m_vt::text,
      (SELECT d FROM latest_date)::text AS data_as_of
    FROM global_atlas.atlas_universe_etfs u
    LEFT JOIN rs_pivot r ON r.ticker = u.ticker
    LEFT JOIN global_atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = (SELECT d FROM latest_date)
    LEFT JOIN global_atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = (SELECT d FROM latest_date)
    WHERE u.ticker = ${ticker}
      AND u.is_active = TRUE
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getCountryMetricHistory(ticker: string, days = 252): Promise<CountryMetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be between 1 and 3650, got: ${days}`)
  }
  return sql<CountryMetricHistoryRow[]>`
    WITH rs_pctile AS (
      SELECT date, rs_pctile AS pctile_3m_vt
      FROM global_atlas.atlas_etf_rs_states
      WHERE ticker = ${ticker}
        AND benchmark = 'vt'
        AND timeframe = '3m'
    )
    SELECT
      m.date::text,
      r.pctile_3m_vt::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_12m::text,
      m.ema_10_ratio::text,
      m.realized_vol_63::text,
      m.extension_pct::text,
      m.max_drawdown_252::text,
      m.volume_expansion::text,
      m.above_30w_ma
    FROM global_atlas.atlas_etf_metrics_daily m
    LEFT JOIN rs_pctile r ON r.date = m.date
    WHERE m.ticker = ${ticker}
      AND m.date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY m.date ASC
  `
}

export async function getCountryStateHistory(ticker: string, days = 252): Promise<CountryStateHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be between 1 and 3650, got: ${days}`)
  }
  return sql<CountryStateHistoryRow[]>`
    SELECT
      date::text,
      rs_state,
      momentum_state,
      risk_state
    FROM global_atlas.atlas_etf_states_daily
    WHERE ticker = ${ticker}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
}
