"""Bottom-up ETF state aggregator.

For each (etf_ticker, date), aggregates constituent stock states
weighted by holding weight_pct.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)

_HOLDINGS_SQL = text("""
    SELECT
        h.etf_ticker             AS etf_ticker,
        h.as_of_date             AS date,
        h.instrument_id::text    AS instrument_id,
        h.weight_pct             AS weight_pct,
        s.state                  AS state,
        s.rs_rank_12m::float8    AS rs_rank_12m
    FROM atlas.atlas_etf_holdings h
    JOIN atlas.atlas_stock_state_daily s
      ON s.instrument_id = h.instrument_id
     AND s.date          = h.as_of_date
     AND s.classifier_version = 'v2.0-validated'
    WHERE (:as_of_date IS NULL OR h.as_of_date = :as_of_date::date)
""")


def load_etf_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load an ETF-holding-day panel suitable for aggregation."""
    with engine.connect() as c:
        return pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})


def aggregate_etf_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ETF holdings into ETF-day state rows."""
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
    panel["weight_pct"] = panel["weight_pct"].astype(float)

    rows: list[dict[str, object]] = []
    for (ticker, dt), group in panel.groupby(["etf_ticker", "date"]):
        weighted = group.rename(columns={"weight_pct": "weight"})
        dist = weighted_state_distribution(weighted[["state", "weight"]])
        agg = AggregateState.from_distribution(dist)
        total_w = group["weight_pct"].sum()
        mean_rs = (
            (group["weight_pct"] * group["rs_rank_12m"]).sum() / total_w if total_w > 0 else None
        )
        rows.append(
            {
                "etf_ticker": ticker,
                "date": dt,
                "dominant_state": agg.dominant_state,
                "dominant_share": agg.dominant_share,
                "n_holdings": int(len(group)),
                "mean_rs_rank_12m": (float(mean_rs) if mean_rs is not None else None),
                "pct_stage_2": (
                    dist.get("stage_2a", 0.0)
                    + dist.get("stage_2b", 0.0)
                    + dist.get("stage_2c", 0.0)
                ),
                "pct_stage_3": dist.get("stage_3", 0.0),
                "pct_stage_4": dist.get("stage_4", 0.0),
            }
        )
    return pd.DataFrame(rows)
