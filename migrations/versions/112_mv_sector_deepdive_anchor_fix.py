"""v6 — mv_sector_deepdive: fix anchor to skip partial-T-0 rows.

# allow-large: full MV body required for DROP + CREATE

Symptom (2026-05-28 live page audit): /sectors/Energy was showing
"12M abs return —", "Above EMA20 —", and only the 3-month column in the
RS multi-baseline table populated.

Root cause: latest_sector_date CTE took MAX(date) from
atlas_sector_metrics_daily. The 2026-05-27 row had ret_1m/ret_3m/ret_6m
populated but rs_1w/rs_1m/rs_6m/rs_12m/pct_above_ema20/rs_12m NULL —
M3 daily compute filled the bottomup_ret_* columns on T-0 but missed
the RS windows. MV picked this partial row.

Fix: anchor latest_sector_date to MAX(date) WHERE rs_1w IS NOT NULL,
so the MV always reads a fully-populated row (today's anchor = 2026-05-22,
the last fully-populated date). Same fix applied to latest_stock_date.

Cleanup task tracked separately: investigate why m3_daily.py writes
partial rows. For now the MV anchor pattern prevents user-visible NULLs.

Revision ID: 112
Revises: 111
Create Date: 2026-05-28 IST
"""

from __future__ import annotations

from alembic import op

revision = "112"
down_revision = "111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_sector_deepdive;")
    op.execute(_CREATE_MV)
    op.execute(
        "CREATE UNIQUE INDEX uix_mv_sector_deepdive_sector "
        "ON atlas.mv_sector_deepdive (sector_name);"
    )
    op.execute("REFRESH MATERIALIZED VIEW atlas.mv_sector_deepdive;")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_sector_deepdive;")
    # Restoration of the prior (broken-anchor) definition lives in migration 105.


