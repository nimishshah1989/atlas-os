"""v6 — mv_etf_deepdive materialized view (Page 07a ETF deep-dive).

# allow-large: SQL body assembles per-ETF deepdive rows with JSONB time series

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.

MV: atlas.mv_etf_deepdive
Row shape: ONE row per active ETF (~34 rows, LATEST snapshot only).
Page 07a renders for a single ETF at a time.

Columns served:
  Identity + scorecard hero — same shape as mv_etf_list_v6 (denormalized)
  price_180d JSONB array     — last 180 trading days OHLCV from atlas_v6_clean_ohlcv
  peer_set JSONB array       — top 5 peers in same etf_category with key deltas

Deferred to follow-up MVs / ingests:
  premium_history_90d        — needs AMFI iNAV ingest (migration 109)
  te_12m series              — needs per-day TE history (not stored today)
  composition / holdings     — ETFs track an underlying index; render via
                                mv_sector_deepdive constituents for sector ETFs

Design:
  LATEST-ONLY snapshot. ~34 rows materialized. Bounded JSONB payloads:
    price_180d  : 180 elements × ~6 fields = ~36KB / row
    peer_set    : 5 elements × 8 fields    = ~2KB / row
  Refresh target <10s.

Source tables:
  atlas.atlas_universe_etfs         — active ETF list
  atlas.atlas_etf_scorecard         — composite + premium + adv (latest snapshot)
  atlas.atlas_etf_metrics_daily     — latest returns + RS
  atlas.atlas_etf_states_daily      — latest state classification
  atlas.atlas_etf_decisions_daily   — latest decision flags
  public.de_etf_ohlcv               — 180-day OHLCV history (ETF prices live here,
                                       not in atlas_v6_clean_ohlcv which holds stocks only)

Refresh: pg_cron 'mv_etf_deepdive_nightly' at 21:10 IST (15:40 UTC) daily.
Unique index on (ticker).

Revision ID: 108
Revises: 107
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "108"
down_revision = "107"
branch_labels = None
depends_on = None

_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_etf_deepdive AS
WITH
latest_scorecard AS (SELECT MAX(snapshot_date) AS d FROM atlas.atlas_etf_scorecard),
latest_metrics  AS (SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily),
latest_states   AS (SELECT MAX(date) AS d FROM atlas.atlas_etf_states_daily),
latest_decisions AS (SELECT MAX(date) AS d FROM atlas.atlas_etf_decisions_daily),
latest_ohlcv    AS (SELECT MAX(date) AS d FROM public.de_etf_ohlcv),

active_etfs AS (
  SELECT u.ticker, u.isin, u.fund_house, u.etf_name,
    u.theme, u.linked_sector, u.linked_index, u.asset_class, u.inception_date
  FROM atlas.atlas_universe_etfs u
  WHERE u.effective_to IS NULL
),

scorecard AS (
  SELECT sc.ticker, sc.instrument_id, sc.snapshot_date AS as_of_date,
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
  SELECT m.ticker,
    m.ret_1d, m.ret_1w, m.ret_1m, m.ret_3m, m.ret_6m, m.ret_12m,
    m.rs_1w_benchmark, m.rs_1m_benchmark, m.rs_3m_benchmark,
    m.realized_vol_63, m.drawdown_ratio_252, m.volume_expansion
  FROM atlas.atlas_etf_metrics_daily m, latest_metrics lm
  WHERE m.date = lm.d
),

states AS (
  SELECT s.ticker, s.rs_state, s.momentum_state, s.risk_state, s.volume_state,
    s.state_since_date
  FROM atlas.atlas_etf_states_daily s, latest_states ls
  WHERE s.date = ls.d
),

decisions AS (
  SELECT d.ticker, d.is_investable, d.position_size_pct
  FROM atlas.atlas_etf_decisions_daily d, latest_decisions ld
  WHERE d.date = ld.d
),

price_window AS (
  SELECT
    u.ticker,
    ohl.date,
    ohl.open, ohl.high, ohl.low, ohl.close, ohl.volume
  FROM public.de_etf_ohlcv ohl
  JOIN active_etfs u  ON u.ticker = ohl.ticker
  CROSS JOIN latest_ohlcv lo
  WHERE ohl.date BETWEEN (lo.d - INTERVAL '270 days')::date AND lo.d
),
price_180d_ranked AS (
  SELECT ticker, date, open, high, low, close, volume,
    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
  FROM price_window
),
price_180d_agg AS (
  SELECT ticker,
    jsonb_agg(
      jsonb_build_object(
        'date',  date::text,
        'open',  ROUND(open::numeric, 2),
        'high',  ROUND(high::numeric, 2),
        'low',   ROUND(low::numeric, 2),
        'close', ROUND(close::numeric, 2),
        'volume', volume
      )
      ORDER BY date ASC
    ) AS price_180d
  FROM price_180d_ranked
  WHERE rn <= 180
  GROUP BY ticker
),

-- Peer set: top 5 by composite_score within the same etf_category, excluding self.
peer_ranked AS (
  SELECT
    s.ticker,
    s.etf_category,
    s.composite_score,
    s.matrix_conviction_score,
    s.adv_20d_inr,
    s.is_atlas_leader,
    s.rank_in_category
  FROM scorecard s
),
peer_set_agg AS (
  SELECT
    self.ticker AS focus_ticker,
    jsonb_agg(
      jsonb_build_object(
        'ticker',                 peer.ticker,
        'composite_score',        ROUND(peer.composite_score::numeric, 4),
        'matrix_conviction_score',ROUND(peer.matrix_conviction_score::numeric, 4),
        'adv_20d_inr',            ROUND(peer.adv_20d_inr::numeric, 2),
        'is_atlas_leader',        peer.is_atlas_leader,
        'rank_in_category',       peer.rank_in_category,
        'delta_composite',        ROUND((peer.composite_score - self.composite_score)::numeric, 4)
      )
      ORDER BY peer.composite_score DESC NULLS LAST
    ) AS peer_set
  FROM peer_ranked self
  JOIN peer_ranked peer
    ON peer.etf_category = self.etf_category
   AND peer.ticker      <> self.ticker
  GROUP BY self.ticker
)

SELECT
  COALESCE(s.as_of_date, (SELECT d FROM latest_metrics)) AS as_of_date,
  e.ticker, e.isin, s.instrument_id, e.etf_name, e.fund_house, e.asset_class,
  e.theme, e.linked_sector, e.linked_index, e.inception_date,
  s.etf_category, s.underlying_sector,
  ROUND(s.matrix_conviction_score::numeric, 4) AS matrix_conviction_score,
  ROUND(s.sector_strength_score::numeric, 4)   AS sector_strength_score,
  ROUND(s.tracking_quality_score::numeric, 4)  AS tracking_quality_score,
  ROUND(s.aum_bracket_score::numeric, 4)       AS aum_bracket_score,
  ROUND(s.liquidity_score::numeric, 4)         AS liquidity_score,
  ROUND(s.expense_ratio_score::numeric, 4)     AS expense_ratio_score,
  ROUND(s.composite_score::numeric, 4)         AS composite_score,
  s.rank_in_category, s.category_size, s.is_atlas_leader, s.eli5,
  ROUND(s.premium_bps::numeric, 2) AS premium_bps,
  ROUND(s.te_60d::numeric, 4)      AS te_60d,
  ROUND(s.adv_20d_inr::numeric, 2) AS adv_20d_inr,

  ROUND(m.ret_1d::numeric, 4)  AS ret_1d,
  ROUND(m.ret_1w::numeric, 4)  AS ret_1w,
  ROUND(m.ret_1m::numeric, 4)  AS ret_1m,
  ROUND(m.ret_3m::numeric, 4)  AS ret_3m,
  ROUND(m.ret_6m::numeric, 4)  AS ret_6m,
  ROUND(m.ret_12m::numeric, 4) AS ret_12m,
  ROUND(m.rs_1w_benchmark::numeric, 4) AS rs_1w,
  ROUND(m.rs_1m_benchmark::numeric, 4) AS rs_1m,
  ROUND(m.rs_3m_benchmark::numeric, 4) AS rs_3m,
  ROUND(m.realized_vol_63::numeric, 4)     AS realized_vol_63,
  ROUND(m.drawdown_ratio_252::numeric, 4)  AS drawdown_ratio_252,
  ROUND(m.volume_expansion::numeric, 4)    AS volume_expansion,

  st.rs_state, st.momentum_state, st.risk_state, st.volume_state, st.state_since_date,
  d.is_investable,
  ROUND(d.position_size_pct::numeric, 4) AS position_size_pct,

  -- Derived action
  CASE
    WHEN d.is_investable IS TRUE AND s.composite_score >= 0.6 THEN 'BUY'
    WHEN d.is_investable IS FALSE THEN 'AVOID'
    WHEN s.composite_score IS NULL THEN NULL
    ELSE 'WATCH'
  END AS action,

  -- JSONB time series
  pa.price_180d,
  ps.peer_set,

  NOW() AS refreshed_at

FROM active_etfs e
LEFT JOIN scorecard s        ON s.ticker = e.ticker
LEFT JOIN metrics m          ON m.ticker = e.ticker
LEFT JOIN states st          ON st.ticker = e.ticker
LEFT JOIN decisions d        ON d.ticker = e.ticker
LEFT JOIN price_180d_agg pa  ON pa.ticker = e.ticker
LEFT JOIN peer_set_agg ps    ON ps.focus_ticker = e.ticker

WITH NO DATA;
"""

_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uix_mv_etf_deepdive_ticker
ON atlas.mv_etf_deepdive (ticker);
"""

_CRON = """
SELECT cron.schedule(
  'mv_etf_deepdive_nightly',
  '40 15 * * *',
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_etf_deepdive;$$
);
"""


def upgrade() -> None:
    op.execute(_CREATE_MV)
    op.execute(_INDEX)
    op.execute("REFRESH MATERIALIZED VIEW atlas.mv_etf_deepdive;")
    op.execute(_CRON)


def downgrade() -> None:
    op.execute("SELECT cron.unschedule('mv_etf_deepdive_nightly');")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_etf_deepdive;")
