"""v4 — mv_sector_deepdive: source the headline from the fresh canonical mv_sector_cards.

# allow-large: full MV body required for DROP + CREATE

Symptom (FM board QA 2026-06-26): /sectors/<x> detail page (a) broken/not
populating and (b) showing wrong returns — Defence 1Y = 113.19% while the sector
LIST (mv_sector_cards) correctly shows 3.3%.

Two root causes:
  1. The old MV (mig 112) anchored every headline metric to
     atlas_sector_metrics_daily WHERE rs_1w IS NOT NULL. Recent m3 runs wrote only
     bottomup_ret_* + bottomup_rs_3m and left rs_1w/rs_12m/pct_above_ema20 NULL, so
     the anchor was stuck at 2026-05-29 — a month stale — and the 1Y return was a
     reconstruction (rs_12m + nifty500_ret) that drifted to 113%.
  2. The v4 frontend renamed the breadth field ema20 -> ema21 (canonical EMA21
     breadth, mig A1). The MV still output pct_above_ema20, so getSectorDeepdive's
     `SELECT pct_above_ema21` errored ("column does not exist") -> page 500.

Fix: rebuild the headline (returns / RS / breadth / verdict / data_as_of) from
atlas.mv_sector_cards — the SAME fresh, corp-action-adjusted, bottom-up source the
sector LIST already uses — so detail == list. Returns are bottomup_ret_* (×100 into
the returns JSONB, matching the frontend's already-a-percent fmtPct). Output column
renamed to pct_above_ema21. Constituents / strength_dist / top_picks are re-anchored
to MAX(date) of atlas_stock_metrics_daily (fresh ret_*, 06-25) instead of the stale
rs_3m_nifty500 anchor; conviction/states join at their own latest date.

RULE #0: every value traces to a real source (mv_sector_cards bottom-up returns,
real per-stock ret_3m, real conviction scores). Nothing imputed.

Refresh order dependency: atlas.mv_sector_cards must be refreshed BEFORE this MV.

Revision ID: 126
Revises: 125
Create Date: 2026-06-26 IST
"""

from __future__ import annotations

from alembic import op

revision = "126"
down_revision = "125"
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
    # Prior (stale-anchor) definition lives in migration 112.


_CREATE_MV = """
CREATE MATERIALIZED VIEW atlas.mv_sector_deepdive AS
WITH cards AS (
  -- Canonical FRESH sector headline (returns/RS/breadth/verdict), latest row per
  -- sector. Same source as the sector LIST page, so the detail page is consistent
  -- and the returns are the corp-action-adjusted bottom-up series.
  SELECT c.* FROM atlas.mv_sector_cards c
  WHERE c.as_of_date = (SELECT MAX(as_of_date) FROM atlas.mv_sector_cards)
), latest_stock_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
), latest_conviction_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_conviction_daily
), latest_stock_state_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
), sector_spine AS (
  SELECT DISTINCT sector AS sector_name FROM atlas.atlas_universe_stocks WHERE effective_to IS NULL
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
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY sector_name ORDER BY composite_score DESC NULLS LAST, ret_3m DESC NULLS LAST
  ) AS rn_composite
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
  COALESCE(cd2.verdict, 'Unknown') AS verdict,
  COALESCE(cd2.constituent_count, cc.constituent_count, 0)::integer AS constituent_count,
  (SELECT MAX(as_of_date) FROM atlas.mv_sector_cards) AS data_as_of,
  jsonb_build_object(
    'ret_1w', CASE WHEN cd2.ret_1w IS NOT NULL THEN ROUND(cd2.ret_1w * 100, 2) ELSE NULL END,
    'ret_1m', CASE WHEN cd2.ret_1m IS NOT NULL THEN ROUND(cd2.ret_1m * 100, 2) ELSE NULL END,
    'ret_3m', CASE WHEN cd2.ret_3m IS NOT NULL THEN ROUND(cd2.ret_3m * 100, 2) ELSE NULL END,
    'ret_6m', CASE WHEN cd2.ret_6m IS NOT NULL THEN ROUND(cd2.ret_6m * 100, 2) ELSE NULL END,
    'ret_12m', CASE WHEN cd2.ret_12m IS NOT NULL THEN ROUND(cd2.ret_12m * 100, 2) ELSE NULL END
  ) AS returns,
  jsonb_build_object(
    'rs_1w', NULL,
    'rs_1m', CASE WHEN cd2.rs_1m IS NOT NULL THEN ROUND(cd2.rs_1m * 100, 2) ELSE NULL END,
    'rs_3m', CASE WHEN cd2.rs_3m IS NOT NULL THEN ROUND(cd2.rs_3m * 100, 2) ELSE NULL END,
    'rs_6m', CASE WHEN cd2.rs_6m IS NOT NULL THEN ROUND(cd2.rs_6m * 100, 2) ELSE NULL END,
    'rs_12m', NULL
  ) AS rs_windows,
  cd2.pct_above_ema21, cd2.pct_above_ema200, cd2.pct_at_52wh,
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
LEFT JOIN cards cd2 ON cd2.sector_name = ss.sector_name
LEFT JOIN constituent_counts cc ON cc.sector_name = ss.sector_name
LEFT JOIN sector_constituents sc_agg ON sc_agg.sector_name = ss.sector_name
LEFT JOIN sector_open_signals os_agg ON os_agg.sector_name = ss.sector_name
LEFT JOIN strength_dist_agg sd ON sd.sector_name = ss.sector_name
LEFT JOIN sector_top_picks tp_agg ON tp_agg.sector_name = ss.sector_name
WITH NO DATA;
"""
