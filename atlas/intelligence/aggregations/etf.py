"""Bottom-up ETF state aggregator.

No raw per-constituent ETF holdings table (etf_ticker, as_of_date,
instrument_id, weight_pct) exists in the atlas schema as of 2026-05-19.
ETF state is computed at the ticker level and stored daily in
``atlas_etf_states_daily`` (rs_state + momentum_state).

This module reads atlas_etf_states_daily and maps the existing ETF-level
states into the Weinstein-family dominant_state + distribution columns
expected by atlas_etf_state_v2.

Mapping rules (rs_state + momentum_state -> Weinstein):
  Leader + any              -> stage_2a
  Strong + Accelerating/Improving  -> stage_2a
  Strong + Flat             -> stage_2b
  Average + Improving       -> stage_2c
  Strong/Average + Deteriorating   -> stage_3
  Average/Weak/Laggard + Collapsing -> stage_4
  Weak/Laggard + Deteriorating/Flat -> stage_4
  ILLIQUID / INSUFFICIENT_HISTORY  -> uninvestable (excluded from load)

Public API is unchanged -- callers use:
  load_etf_holdings_panel(engine, as_of_date) -> pd.DataFrame
  aggregate_etf_states(panel) -> pd.DataFrame
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)

# States in atlas_etf_states_daily that indicate no investable data.
_SKIP_RS_STATES = frozenset({"ILLIQUID", "INSUFFICIENT_HISTORY"})

# Approximate rs_rank_12m implied by each rs_state.
_RS_STATE_TO_RANK: dict[str, float] = {
    "Leader": 0.95,
    "Strong": 0.80,
    "Average": 0.50,
    "Weak": 0.20,
    "Laggard": 0.05,
}


def _map_etf_to_weinstein(rs_state: str, momentum_state: str) -> str:
    """Map (rs_state, momentum_state) to a Weinstein stage string.

    Returns one of: stage_2a, stage_2b, stage_2c, stage_3, stage_4,
    stage_1, uninvestable.
    """
    if rs_state in _SKIP_RS_STATES:
        return "uninvestable"
    if rs_state == "Leader" and momentum_state in ("Accelerating", "Improving", "Flat"):
        return "stage_2a"
    if rs_state == "Strong" and momentum_state in ("Accelerating", "Improving"):
        return "stage_2a"
    if rs_state == "Strong" and momentum_state == "Flat":
        return "stage_2b"
    if rs_state == "Average" and momentum_state == "Improving":
        return "stage_2c"
    if rs_state in ("Strong", "Average") and momentum_state == "Deteriorating":
        return "stage_3"
    if rs_state == "Average" and momentum_state in ("Flat", "Accelerating"):
        return "stage_1"
    if rs_state in ("Average", "Weak", "Laggard") and momentum_state == "Collapsing":
        return "stage_4"
    if rs_state in ("Weak", "Laggard") and momentum_state in ("Deteriorating", "Flat"):
        return "stage_4"
    # Catch-all: unclassified -> stage_1 (base / unclear)
    return "stage_1"


_HOLDINGS_SQL = text("""
    SELECT
        e.ticker             AS etf_ticker,
        e.date               AS date,
        e.rs_state           AS rs_state,
        e.momentum_state     AS momentum_state
    FROM atlas.atlas_etf_states_daily e
    WHERE e.rs_state NOT IN ('ILLIQUID', 'INSUFFICIENT_HISTORY')
      AND (:as_of_date IS NULL OR e.date = CAST(:as_of_date AS date))
""")


def load_etf_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load an ETF-day panel from atlas_etf_states_daily.

    Returns one row per (etf_ticker, date) with columns:
    etf_ticker, date, rs_state, momentum_state.

    Rows with ILLIQUID or INSUFFICIENT_HISTORY rs_state are excluded.

    Args:
        engine: SQLAlchemy engine connected to the atlas DB.
        as_of_date: ISO date string to filter a single day. None = all days.

    Returns:
        DataFrame with one row per (etf_ticker, date).
    """
    with engine.connect() as c:
        return pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})


def aggregate_etf_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ETF panel into atlas_etf_state_v2 shape rows.

    Expects panel to have: etf_ticker, date, rs_state, momentum_state.
    Each ETF-day row maps to one Weinstein state via _map_etf_to_weinstein.
    Because each ETF is treated as a single unit, dominant_state is the
    mapped state and dominant_share is 1.0.

    Returns:
        DataFrame with columns matching atlas_etf_state_v2 schema:
        etf_ticker, date, dominant_state, dominant_share, n_holdings,
        mean_rs_rank_12m, pct_stage_2, pct_stage_3, pct_stage_4.
    """
    if panel.empty:
        return pd.DataFrame(
            columns=[
                "etf_ticker",
                "date",
                "dominant_state",
                "dominant_share",
                "n_holdings",
                "mean_rs_rank_12m",
                "pct_stage_2",
                "pct_stage_3",
                "pct_stage_4",
            ]
        )

    panel = panel.copy()
    # Map each row to a Weinstein state. ETF panel is O(100-200 rows/day).
    panel["state"] = [
        _map_etf_to_weinstein(rs, mom)
        for rs, mom in zip(panel["rs_state"], panel["momentum_state"], strict=False)
    ]
    panel["weight"] = 1.0  # equal-weight: one state per ETF
    panel["rs_rank_approx"] = panel["rs_state"].map(_RS_STATE_TO_RANK)

    rows: list[dict[str, object]] = []
    for (ticker, dt), group in panel.groupby(["etf_ticker", "date"]):
        dist = weighted_state_distribution(group[["state", "weight"]])
        agg = AggregateState.from_distribution(dist)

        pct_stage_2 = (
            dist.get("stage_2a", 0.0) + dist.get("stage_2b", 0.0) + dist.get("stage_2c", 0.0)
        )
        rs_vals = group["rs_rank_approx"].dropna()
        mean_rs = float(rs_vals.mean()) if not rs_vals.empty else None

        rows.append(
            {
                "etf_ticker": ticker,
                "date": dt,
                "dominant_state": agg.dominant_state,
                "dominant_share": agg.dominant_share,
                "n_holdings": len(group),
                "mean_rs_rank_12m": mean_rs,
                "pct_stage_2": pct_stage_2,
                "pct_stage_3": dist.get("stage_3", 0.0),
                "pct_stage_4": dist.get("stage_4", 0.0),
            }
        )
    return pd.DataFrame(rows)
