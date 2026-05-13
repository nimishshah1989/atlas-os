import 'server-only'
import sql from '@/lib/db'

export type USETFRow = {
  ticker: string
  etf_category: string | null
  linked_sector: string | null
  is_benchmark: boolean
  data_as_of: string | null
  // Returns
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  // Risk
  realized_vol_63: string | null
  max_drawdown_252: string | null
  extension_pct: string | null
  atr_21: string | null
  avg_volume_20: string | null
  volume_expansion: string | null
  ema_10_ratio: string | null
  ema_20_ratio: string | null
  above_30w_ma: boolean | null
  // RS vs VT (primary)
  rs_pctile_1m_vt: string | null
  rs_pctile_3m_vt: string | null
  rs_1m_vt: string | null
  rs_3m_vt: string | null
  // RS vs ACWI
  rs_pctile_3m_acwi: string | null
  rs_3m_acwi: string | null
  // RS vs GOLD (relevant for commodity ETFs)
  rs_pctile_3m_gold: string | null
  rs_3m_gold: string | null
  // States
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  weinstein_gate_pass: boolean | null
}

export async function getUSETFs(): Promise<USETFRow[]> {
  return sql<USETFRow[]>`
    WITH latest AS (
      SELECT ticker, MAX(date) AS d
      FROM us_atlas.atlas_etf_metrics_daily
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.etf_category,
      u.linked_sector,
      u.is_benchmark,
      l.d::text                         AS data_as_of,
      m.ret_1w::text                    AS ret_1w,
      m.ret_1m::text                    AS ret_1m,
      m.ret_3m::text                    AS ret_3m,
      m.ret_6m::text                    AS ret_6m,
      m.ret_12m::text                   AS ret_12m,
      m.realized_vol_63::text           AS realized_vol_63,
      m.max_drawdown_252::text          AS max_drawdown_252,
      m.extension_pct::text             AS extension_pct,
      m.atr_21::text                    AS atr_21,
      m.avg_volume_20::text             AS avg_volume_20,
      m.volume_expansion::text          AS volume_expansion,
      m.ema_10_ratio::text              AS ema_10_ratio,
      m.ema_20_ratio::text              AS ema_20_ratio,
      m.above_30w_ma,
      m.rs_pctile_1m_vt::text           AS rs_pctile_1m_vt,
      m.rs_pctile_3m_vt::text           AS rs_pctile_3m_vt,
      m.rs_1m_vt::text                  AS rs_1m_vt,
      m.rs_3m_vt::text                  AS rs_3m_vt,
      m.rs_pctile_3m_acwi::text         AS rs_pctile_3m_acwi,
      m.rs_3m_acwi::text                AS rs_3m_acwi,
      m.rs_pctile_3m_gold::text         AS rs_pctile_3m_gold,
      m.rs_3m_gold::text                AS rs_3m_gold,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      s.weinstein_gate_pass
    FROM us_atlas.atlas_universe_etfs u
    LEFT JOIN latest l ON l.ticker = u.ticker
    LEFT JOIN us_atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN us_atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = l.d
    WHERE u.is_active = TRUE
    ORDER BY
      CASE s.rs_state
        WHEN 'Leader'        THEN 1
        WHEN 'Strong'        THEN 2
        WHEN 'Consolidating' THEN 3
        WHEN 'Emerging'      THEN 4
        WHEN 'Average'       THEN 5
        WHEN 'Weak'          THEN 6
        WHEN 'Laggard'       THEN 7
        ELSE 8
      END,
      m.rs_pctile_3m_vt DESC NULLS LAST
  `
}
