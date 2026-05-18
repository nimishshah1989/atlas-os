"""Bottom-up sector state aggregator.

Reads ``atlas_stock_state_daily`` joined to ``atlas_universe_stocks``
(for sector + market_cap weights), produces one row per (sector, date)
with dominant state, distribution, breadth metrics.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)

_PANEL_SQL = text("""
    SELECT
        s.instrument_id::text       AS instrument_id,
        u.sector                    AS sector,
        s.date                      AS date,
        s.state                     AS state,
        s.within_state_rank::float8 AS within_state_rank,
        s.rs_rank_12m::float8       AS rs_rank_12m,
        u.market_cap_inr            AS market_cap
    FROM atlas.atlas_stock_state_daily s
    JOIN atlas.atlas_universe_stocks u USING (instrument_id)
    WHERE s.classifier_version = 'v2.0-validated'
      AND (:as_of_date IS NULL OR s.date = :as_of_date::date)
      AND u.sector IS NOT NULL
""")


def load_stock_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a stock-day panel suitable for aggregation."""
    with engine.connect() as c:
        df = pd.read_sql(_PANEL_SQL, c, params={"as_of_date": as_of_date})
    return df


def aggregate_sector_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate stock panel into sector-day rows.

    Returns a DataFrame with columns: sector, date, dominant_state,
    dominant_share, n_constituents, mean_within_state_rank,
    pct_stage_2 (sum of stage_2a/2b/2c), pct_stage_3, pct_stage_4,
    pct_stage_1, pct_uninvestable.
    """
    if panel.empty:
        return pd.DataFrame(
            columns=[
                "sector",
                "date",
                "dominant_state",
                "dominant_share",
                "n_constituents",
                "mean_within_state_rank",
                "pct_stage_2",
                "pct_stage_3",
                "pct_stage_4",
                "pct_stage_1",
                "pct_uninvestable",
            ]
        )

    rows: list[dict[str, object]] = []
    for (sector, dt), group in panel.groupby(["sector", "date"]):
        weighted = group.rename(columns={"market_cap": "weight"})
        dist = weighted_state_distribution(weighted[["state", "weight"]])
        agg = AggregateState.from_distribution(dist)
        wsr = group["within_state_rank"].dropna()
        pct_stage_2 = (
            dist.get("stage_2a", 0.0) + dist.get("stage_2b", 0.0) + dist.get("stage_2c", 0.0)
        )
        # dominant_share: for stage_2 variants report the combined family share
        # (the dominant state is still the strongest individual, but the share
        # reflects the full stage_2 cohort for breadth reporting).
        if agg.dominant_state in ("stage_2a", "stage_2b", "stage_2c"):
            reported_dominant_share = pct_stage_2
        else:
            reported_dominant_share = agg.dominant_share
        rows.append(
            {
                "sector": sector,
                "date": dt,
                "dominant_state": agg.dominant_state,
                "dominant_share": reported_dominant_share,
                "n_constituents": len(group),
                "mean_within_state_rank": (float(wsr.mean()) if not wsr.empty else None),
                "pct_stage_2": pct_stage_2,
                "pct_stage_3": dist.get("stage_3", 0.0),
                "pct_stage_4": dist.get("stage_4", 0.0),
                "pct_stage_1": dist.get("stage_1", 0.0),
                "pct_uninvestable": dist.get("uninvestable", 0.0),
            }
        )
    return pd.DataFrame(rows)