_CREATE_MV = """
CREATE MATERIALIZED VIEW atlas.mv_sector_deepdive AS
WITH latest_sector_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_sector_metrics_daily WHERE rs_1w IS NOT NULL
), latest_stock_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily WHERE rs_3m_nifty500 IS NOT NULL
), latest_conviction_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_conviction_daily
), latest_stock_state_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
), latest_sector_state_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_sector_states_daily
), sector_spine AS (
  SELECT DISTINCT sector AS sector_name FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL
), sector_metrics AS (
  SELECT smd.sector_name,
    smd.bottomup_ret_1m AS ret_1m_raw, smd.bottomup_ret_3m AS ret_3m_raw, smd.bottomup_ret_6m AS ret_6m_raw,
    smd.rs_1w AS rs_1w_raw, smd.rs_1m AS rs_1m_raw,
    smd.bottomup_rs_3m_nifty500 AS rs_3m_raw,
    smd.rs_6m AS rs_6m_raw, smd.rs_12m AS rs_12m_raw,
    smd.pct_above_ema20, smd.pct_above_ema200, smd.pct_52wh AS pct_at_52wh
  FROM atlas.atlas_sector_metrics_daily smd CROSS JOIN latest_sector_date lsd
  WHERE smd.date = lsd.d
), n500_rets AS (
  SELECT ret_1w AS n500_ret_1w, ret_12m AS n500_ret_12m
  FROM atlas.atlas_index_metrics_daily CROSS JOIN latest_sector_date lsd
  WHERE index_code = 'NIFTY 500' AND date = lsd.d LIMIT 1
), sector_states AS (
  SELECT ssd.sector_name, ssd.sector_state
  FROM atlas.atlas_sector_states_daily ssd CROSS JOIN latest_sector_state_date lssd
  WHERE ssd.date = lssd.d
), constituent_counts AS (
  SELECT sector AS sector_name, COUNT(DISTINCT instrument_id) AS constituent_count
  FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL GROUP BY sector
), stock_data AS (
  SELECT u.sector AS sector_name, u.symbol, u.company_name, u.tier, u.instrument_id,
    smd.ret_1w, smd.ret_1m, smd.ret_3m, smd.ret_6m, smd.rs_3m_nifty500,
    smd.realized_vol_63 AS vol_60d,
    ss_1.rs_state,
    CASE WHEN cd.conviction_score IS NOT NULL THEN ROUND((cd.conviction_score - 0.5) * 20, 4) ELSE NULL END AS composite_score,
    CASE cd.confidence_label
      WHEN 'industry_grade' THEN 'H' WHEN 'baseline' THEN 'M' WHEN 'descriptive_only' THEN 'L' ELSE NULL END AS confidence_band,
    CASE
      WHEN cd.conviction_score IS NULL THEN NULL
      WHEN cd.conviction_score >= 0.55 THEN 'POSITIVE'
      WHEN cd.conviction_score <= 0.45 THEN 'NEGATIVE'
      ELSE 'NEUTRAL' END AS action
  FROM atlas.atlas_universe_stocks u
  LEFT JOIN atlas.atlas_stock_metrics_daily smd
    ON smd.instrument_id = u.instrument_id AND smd.date = (SELECT d FROM latest_stock_date)
  LEFT JOIN atlas.atlas_stock_states_daily ss_1
    ON ss_1.instrument_id = u.instrument_id AND ss_1.date = (SELECT d FROM latest_stock_state_date)
  LEFT JOIN atlas.atlas_stock_conviction_daily cd
    ON cd.instrument_id = u.instrument_id AND cd.date = (SELECT d FROM latest_conviction_date)
  WHERE u.effective_to IS NULL
), stock_ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY sector_name ORDER BY composite_score DESC NULLS LAST) AS rn_composite
  FROM stock_data
), strength_dist_agg AS (
  SELECT q.sector_name,
    COUNT(*) FILTER (WHERE q.quintile = 5) AS very_strong,
    COUNT(*) FILTER (WHERE q.quintile = 4) AS strong,
    COUNT(*) FILTER (WHERE q.quintile = 3) AS neutral,
    COUNT(*) FILTER (WHERE q.quintile = 2) AS weak,
    COUNT(*) FILTER (WHERE q.quintile = 1) AS very_weak
  FROM (SELECT sector_name, NTILE(5) OVER (PARTITION BY sector_name ORDER BY ret_3m) AS quintile
        FROM stock_data WHERE ret_3m IS NOT NULL) q
  GROUP BY q.sector_name
), open_signals_raw AS (
  SELECT u.sector AS sector_name, u.symbol, u.company_name,
    sc.action::text, sc.tenure::text, sc.cap_tier_at_trigger::text,
    ROUND(sc.confidence_unconditional::numeric, 4) AS confidence_unconditional,
    sc.date AS signal_date
  FROM atlas.atlas_signal_calls sc
  JOIN atlas.atlas_universe_stocks u ON u.instrument_id = sc.instrument_id AND u.effective_to IS NULL
  WHERE sc.exit_date IS NULL AND sc.action IN ('POSITIVE'::atlas.atlas_cell_action, 'NEGATIVE'::atlas.atlas_cell_action)
), sector_constituents AS (
  SELECT sector_name, COALESCE(jsonb_agg(jsonb_build_object(
    'symbol', symbol, 'company_name', company_name, 'tier', tier,
    'ret_1w', CASE WHEN ret_1w IS NOT NULL THEN ROUND(ret_1w * 100, 2) ELSE NULL END,
    'ret_1m', CASE WHEN ret_1m IS NOT NULL THEN ROUND(ret_1m * 100, 2) ELSE NULL END,
    'ret_3m', CASE WHEN ret_3m IS NOT NULL THEN ROUND(ret_3m * 100, 2) ELSE NULL END,
    'ret_6m', CASE WHEN ret_6m IS NOT NULL THEN ROUND(ret_6m * 100, 2) ELSE NULL END,
    'rs_3m_nifty500_pp', CASE WHEN rs_3m_nifty500 IS NOT NULL THEN ROUND(rs_3m_nifty500 * 100, 2) ELSE NULL END,
    'vol_60d', CASE WHEN vol_60d IS NOT NULL THEN ROUND(vol_60d * 100, 2) ELSE NULL END,
    'rs_state', rs_state, 'composite_score', composite_score,
    'confidence_band', confidence_band, 'action', action
  ) ORDER BY rn_composite) FILTER (WHERE rn_composite <= 30), '[]'::jsonb) AS constituents_top30
  FROM stock_ranked GROUP BY sector_name
), sector_top_picks AS (
  SELECT sector_name, COALESCE(jsonb_agg(jsonb_build_object(
    'symbol', symbol, 'company_name', company_name, 'composite_score', composite_score,
    'confidence_band', confidence_band, 'action', action
  ) ORDER BY rn_composite) FILTER (WHERE rn_composite <= 10 AND composite_score > 0), '[]'::jsonb) AS top_picks_top10
  FROM stock_ranked GROUP BY sector_name
), sector_open_signals AS (
  SELECT sector_name, COALESCE(jsonb_agg(jsonb_build_object(
    'symbol', symbol, 'company_name', company_name, 'action', action, 'tenure', tenure,
    'cap_tier_at_trigger', cap_tier_at_trigger, 'confidence_unconditional', confidence_unconditional,
    'signal_date', signal_date::text
  ) ORDER BY signal_date DESC), '[]'::jsonb) AS open_signals
  FROM open_signals_raw GROUP BY sector_name
)
SELECT ss.sector_name,
  COALESCE(sst.sector_state, 'Unknown') AS verdict,
  COALESCE(cc.constituent_count, 0)::integer AS constituent_count,
  (SELECT d FROM latest_sector_date) AS data_as_of,
  jsonb_build_object(
    'ret_1w', CASE WHEN sm.rs_1w_raw IS NOT NULL AND nr.n500_ret_1w IS NOT NULL
                   THEN ROUND((sm.rs_1w_raw + nr.n500_ret_1w) * 100, 2) ELSE NULL END,
    'ret_1m', CASE WHEN sm.ret_1m_raw IS NOT NULL THEN ROUND(sm.ret_1m_raw * 100, 2) ELSE NULL END,
    'ret_3m', CASE WHEN sm.ret_3m_raw IS NOT NULL THEN ROUND(sm.ret_3m_raw * 100, 2) ELSE NULL END,
    'ret_6m', CASE WHEN sm.ret_6m_raw IS NOT NULL THEN ROUND(sm.ret_6m_raw * 100, 2) ELSE NULL END,
    'ret_12m', CASE WHEN sm.rs_12m_raw IS NOT NULL AND nr.n500_ret_12m IS NOT NULL
                    THEN ROUND((sm.rs_12m_raw + nr.n500_ret_12m) * 100, 2) ELSE NULL END
  ) AS returns,
  jsonb_build_object(
    'rs_1w', CASE WHEN sm.rs_1w_raw IS NOT NULL THEN ROUND(sm.rs_1w_raw * 100, 2) ELSE NULL END,
    'rs_1m', CASE WHEN sm.rs_1m_raw IS NOT NULL THEN ROUND(sm.rs_1m_raw * 100, 2) ELSE NULL END,
    'rs_3m', CASE WHEN sm.rs_3m_raw IS NOT NULL THEN ROUND(sm.rs_3m_raw * 100, 2) ELSE NULL END,
    'rs_6m', CASE WHEN sm.rs_6m_raw IS NOT NULL THEN ROUND(sm.rs_6m_raw * 100, 2) ELSE NULL END,
    'rs_12m', CASE WHEN sm.rs_12m_raw IS NOT NULL THEN ROUND(sm.rs_12m_raw * 100, 2) ELSE NULL END
  ) AS rs_windows,
  sm.pct_above_ema20, sm.pct_above_ema200, sm.pct_at_52wh,
  COALESCE(sc_agg.constituents_top30, '[]'::jsonb) AS constituents_top30,
  COALESCE(os_agg.open_signals, '[]'::jsonb) AS open_signals,
  jsonb_build_object(
    'very_strong', COALESCE(sd.very_strong, 0), 'strong', COALESCE(sd.strong, 0),
    'neutral', COALESCE(sd.neutral, 0), 'weak', COALESCE(sd.weak, 0),
    'very_weak', COALESCE(sd.very_weak, 0)
  ) AS strength_dist,
  COALESCE(tp_agg.top_picks_top10, '[]'::jsonb) AS top_picks_top10,
  NOW() AS refreshed_at
FROM sector_spine ss
LEFT JOIN sector_metrics sm ON sm.sector_name = ss.sector_name
LEFT JOIN n500_rets nr ON true
LEFT JOIN sector_states sst ON sst.sector_name = ss.sector_name
LEFT JOIN constituent_counts cc ON cc.sector_name = ss.sector_name
LEFT JOIN sector_constituents sc_agg ON sc_agg.sector_name = ss.sector_name
LEFT JOIN sector_open_signals os_agg ON os_agg.sector_name = ss.sector_name
LEFT JOIN strength_dist_agg sd ON sd.sector_name = ss.sector_name
LEFT JOIN sector_top_picks tp_agg ON tp_agg.sector_name = ss.sector_name
WITH NO DATA;
"""
