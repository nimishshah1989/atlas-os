import 'server-only'
import sql from '@/lib/db'

export type USSectorRow = {
  gics_sector: string
  constituent_count: number
  live_count: number
  // Avg returns across live stocks
  avg_ret_1m: string | null
  avg_ret_3m: string | null
  avg_ret_6m: string | null
  // RS (primary: VT benchmark)
  avg_rs_pctile_3m_vt: string | null
  avg_rs_pctile_1m_vt: string | null
  // RS momentum = avg(rs_pctile_1m) - avg(rs_pctile_3m)
  // Positive = recent RS accelerating, negative = deteriorating
  rs_momentum: string | null
  // Breadth
  participation_rs: string | null  // % in Leader/Strong (0–100)
  participation_30w: string | null  // % above 30W MA (0–100)
  // State distribution counts
  rs_state_leader: number
  rs_state_strong: number
  rs_state_consolidating: number
  rs_state_emerging: number
  rs_state_average: number
  rs_state_weak: number
  rs_state_laggard: number
  // Risk / vol
  avg_vol_63: string | null
  avg_drawdown: string | null
  avg_extension_pct: string | null
  data_as_of: string | null
}

export type USSectorRRGPoint = {
  gics_sector: string
  date: string
  avg_rs_pctile_3m_vt: string | null
  rs_momentum: string | null
}

export type USSectorStockRow = {
  ticker: string
  company_name: string | null
  rs_state: string | null
  momentum_state: string | null
  above_30w_ma: boolean | null
  rs_pctile_3m_vt: string | null
  rs_pctile_1m_vt: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  extension_pct: string | null
  max_drawdown_252: string | null
  realized_vol_63: string | null
}

export type USSectorMetricHistoryRow = {
  date: string
  avg_rs_pctile_3m_vt: string | null
  avg_rs_pctile_1m_vt: string | null
  avg_ret_1m: string | null
  avg_ret_3m: string | null
  participation_rs: string | null
}

export async function getUSSectorSummary(): Promise<USSectorRow[]> {
  return sql<USSectorRow[]>`
    WITH latest_date AS (
      SELECT MAX(date) AS d FROM us_atlas.atlas_stock_states_daily
    ),
    live_stocks AS (
      SELECT
        s.ticker,
        s.gics_sector,
        s.rs_state,
        s.above_30w_ma,
        m.rs_pctile_3m_vt,
        m.rs_pctile_1m_vt,
        m.ret_1m,
        m.ret_3m,
        m.ret_6m,
        m.realized_vol_63,
        m.max_drawdown_252,
        m.extension_pct
      FROM us_atlas.atlas_stock_states_daily s
      JOIN us_atlas.atlas_stock_metrics_daily m ON m.ticker = s.ticker AND m.date = s.date
      JOIN us_atlas.atlas_universe_stocks u ON u.ticker = s.ticker
      CROSS JOIN latest_date ld
      WHERE s.date = ld.d
        AND u.is_active = true
        AND s.gics_sector IS NOT NULL
        AND s.history_gate_pass = true
        AND s.liquidity_gate_pass = true
    )
    SELECT
      gics_sector,
      COUNT(*)::int                                                                      AS live_count,
      COUNT(*)::int                                                                      AS constituent_count,
      AVG(ret_1m)::text                                                                  AS avg_ret_1m,
      AVG(ret_3m)::text                                                                  AS avg_ret_3m,
      AVG(ret_6m)::text                                                                  AS avg_ret_6m,
      AVG(rs_pctile_3m_vt)::text                                                         AS avg_rs_pctile_3m_vt,
      AVG(rs_pctile_1m_vt)::text                                                         AS avg_rs_pctile_1m_vt,
      (AVG(rs_pctile_1m_vt) - AVG(rs_pctile_3m_vt))::text                               AS rs_momentum,
      (100.0 * COUNT(CASE WHEN rs_state IN ('Leader','Strong') THEN 1 END)
               / NULLIF(COUNT(*), 0))::text                                              AS participation_rs,
      (100.0 * COUNT(CASE WHEN above_30w_ma = true THEN 1 END)
               / NULLIF(COUNT(*), 0))::text                                              AS participation_30w,
      COUNT(CASE WHEN rs_state = 'Leader'        THEN 1 END)::int                       AS rs_state_leader,
      COUNT(CASE WHEN rs_state = 'Strong'        THEN 1 END)::int                       AS rs_state_strong,
      COUNT(CASE WHEN rs_state = 'Consolidating' THEN 1 END)::int                       AS rs_state_consolidating,
      COUNT(CASE WHEN rs_state = 'Emerging'      THEN 1 END)::int                       AS rs_state_emerging,
      COUNT(CASE WHEN rs_state = 'Average'       THEN 1 END)::int                       AS rs_state_average,
      COUNT(CASE WHEN rs_state = 'Weak'          THEN 1 END)::int                       AS rs_state_weak,
      COUNT(CASE WHEN rs_state = 'Laggard'       THEN 1 END)::int                       AS rs_state_laggard,
      AVG(realized_vol_63)::text                                                         AS avg_vol_63,
      AVG(max_drawdown_252)::text                                                        AS avg_drawdown,
      AVG(extension_pct)::text                                                           AS avg_extension_pct,
      (SELECT d::text FROM latest_date)                                                  AS data_as_of
    FROM live_stocks
    GROUP BY gics_sector
    ORDER BY AVG(rs_pctile_3m_vt) DESC NULLS LAST
  `
}

