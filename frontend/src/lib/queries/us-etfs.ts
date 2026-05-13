import 'server-only'
import sql from '@/lib/db'

export type USETFRow = {
  ticker: string
  etf_name: string | null
  etf_category: string | null
  linked_sector: string | null
  is_benchmark: boolean
  data_as_of: string | null
  // Returns
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  ret_12m_1m: string | null
  // Risk
  realized_vol_63: string | null
  vol_ratio_63: string | null
  max_drawdown_252: string | null
  extension_pct: string | null
  atr_21: string | null
  // Volume
  avg_volume_20: string | null
  volume_expansion: string | null
  effort_ratio_63: string | null
  // EMA ratios
  ema_10_ratio: string | null
  ema_20_ratio: string | null
  above_30w_ma: boolean | null
  // RS vs VT — 5 timeframes
  rs_1w_vt: string | null
  rs_1m_vt: string | null
  rs_3m_vt: string | null
  rs_6m_vt: string | null
  rs_12m_vt: string | null
  rs_pctile_1w_vt: string | null
  rs_pctile_1m_vt: string | null
  rs_pctile_3m_vt: string | null
  rs_pctile_6m_vt: string | null
  rs_pctile_12m_vt: string | null
  // RS vs ACWI
  rs_1w_acwi: string | null
  rs_1m_acwi: string | null
  rs_3m_acwi: string | null
  rs_6m_acwi: string | null
  rs_12m_acwi: string | null
  rs_pctile_1w_acwi: string | null
  rs_pctile_1m_acwi: string | null
  rs_pctile_3m_acwi: string | null
  rs_pctile_6m_acwi: string | null
  rs_pctile_12m_acwi: string | null
  // RS vs EEM (EM benchmark)
  rs_1w_eem: string | null
  rs_1m_eem: string | null
  rs_3m_eem: string | null
  rs_6m_eem: string | null
  rs_12m_eem: string | null
  rs_pctile_1w_eem: string | null
  rs_pctile_1m_eem: string | null
  rs_pctile_3m_eem: string | null
  rs_pctile_6m_eem: string | null
  rs_pctile_12m_eem: string | null
  // RS vs GOLD
  rs_1w_gold: string | null
  rs_1m_gold: string | null
  rs_3m_gold: string | null
  rs_6m_gold: string | null
  rs_12m_gold: string | null
  rs_pctile_1w_gold: string | null
  rs_pctile_1m_gold: string | null
  rs_pctile_3m_gold: string | null
  rs_pctile_6m_gold: string | null
  rs_pctile_12m_gold: string | null
  // Consensus
  rs_consensus_bullish: number | null
  rs_consensus_bearish: number | null
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
      i.name                            AS etf_name,
      u.etf_category,
      u.linked_sector,
      u.is_benchmark,
      l.d::text                         AS data_as_of,
      m.ret_1d::text                    AS ret_1d,
      m.ret_1w::text                    AS ret_1w,
      m.ret_1m::text                    AS ret_1m,
      m.ret_3m::text                    AS ret_3m,
      m.ret_6m::text                    AS ret_6m,
      m.ret_12m::text                   AS ret_12m,
      m.ret_12m_1m::text                AS ret_12m_1m,
      m.realized_vol_63::text           AS realized_vol_63,
      m.vol_ratio_63::text              AS vol_ratio_63,
      m.max_drawdown_252::text          AS max_drawdown_252,
      m.extension_pct::text             AS extension_pct,
      m.atr_21::text                    AS atr_21,
      m.avg_volume_20::text             AS avg_volume_20,
      m.volume_expansion::text          AS volume_expansion,
      m.effort_ratio_63::text           AS effort_ratio_63,
      m.ema_10_ratio::text              AS ema_10_ratio,
      m.ema_20_ratio::text              AS ema_20_ratio,
      m.above_30w_ma,
      m.rs_1w_vt::text                  AS rs_1w_vt,
      m.rs_1m_vt::text                  AS rs_1m_vt,
      m.rs_3m_vt::text                  AS rs_3m_vt,
      m.rs_6m_vt::text                  AS rs_6m_vt,
      m.rs_12m_vt::text                 AS rs_12m_vt,
      m.rs_pctile_1w_vt::text           AS rs_pctile_1w_vt,
      m.rs_pctile_1m_vt::text           AS rs_pctile_1m_vt,
      m.rs_pctile_3m_vt::text           AS rs_pctile_3m_vt,
      m.rs_pctile_6m_vt::text           AS rs_pctile_6m_vt,
      m.rs_pctile_12m_vt::text          AS rs_pctile_12m_vt,
      m.rs_1w_acwi::text                AS rs_1w_acwi,
      m.rs_1m_acwi::text                AS rs_1m_acwi,
      m.rs_3m_acwi::text                AS rs_3m_acwi,
      m.rs_6m_acwi::text                AS rs_6m_acwi,
      m.rs_12m_acwi::text               AS rs_12m_acwi,
      m.rs_pctile_1w_acwi::text         AS rs_pctile_1w_acwi,
      m.rs_pctile_1m_acwi::text         AS rs_pctile_1m_acwi,
      m.rs_pctile_3m_acwi::text         AS rs_pctile_3m_acwi,
      m.rs_pctile_6m_acwi::text         AS rs_pctile_6m_acwi,
      m.rs_pctile_12m_acwi::text        AS rs_pctile_12m_acwi,
      m.rs_1w_eem::text                 AS rs_1w_eem,
      m.rs_1m_eem::text                 AS rs_1m_eem,
      m.rs_3m_eem::text                 AS rs_3m_eem,
      m.rs_6m_eem::text                 AS rs_6m_eem,
      m.rs_12m_eem::text                AS rs_12m_eem,
      m.rs_pctile_1w_eem::text          AS rs_pctile_1w_eem,
      m.rs_pctile_1m_eem::text          AS rs_pctile_1m_eem,
      m.rs_pctile_3m_eem::text          AS rs_pctile_3m_eem,
      m.rs_pctile_6m_eem::text          AS rs_pctile_6m_eem,
      m.rs_pctile_12m_eem::text         AS rs_pctile_12m_eem,
      m.rs_1w_gold::text                AS rs_1w_gold,
      m.rs_1m_gold::text                AS rs_1m_gold,
      m.rs_3m_gold::text                AS rs_3m_gold,
      m.rs_6m_gold::text                AS rs_6m_gold,
      m.rs_12m_gold::text               AS rs_12m_gold,
      m.rs_pctile_1w_gold::text         AS rs_pctile_1w_gold,
      m.rs_pctile_1m_gold::text         AS rs_pctile_1m_gold,
      m.rs_pctile_3m_gold::text         AS rs_pctile_3m_gold,
      m.rs_pctile_6m_gold::text         AS rs_pctile_6m_gold,
      m.rs_pctile_12m_gold::text        AS rs_pctile_12m_gold,
      m.rs_consensus_bullish,
      m.rs_consensus_bearish,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      s.weinstein_gate_pass
    FROM us_atlas.atlas_universe_etfs u
    LEFT JOIN us_atlas.instruments i ON i.ticker = u.ticker
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
