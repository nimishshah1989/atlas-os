"""v6 — mv_stock_list_v6 materialized view (Page 01 Stocks list).

Creates atlas.mv_stock_list_v6 — one row per active M1 instrument with
the 15+ load-bearing columns for the v6 Stocks page list.

Composite + confidence_band are LIFTED from atlas_stock_conviction_daily
(mig 039), not re-computed.  Composite mapping:
  composite_score = (conviction_score - 0.5) * 20  → [-10, +10]

confidence_band mapping (from conviction.confidence_label):
  industry_grade    → H
  baseline          → M
  descriptive_only  → L

cross_cell_depth = count of OPEN signal_calls (exit_date IS NULL) for
the instrument's current cell.

Tape scalars (tape_1m / tape_3m / tape_6m / tape_12m) are conviction
scores aggregated over rolling windows, sourced from conviction history.

Returns (ret_1m / ret_3m / ret_12m), RS (rs_3m_nifty500), vol (vol_60d),
predicted_excess, cell_ic, last_fire_date, is_fresh_today are sourced
from the scorecard and signal-call tables.

Refresh strategy:
  - CONCURRENT via pg_cron after scorecard writer completes.
  - Unique index on instrument_id required for CONCURRENT.

Design doc: docs/superpowers/specs/2026-05-26-v6-stocks-mvs-design.md

Revision ID: 097
Revises: 096
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None

_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_stock_list_v6 AS
WITH

-- Latest conviction row per instrument
latest_conviction AS (
  SELECT DISTINCT ON (instrument_id)
    instrument_id,
    conviction_score,
    confidence_label,
    predicted_excess,
    cell_ic,
    tier,
    date AS conviction_date
  FROM atlas.atlas_stock_conviction_daily
  ORDER BY instrument_id, date DESC
),

-- composite_score: lift from conviction_score via (score - 0.5) * 20
composite AS (
  SELECT
    instrument_id,
    conviction_score,
    ROUND(((conviction_score - 0.5) * 20)::numeric, 4)  AS composite_score,
    CASE confidence_label
      WHEN 'industry_grade'   THEN 'H'
      WHEN 'baseline'         THEN 'M'
      WHEN 'descriptive_only' THEN 'L'
      ELSE NULL
    END                                                   AS confidence_band,
    predicted_excess,
    cell_ic,
    conviction_date,
    tier
  FROM latest_conviction
),

-- cross_cell_depth: open signal calls (exit_date IS NULL) per instrument
cross_cell AS (
  SELECT
    instrument_id,
    COUNT(*) AS cross_cell_depth,
    MAX(entry_date) AS last_fire_date
  FROM atlas.atlas_signal_calls
  WHERE exit_date IS NULL
  GROUP BY instrument_id
),

-- Tape scalars: proportion of rolling-window conviction rows that are
-- above neutral threshold (conviction_score >= 0.5) — 1m/3m/6m/12m
tape_agg AS (
  SELECT
    instrument_id,
    ROUND(AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '21 days'  AND conviction_score >= 0.5 THEN 1.0 ELSE 0.0 END)::numeric, 4)  AS tape_1m,
    ROUND(AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '63 days'  AND conviction_score >= 0.5 THEN 1.0 ELSE 0.0 END)::numeric, 4)  AS tape_3m,
    ROUND(AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '126 days' AND conviction_score >= 0.5 THEN 1.0 ELSE 0.0 END)::numeric, 4)  AS tape_6m,
    ROUND(AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '252 days' AND conviction_score >= 0.5 THEN 1.0 ELSE 0.0 END)::numeric, 4)  AS tape_12m
  FROM atlas.atlas_stock_conviction_daily
  WHERE date >= CURRENT_DATE - INTERVAL '252 days'
  GROUP BY instrument_id
),

-- Returns and RS from index_metrics (scorecard proxy — latest row)
returns_rs AS (
  SELECT DISTINCT ON (instrument_id)
    instrument_id,
    ret_1m,
    ret_3m,
    ret_12m,
    rs_3m_nifty500,
    vol_60d
  FROM atlas.atlas_stock_scorecard_daily
  ORDER BY instrument_id, date DESC
),

-- Action: BUY / HOLD / SELL from latest scorecard row
action_agg AS (
  SELECT DISTINCT ON (instrument_id)
    instrument_id,
    action,
    (date = CURRENT_DATE) AS is_fresh_today
  FROM atlas.atlas_stock_scorecard_daily
  ORDER BY instrument_id, date DESC
),

-- Instrument master (symbol, company_name, sector, cap_tier)
inst AS (
  SELECT
    id AS instrument_id,
    symbol,
    company_name,
    sector,
    cap_tier
  FROM atlas.atlas_instruments
  WHERE is_active IS TRUE
    AND universe_type = 'M1'
)

SELECT
  i.instrument_id,
  i.symbol,
  i.company_name,
  i.sector,
  i.cap_tier,

  -- Action
  COALESCE(a.action, 'HOLD')   AS action,

  -- Composite + band
  c.composite_score,
  c.confidence_band,

  -- Cross-cell depth (open signal calls count)
  COALESCE(x.cross_cell_depth, 0)::integer  AS cross_cell_depth,

  -- Tape scalars
  t.tape_1m,
  t.tape_3m,
  t.tape_6m,
  t.tape_12m,

  -- Returns
  r.ret_1m,
  r.ret_3m,
  r.ret_12m,

  -- RS
  r.rs_3m_nifty500,

  -- Vol
  r.vol_60d,

  -- Forward IC / conviction quality
  c.predicted_excess,
  c.cell_ic,

  -- Last fire date (most recent open signal call entry date)
  x.last_fire_date,

  -- Freshness
  COALESCE(a.is_fresh_today, FALSE)  AS is_fresh_today,

  -- Metadata
  NOW()  AS refreshed_at

FROM inst i
LEFT JOIN composite      c ON c.instrument_id = i.instrument_id
LEFT JOIN cross_cell      x ON x.instrument_id = i.instrument_id
LEFT JOIN tape_agg        t ON t.instrument_id = i.instrument_id
LEFT JOIN returns_rs      r ON r.instrument_id = i.instrument_id
LEFT JOIN action_agg      a ON a.instrument_id = i.instrument_id

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uix_mv_stock_list_v6_instrument_id
  ON atlas.mv_stock_list_v6 (instrument_id);
"""

_REFRESH_MV = "REFRESH MATERIALIZED VIEW atlas.mv_stock_list_v6;"

_DROP_UNIQUE_INDEX = "DROP INDEX IF EXISTS atlas.uix_mv_stock_list_v6_instrument_id;"

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_list_v6 CASCADE;"


def upgrade() -> None:
    """Create mv_stock_list_v6 MV + unique index + initial refresh."""
    op.execute(_CREATE_MV)
    op.execute(_CREATE_UNIQUE_INDEX)
    op.execute(_REFRESH_MV)


def downgrade() -> None:
    """Drop index then MV in dependency-safe order."""
    op.execute(_DROP_UNIQUE_INDEX)
    op.execute(_DROP_MV)
