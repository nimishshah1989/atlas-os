"""v6 — mv_etf_list_v6 materialized view (Page 07 ETFs).

# allow-large: SQL body is a multi-CTE chain joining 6 ETF tables for latest snapshot

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.

MV: atlas.mv_etf_list_v6
Row shape: ONE row per active ETF (~34 rows, LATEST snapshot only).
Page 07 hero stories + AMC tiles + premium/discount scatter + story cards + table
all derive from these rows via frontend filtering/grouping.

Columns served:
  Identity:
    as_of_date, instrument_id, ticker, etf_name, fund_house, asset_class,
    theme, linked_sector, linked_index, isin
  Scorecard (from atlas_etf_scorecard):
    matrix_conviction_score, composite_score, sector_strength_score,
    tracking_quality_score, aum_bracket_score, liquidity_score,
    expense_ratio_score, rank_in_category, category_size, is_atlas_leader,
    eli5, premium_bps, te_60d, adv_20d_inr, etf_category, etf_sub_category
  Returns + RS (from atlas_etf_metrics_daily):
    ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m
    rs_1w_benchmark, rs_1m_benchmark, rs_3m_benchmark
    rs_pctile_1w, rs_pctile_1m, rs_pctile_3m
    realized_vol_63, drawdown_ratio_252, volume_expansion
  State (from atlas_etf_states_daily):
    rs_state, momentum_state, risk_state, volume_state
    weinstein_gate_pass, history_gate_pass, liquidity_gate_pass
    state_since_date
  Decision (from atlas_etf_decisions_daily):
    is_investable, strength_gate, direction_gate, risk_gate, sector_gate,
    market_gate, transition_trigger, breakout_trigger, proximity_pass,
    position_size_pct
  Open signal (from atlas_etf_signal_calls):
    cell_id, signal_action, signal_tenure, signal_predicted_excess,
    signal_confidence
  Derived:
    action               — BUY / AVOID / WATCH from signal_action + composite
    aum_proxy_cr         — adv_20d_inr × 30 (rough monthly turnover proxy in INR cr)
    scatter_zone         — clean_buy / discount_outlier / premium_outlier / low_adv

Design:
  LATEST-ONLY snapshot. ~34 rows materialized; refresh <2s.
  Per-AMC aggregates computed in frontend via GROUP BY fund_house.

Source tables (all latest-date):
  atlas.atlas_universe_etfs        — 34 active ETFs (effective_to IS NULL)
  atlas.atlas_etf_scorecard        — 34 latest scorecard rows
  atlas.atlas_etf_metrics_daily    — daily returns + RS
  atlas.atlas_etf_states_daily     — daily state classification
  atlas.atlas_etf_decisions_daily  — daily gate verdicts + position sizing
  atlas.atlas_etf_signal_calls     — open cell signals

Refresh: pg_cron 'mv_etf_list_v6_nightly' at 21:05 IST (15:35 UTC) daily.
CONCURRENTLY after first build. Unique index on (ticker).

Revision ID: 107
Revises: 106
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None

_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_etf_list_v6 AS
WITH
latest_scorecard AS (
  SELECT MAX(snapshot_date) AS d FROM atlas.atlas_etf_scorecard
),
latest_metrics AS (
  SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
),
latest_states AS (
  SELECT MAX(date) AS d FROM atlas.atlas_etf_states_daily
),
latest_decisions AS (
  SELECT MAX(date) AS d FROM atlas.atlas_etf_decisions_daily
),

active_etfs AS (
  SELECT
    u.ticker, u.isin, u.fund_house, u.etf_name,
    u.theme, u.linked_sector, u.linked_index, u.asset_class,
    u.inception_date
  FROM atlas.atlas_universe_etfs u
  WHERE u.effective_to IS NULL
),

scorecard AS (
  SELECT
    sc.ticker, sc.instrument_id, sc.snapshot_date AS as_of_date,
    sc.etf_category, sc.underlying_sector,
    sc.matrix_conviction_score, sc.sector_strength_score, sc.tracking_quality_score,
    sc.aum_bracket_score, sc.liquidity_score, sc.expense_ratio_score,
    sc.composite_score, sc.rank_in_category, sc.category_size,
    sc.is_atlas_leader, sc.eli5,
    sc.premium_bps, sc.te_60d, sc.adv_20d_inr
  FROM atlas.atlas_etf_scorecard sc, latest_scorecard ls
  WHERE sc.snapshot_date = ls.d
),

metrics AS (
  SELECT
    m.ticker,
    m.ret_1d, m.ret_1w, m.ret_1m, m.ret_3m, m.ret_6m, m.ret_12m,
    m.rs_1w_benchmark, m.rs_1m_benchmark, m.rs_3m_benchmark,
    m.rs_pctile_1w, m.rs_pctile_1m, m.rs_pctile_3m,
    m.realized_vol_63, m.drawdown_ratio_252, m.volume_expansion,
    m.weinstein_gate_pass AS metrics_weinstein_pass,
    m.avg_volume_20
  FROM atlas.atlas_etf_metrics_daily m, latest_metrics lm
  WHERE m.date = lm.d
),

states AS (
  SELECT
    s.ticker,
    s.rs_state, s.momentum_state, s.risk_state, s.volume_state,
    s.history_gate_pass, s.liquidity_gate_pass, s.weinstein_gate_pass,
    s.state_since_date
  FROM atlas.atlas_etf_states_daily s, latest_states ls
  WHERE s.date = ls.d
),

decisions AS (
  SELECT
    d.ticker,
    d.is_investable, d.strength_gate, d.direction_gate, d.risk_gate,
    d.sector_gate, d.market_gate, d.transition_trigger, d.breakout_trigger,
    d.proximity_pass, d.position_size_pct,
    d.market_multiplier, d.risk_multiplier,
    d.exit_market_riskoff, d.exit_sector_avoid, d.exit_rs_deteriorate,
    d.exit_momentum_collapse, d.exit_stop_loss
  FROM atlas.atlas_etf_decisions_daily d, latest_decisions ld
  WHERE d.date = ld.d
),

-- Distinct ticker <-> instrument_id mapping (1 row per ETF)
ticker_map AS (
  SELECT DISTINCT instrument_id, ticker
  FROM atlas.atlas_etf_scorecard
  WHERE instrument_id IS NOT NULL
),
open_signals AS (
  SELECT
    tm.ticker,
    sc.cell_id, sc.action AS signal_action, sc.tenure AS signal_tenure,
    sc.predicted_excess AS signal_predicted_excess,
    sc.confidence_unconditional AS signal_confidence,
    sc.date AS signal_fire_date,
    ROW_NUMBER() OVER (PARTITION BY sc.etf_instrument_id ORDER BY sc.date DESC, sc.computed_at DESC) AS rn
  FROM atlas.atlas_etf_signal_calls sc
  JOIN ticker_map tm ON tm.instrument_id = sc.etf_instrument_id
  WHERE sc.exit_date IS NULL
),
open_signals_latest AS (SELECT * FROM open_signals WHERE rn = 1)

SELECT
  COALESCE(s.as_of_date, (SELECT d FROM latest_metrics)) AS as_of_date,
  e.ticker,
  e.isin,
  s.instrument_id,
  e.etf_name,
  e.fund_house,
  e.asset_class,
  e.theme,
  e.linked_sector,
  e.linked_index,
  e.inception_date,

  -- Scorecard
  s.etf_category,
  s.underlying_sector,
  ROUND(s.matrix_conviction_score::numeric, 4) AS matrix_conviction_score,
  ROUND(s.sector_strength_score::numeric, 4)   AS sector_strength_score,
  ROUND(s.tracking_quality_score::numeric, 4)  AS tracking_quality_score,
  ROUND(s.aum_bracket_score::numeric, 4)       AS aum_bracket_score,
  ROUND(s.liquidity_score::numeric, 4)         AS liquidity_score,
  ROUND(s.expense_ratio_score::numeric, 4)     AS expense_ratio_score,
  ROUND(s.composite_score::numeric, 4)         AS composite_score,
  s.rank_in_category,
  s.category_size,
  s.is_atlas_leader,
  s.eli5,
  ROUND(s.premium_bps::numeric, 2)             AS premium_bps,
  ROUND(s.te_60d::numeric, 4)                  AS te_60d,
  ROUND(s.adv_20d_inr::numeric, 2)             AS adv_20d_inr,

  -- Returns + RS
  ROUND(m.ret_1d::numeric, 4)  AS ret_1d,
  ROUND(m.ret_1w::numeric, 4)  AS ret_1w,
  ROUND(m.ret_1m::numeric, 4)  AS ret_1m,
  ROUND(m.ret_3m::numeric, 4)  AS ret_3m,
  ROUND(m.ret_6m::numeric, 4)  AS ret_6m,
  ROUND(m.ret_12m::numeric, 4) AS ret_12m,
  ROUND(m.rs_1w_benchmark::numeric, 4) AS rs_1w,
  ROUND(m.rs_1m_benchmark::numeric, 4) AS rs_1m,
  ROUND(m.rs_3m_benchmark::numeric, 4) AS rs_3m,
  ROUND(m.rs_pctile_1w::numeric, 4) AS rs_pctile_1w,
  ROUND(m.rs_pctile_1m::numeric, 4) AS rs_pctile_1m,
  ROUND(m.rs_pctile_3m::numeric, 4) AS rs_pctile_3m,
  ROUND(m.realized_vol_63::numeric, 4) AS realized_vol_63,
  ROUND(m.drawdown_ratio_252::numeric, 4) AS drawdown_ratio_252,
  ROUND(m.volume_expansion::numeric, 4) AS volume_expansion,
  m.avg_volume_20,

  -- State
  st.rs_state,
  st.momentum_state,
  st.risk_state,
  st.volume_state,
  st.history_gate_pass,
  st.liquidity_gate_pass,
  st.weinstein_gate_pass,
  st.state_since_date,

  -- Decision
  d.is_investable,
  d.strength_gate,
  d.direction_gate,
  d.risk_gate,
  d.sector_gate,
  d.market_gate,
  d.transition_trigger,
  d.breakout_trigger,
  d.proximity_pass,
  ROUND(d.position_size_pct::numeric, 4) AS position_size_pct,
  ROUND(d.market_multiplier::numeric, 4) AS market_multiplier,
  ROUND(d.risk_multiplier::numeric, 4)   AS risk_multiplier,
  d.exit_market_riskoff,
  d.exit_sector_avoid,
  d.exit_rs_deteriorate,
  d.exit_momentum_collapse,
  d.exit_stop_loss,

  -- Open signal (NULL when no open call)
  os.cell_id,
  os.signal_action,
  os.signal_tenure,
  ROUND(os.signal_predicted_excess::numeric, 4) AS signal_predicted_excess,
  ROUND(os.signal_confidence::numeric, 4)       AS signal_confidence,
  os.signal_fire_date,

  -- Derived action: open signal first, else composite_score thresholds
  CASE
    WHEN os.signal_action = 'POSITIVE' THEN 'BUY'
    WHEN os.signal_action = 'NEGATIVE' THEN 'AVOID'
    WHEN d.is_investable IS TRUE AND s.composite_score >= 0.6 THEN 'BUY'
    WHEN d.is_investable IS FALSE THEN 'AVOID'
    WHEN s.composite_score IS NULL THEN NULL
    ELSE 'WATCH'
  END AS action,

  -- AUM proxy: ADV (INR) × ~20 trading days → INR crores
  CASE
    WHEN s.adv_20d_inr IS NOT NULL
    THEN ROUND((s.adv_20d_inr * 20 / 1e7)::numeric, 2)
    ELSE NULL
  END AS adv_monthly_cr,

  -- Scatter zone: premium_bps × adv liquidity
  -- scatter_zone: liquidity first, then premium overlay.
  -- premium_bps will be NULL until AMFI iNAV ingest backfills (migration 108);
  -- when missing, classify on adv alone so the bubble still renders.
  CASE
    WHEN s.adv_20d_inr IS NULL                       THEN NULL
    WHEN s.adv_20d_inr < 3e7                         THEN 'low_adv'
    WHEN s.premium_bps IS NULL                       THEN 'premium_unknown'
    WHEN s.premium_bps >  25                         THEN 'premium_outlier'
    WHEN s.premium_bps < -25                         THEN 'discount_outlier'
    ELSE 'clean_buy'
  END AS scatter_zone,

  NOW() AS refreshed_at

FROM active_etfs e
LEFT JOIN scorecard s        ON s.ticker = e.ticker
LEFT JOIN metrics m          ON m.ticker = e.ticker
LEFT JOIN states st          ON st.ticker = e.ticker
LEFT JOIN decisions d        ON d.ticker = e.ticker
LEFT JOIN open_signals_latest os ON os.ticker = e.ticker

WITH NO DATA;
"""


_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uix_mv_etf_list_v6_ticker
ON atlas.mv_etf_list_v6 (ticker);
"""

_CRON = """
SELECT cron.schedule(
  'mv_etf_list_v6_nightly',
  '35 15 * * *',
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_etf_list_v6;$$
);
"""


def upgrade() -> None:
    op.execute(_CREATE_MV)
    op.execute(_INDEX)
    op.execute("REFRESH MATERIALIZED VIEW atlas.mv_etf_list_v6;")
    op.execute(_CRON)


def downgrade() -> None:
    op.execute("SELECT cron.unschedule('mv_etf_list_v6_nightly');")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_etf_list_v6;")
