"""Continuous dwell-days recompute.

The monthly-chunk backfill computed dwell per-chunk so it never crossed month
boundaries; this walks each instrument's full history once and writes true
run-length into atlas.atlas_stock_state_daily.

Public API:
  recompute_dwell_days(panel)          -> DataFrame  (pure, testable, no DB)
  recompute_and_persist(engine, cv)    -> int (rows updated)

Schema confirmed from migration 072:
  Table:   atlas.atlas_stock_state_daily
  PK:      (instrument_id uuid, date date)
  State:   state VARCHAR(24)  — NOT engine_state
  Dwell:   dwell_days INTEGER
  Version: classifier_version VARCHAR(16); default "v2.0-validated"

Algorithm (vectorized — no iterrows, no apply on large data):
  1. Sort by [instrument_id, date]
  2. Detect state-change or instrument-change boundary
  3. Assign run_id via cumsum within each instrument
  4. cumcount within [instrument_id, run_id] = 0-indexed dwell
"""

from __future__ import annotations

from typing import cast

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def recompute_dwell_days(panel: pd.DataFrame) -> pd.DataFrame:
    """Recompute dwell_days for every row in panel using vectorized run-length encoding.

    Args:
        panel: DataFrame with columns [instrument_id, date, state].
               Values in instrument_id may be strings or UUIDs.

    Returns:
        The same rows sorted by [instrument_id, date] with a 'dwell_days'
        column added (or overwritten). 0-indexed: first day in a run = 0.

    Edge cases:
        - Empty panel: returns empty DataFrame with dwell_days column.
        - Single-row instrument: dwell_days = 0 always.
        - Instrument boundary: always starts a new run (dwell resets to 0).
        - State change: run resets to 0 on the next row.
    """
    if panel.empty:
        result = panel.copy()
        result["dwell_days"] = pd.Series(dtype="int64")
        return result

    df = panel.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # Detect new run: state changed from previous row within the same instrument.
    # groupby().shift() produces NaN at the first row of each instrument group,
    # which makes (state != NaN) evaluate to True — correct, because the first
    # row of each instrument always starts a new run.
    state_change = df["state"] != df.groupby("instrument_id")["state"].shift()

    # Cumulative sum of state-change booleans within each instrument gives
    # a monotonically-increasing run identifier that increments on each new run.
    run_id = state_change.groupby(df["instrument_id"]).cumsum()

    # cumcount within each (instrument, run) gives 0-indexed position = dwell_days.
    df["dwell_days"] = df.groupby(["instrument_id", run_id]).cumcount()

    return df


def recompute_and_persist(
    engine: Engine,
    classifier_version: str = "v2.0-validated",
) -> int:
    """Load full state history for classifier_version, recompute dwell_days, persist.

    Steps:
      1. SELECT instrument_id, date, state from atlas.atlas_stock_state_daily
         WHERE classifier_version = :cv  (parameterized — no f-string injection)
      2. recompute_dwell_days(panel) — vectorized pandas
      3. Batch UPDATE dwell_days back into the table

    Args:
        engine:              SQLAlchemy Engine connected to the atlas DB.
        classifier_version:  Filters and tags rows. Default "v2.0-validated".

    Returns:
        Number of rows updated (0 if table empty for that version).

    Raises:
        RuntimeError: if row count before and after transform does not match
                      (data integrity guard).
    """
    with engine.connect() as conn:
        panel = pd.read_sql(
            text("""
                SELECT instrument_id::text AS instrument_id, date, state
                FROM atlas.atlas_stock_state_daily
                WHERE classifier_version = :cv
                ORDER BY instrument_id, date
            """),
            conn,
            params={"cv": classifier_version},
        )

    if panel.empty:
        return 0

    rows_before = len(panel)

    out = recompute_dwell_days(panel)

    rows_after = len(out)
    if rows_before != rows_after:
        raise RuntimeError(
            f"Row count mismatch after recompute_dwell_days: "
            f"before={rows_before} after={rows_after}"
        )

    subset = cast(pd.DataFrame, out[["instrument_id", "date", "dwell_days"]])
    records = subset.to_dict(orient="records")

    # Batch UPDATE. Using CAST() not ::uuid syntax to avoid SQLAlchemy
    # param-cast collision (wiki bug-pattern: SQLAlchemy Param-Cast Collision).
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE atlas.atlas_stock_state_daily
                SET dwell_days = :dwell_days
                WHERE instrument_id = CAST(:instrument_id AS uuid)
                  AND date = :date
                  AND classifier_version = :cv
            """),
            [{**r, "cv": classifier_version} for r in records],
        )

    return len(records)