export async function getUSSectorByName(sectorName: string): Promise<USSectorRow | null> {
  const rows = await getUSSectorSummary()
  return rows.find(r => r.gics_sector === sectorName) ?? null
}

export async function getUSStocksInSector(sectorName: string): Promise<USSectorStockRow[]> {
  return sql<USSectorStockRow[]>`
    WITH latest_date AS (
      SELECT MAX(date) AS d FROM us_atlas.atlas_stock_states_daily
    )
    SELECT
      u.ticker,
      i.name                    AS company_name,
      s.rs_state,
      s.momentum_state,
      s.above_30w_ma,
      m.rs_pctile_3m_vt::text,
      m.rs_pctile_1m_vt::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_6m::text,
      m.extension_pct::text,
      m.max_drawdown_252::text,
      m.realized_vol_63::text
    FROM us_atlas.atlas_universe_stocks u
    LEFT JOIN us_atlas.instruments i ON i.ticker = u.ticker
    JOIN us_atlas.atlas_stock_states_daily s ON s.ticker = u.ticker
    JOIN us_atlas.atlas_stock_metrics_daily m ON m.ticker = u.ticker AND m.date = s.date
    CROSS JOIN latest_date ld
    WHERE s.date = ld.d
      AND u.is_active = true
      AND s.gics_sector = ${sectorName}
      AND s.history_gate_pass = true
      AND s.liquidity_gate_pass = true
    ORDER BY m.rs_pctile_3m_vt DESC NULLS LAST
  `
}

export async function getUSSectorMetricHistory(sectorName: string, days = 126): Promise<USSectorMetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be between 1 and 3650, got: ${days}`)
  }
  return sql<USSectorMetricHistoryRow[]>`
    SELECT
      m.date::text,
      AVG(m.rs_pctile_3m_vt)::text   AS avg_rs_pctile_3m_vt,
      AVG(m.rs_pctile_1m_vt)::text   AS avg_rs_pctile_1m_vt,
      AVG(m.ret_1m)::text            AS avg_ret_1m,
      AVG(m.ret_3m)::text            AS avg_ret_3m,
      (100.0 * COUNT(CASE WHEN s.rs_state IN ('Leader','Strong') THEN 1 END)
               / NULLIF(COUNT(*), 0))::text AS participation_rs
    FROM us_atlas.atlas_stock_metrics_daily m
    JOIN us_atlas.atlas_stock_states_daily s ON s.ticker = m.ticker AND s.date = m.date
    JOIN us_atlas.atlas_universe_stocks u ON u.ticker = m.ticker
    WHERE s.gics_sector = ${sectorName}
      AND u.is_active = true
      AND s.history_gate_pass = true
      AND s.liquidity_gate_pass = true
      AND m.date >= CURRENT_DATE - (${days} || ' days')::interval
    GROUP BY m.date
    ORDER BY m.date ASC
  `
}

export async function getUSSectorRRGHistory(): Promise<USSectorRRGPoint[]> {
  return sql<USSectorRRGPoint[]>`
    WITH trading_dates AS (
      SELECT DISTINCT date
      FROM us_atlas.atlas_stock_metrics_daily
      ORDER BY date DESC
      LIMIT 21
    )
    SELECT
      s.gics_sector,
      m.date::text                                                AS date,
      AVG(m.rs_pctile_3m_vt)::text                               AS avg_rs_pctile_3m_vt,
      (AVG(m.rs_pctile_1m_vt) - AVG(m.rs_pctile_3m_vt))::text   AS rs_momentum
    FROM us_atlas.atlas_stock_metrics_daily m
    JOIN us_atlas.atlas_stock_states_daily s ON s.ticker = m.ticker AND s.date = m.date
    JOIN us_atlas.atlas_universe_stocks u ON u.ticker = m.ticker
    WHERE m.date IN (SELECT date FROM trading_dates)
      AND u.is_active = true
      AND s.gics_sector IS NOT NULL
      AND s.history_gate_pass = true
      AND s.liquidity_gate_pass = true
    GROUP BY s.gics_sector, m.date
    ORDER BY s.gics_sector, m.date DESC
  `
}
