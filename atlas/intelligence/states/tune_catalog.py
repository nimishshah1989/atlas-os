"""Threshold tuning catalog and factor-panel builders for the state engine.

Defines the Phase 2 MVP catalog of tunable thresholds and the SQL-based
factor builders that produce the (date, instrument_id) → factor panels
that the IC optimizer consumes.

Public API:
  TUNE_CATALOG         — list[dict], one entry per tunable threshold
  build_factor_panel   — loads and returns a factor panel from the live DB

Extending: add a new dict row to TUNE_CATALOG and a new branch in
build_factor_panel.  The CLI in atlas.trading.cli_states loops over the
catalog and delegates all factor construction here.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
# breakout_ratio is intentionally NotImplementedError for this task — it
# requires a raw OHLCV pull (close / max_close_60d_excl_today).  Skipping
# it is correct per the Phase 2 MVP scope.

TUNE_CATALOG: list[dict] = [
    {
        "threshold_name": "theta_rs",
        "state": "stage_2a",
        "candidates": [50.0, 60.0, 70.0, 75.0, 80.0, 85.0, 90.0],
        "horizon_days": 63,
        "factor_builder": "rs_rank_12m",
    },
    {
        "threshold_name": "theta_vol_mult",
        "state": "stage_2a",
        "candidates": [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0],
        "horizon_days": 21,
        "factor_builder": "volume_ratio_50d",
    },
    {
        "threshold_name": "theta_base_breakout",
        "state": "stage_2a",
        "candidates": [0.98, 1.00, 1.01, 1.02, 1.03, 1.05],
        "horizon_days": 21,
        "factor_builder": "breakout_ratio",
    },
    {
        "threshold_name": "theta_distribution",
        "state": "stage_3",
        "candidates": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0],
        "horizon_days": 21,
        "factor_builder": "distribution_days_25d",
    },
]


def build_factor_panel(
    eng,
    builder_id: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Build a MultiIndex (date, instrument_id) factor panel for one threshold.

    Args:
        eng:        SQLAlchemy Engine (synchronous, already stripped of dialect prefix).
        builder_id: Matches the 'factor_builder' key in TUNE_CATALOG.
        start:      Inclusive start date for the factor window.
        end:        Inclusive end date.

    Returns:
        DataFrame with index names ['date', 'instrument_id'] and one column
        'factor' = the continuous metric being thresholded.
        Returns an empty DataFrame with correct MultiIndex names when no rows
        are found (caller logs and skips).

    Raises:
        NotImplementedError: for builder_id='breakout_ratio' (Phase 2 deferred).
        ValueError:          for unrecognised builder_id values.
    """
    if builder_id == "rs_rank_12m":
        with eng.connect() as c:
            df = pd.read_sql(
                text("""
                    SELECT date, instrument_id::text AS instrument_id,
                           rs_rank_12m AS factor
                    FROM atlas.atlas_stock_state_daily
                    WHERE date BETWEEN :s AND :e
                      AND rs_rank_12m IS NOT NULL
                """),
                c,
                params={"s": start, "e": end},
            )
        # theta_rs operates on 0-100 scale; rs_rank_12m is stored 0-1.
        df["factor"] = df["factor"].astype(float) * 100.0

    elif builder_id == "volume_ratio_50d":
        with eng.connect() as c:
            df = pd.read_sql(
                text("""
                    SELECT date, instrument_id::text AS instrument_id,
                           volume_ratio_50d AS factor
                    FROM atlas.atlas_stock_state_daily
                    WHERE date BETWEEN :s AND :e
                      AND volume_ratio_50d IS NOT NULL
                """),
                c,
                params={"s": start, "e": end},
            )
        df["factor"] = df["factor"].astype(float)

    elif builder_id == "breakout_ratio":
        raise NotImplementedError(
            "breakout_ratio requires raw OHLCV (close / max_close_60d_excl_today); "
            "implement in a later Phase 2 iteration"
        )

    elif builder_id == "distribution_days_25d":
        with eng.connect() as c:
            df = pd.read_sql(
                text("""
                    SELECT date, instrument_id::text AS instrument_id,
                           distribution_days::numeric AS factor
                    FROM atlas.atlas_stock_state_daily
                    WHERE date BETWEEN :s AND :e
                      AND distribution_days IS NOT NULL
                """),
                c,
                params={"s": start, "e": end},
            )
        df["factor"] = df["factor"].astype(float)

    else:
        raise ValueError(f"unknown factor builder: {builder_id!r}")

    if df.empty:
        empty: pd.DataFrame = pd.DataFrame(columns=["factor"])
        empty.index = pd.MultiIndex.from_tuples([], names=["date", "instrument_id"])
        return empty

    before = len(df)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index(["date", "instrument_id"])
    log.info(
        "factor_panel_built",
        builder=builder_id,
        rows_before=before,
        rows_after=len(df),
    )
    return df[["factor"]]
