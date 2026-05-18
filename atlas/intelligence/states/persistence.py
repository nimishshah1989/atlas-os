"""Persist state-classifier output panels into atlas.atlas_stock_state_daily.

Single public function: persist_state_panel(engine, panel) -> int.

Idempotent: re-running with the same (instrument_id, date) UPSERTS via
ON CONFLICT — overwriting the row with the latest classifier output. This
matches the design intent that the classifier output is a derived view; the
'truth' is whatever the latest run computed.

The table schema (migration 072) requires:
  PK (instrument_id, date)
  CHECK state IN (uninvestable, stage_1, stage_2a, stage_2b, stage_2c, stage_3, stage_4)
  CHECK urgency_score IN (urgent, normal, late, n/a)
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

_UPSERT_SQL = """
INSERT INTO atlas.atlas_stock_state_daily
    (instrument_id, date, state, prior_state, state_since_date,
     dwell_days, dwell_percentile, urgency_score, within_state_rank,
     rs_rank_12m, close_vs_sma_50, close_vs_sma_150, close_vs_sma_200,
     sma_200_slope, volume_ratio_50d, distribution_days, classifier_version)
VALUES
    (:instrument_id, :date, :state, :prior_state, :state_since_date,
     :dwell_days, :dwell_percentile, :urgency_score, :within_state_rank,
     :rs_rank_12m, :close_vs_sma_50, :close_vs_sma_150, :close_vs_sma_200,
     :sma_200_slope, :volume_ratio_50d, :distribution_days, :classifier_version)
ON CONFLICT (instrument_id, date) DO UPDATE SET
    state = EXCLUDED.state,
    prior_state = EXCLUDED.prior_state,
    state_since_date = EXCLUDED.state_since_date,
    dwell_days = EXCLUDED.dwell_days,
    dwell_percentile = EXCLUDED.dwell_percentile,
    urgency_score = EXCLUDED.urgency_score,
    within_state_rank = EXCLUDED.within_state_rank,
    rs_rank_12m = EXCLUDED.rs_rank_12m,
    close_vs_sma_50 = EXCLUDED.close_vs_sma_50,
    close_vs_sma_150 = EXCLUDED.close_vs_sma_150,
    close_vs_sma_200 = EXCLUDED.close_vs_sma_200,
    sma_200_slope = EXCLUDED.sma_200_slope,
    volume_ratio_50d = EXCLUDED.volume_ratio_50d,
    distribution_days = EXCLUDED.distribution_days,
    classifier_version = EXCLUDED.classifier_version
"""


_REQUIRED_COLS: tuple[str, ...] = (
    "instrument_id",
    "date",
    "state",
    "prior_state",
    "state_since_date",
    "dwell_days",
    "urgency_score",
    "classifier_version",
)
_OPTIONAL_COLS: tuple[str, ...] = (
    "dwell_percentile",
    "within_state_rank",
    "rs_rank_12m",
    "close_vs_sma_50",
    "close_vs_sma_150",
    "close_vs_sma_200",
    "sma_200_slope",
    "volume_ratio_50d",
    "distribution_days",
)


def _row_to_params(row: pd.Series) -> dict:
    """Convert a panel row to SQL parameters, mapping missing optional fields to None.

    Converts numpy scalars to Python primitives so all DB drivers accept them.
    NaN optional values map to None (SQL NULL).
    """
    params: dict = {}
    for col in _REQUIRED_COLS:
        v = row[col]
        params[col] = v.item() if hasattr(v, "item") else v
    for col in _OPTIONAL_COLS:
        if col in row.index:
            v = row[col]
            if pd.isna(v):
                params[col] = None
            else:
                params[col] = v.item() if hasattr(v, "item") else v
        else:
            params[col] = None
    return params


def _dedup_params(params: list[dict]) -> list[dict]:
    """Deduplicate by natural key (instrument_id, date); last occurrence wins.

    PostgreSQL ON CONFLICT cannot resolve duplicates within the same batch
    (CardinalityViolationError). This guard is cheap and makes the function
    safe even for multi-date panels with repeated natural keys.
    """
    seen: dict[tuple, int] = {}
    for idx, p in enumerate(params):
        key = (str(p["instrument_id"]), p["date"])
        seen[key] = idx
    return [params[i] for i in sorted(seen.values())]


def persist_state_panel(engine: Engine, panel: pd.DataFrame) -> int:
    """Upsert panel rows into atlas_stock_state_daily.

    Idempotent — safe to re-run. Re-inserting the same (instrument_id, date)
    overwrites all non-key columns with the latest classifier output.

    Args:
        engine: SQLAlchemy Engine connected to the atlas DB.
        panel: DataFrame produced by classify_state_panel. Required columns:
            instrument_id, date, state, prior_state, state_since_date,
            dwell_days, urgency_score, classifier_version.
            Optional columns (None if absent or NaN): dwell_percentile,
            within_state_rank, rs_rank_12m, close_vs_sma_{50,150,200},
            sma_200_slope, volume_ratio_50d, distribution_days.

    Returns:
        Number of rows written (after deduplication).
    """
    # Guard: early-exit BEFORE any DB access so callers may safely pass an
    # empty panel without needing a live engine (test 4 depends on this).
    if panel.empty:
        return 0

    params = [_row_to_params(row) for _, row in panel.iterrows()]
    params = _dedup_params(params)

    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), params)

    return len(params)
