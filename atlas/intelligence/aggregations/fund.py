"""Bottom-up fund composition + holdings aggregator.

Composition: % of fund AUM in each Weinstein state across constituent holdings.
Holdings: mean within_state_rank across holdings as a quality proxy.
Recommendation: derived from (nav_state, composition_state, holdings_state).

nav_state remains a fund-internal NAV-vs-category computation produced by
``atlas/compute/lens_nav.py``; this module only consumes it.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Thresholds for composition_state classification.
ALIGNED_THRESHOLD = 0.60  # >= 60% of holdings in stage 2 -> Aligned
DETERIORATING_THRESHOLD = 0.40  # >= 40% in stage 3/4 -> Deteriorating

# Thresholds for holdings_state classification.
STRONG_HOLDINGS_THRESHOLD = 0.60  # mean within_state_rank >= 0.60
WEAK_HOLDINGS_THRESHOLD = 0.30  # mean within_state_rank <= 0.30


_HOLDINGS_SQL = text("""
    SELECT
        h.mstar_id::text             AS mstar_id,
        h.as_of_date                 AS date,
        h.instrument_id::text        AS instrument_id,
        h.weight_pct                 AS weight_pct,
        s.state                      AS state,
        s.within_state_rank::float8  AS within_state_rank
    FROM atlas.atlas_fund_holdings h
    JOIN atlas.atlas_stock_state_daily s
      ON s.instrument_id = h.instrument_id
     AND s.date          = h.as_of_date
     AND s.classifier_version = 'v2.0-validated'
    WHERE (:as_of_date IS NULL OR h.as_of_date = :as_of_date::date)
""")


def load_fund_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a fund-holding-day panel suitable for composition aggregation."""
    with engine.connect() as c:
        return pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})


def aggregate_fund_composition(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fund holdings into composition + holdings states."""
    if panel.empty:
        return pd.DataFrame(
            columns=[
                "mstar_id",
                "date",
                "composition_state",
                "holdings_state",
                "pct_holdings_stage_2",
                "pct_holdings_stage_3",
                "pct_holdings_stage_4",
                "mean_within_state_rank",
                "n_holdings",
            ]
        )

    rows: list[dict[str, object]] = []
    panel = panel.copy()
    panel["weight_pct"] = panel["weight_pct"].astype(float) / 100.0

    for (mstar_id, dt), group in panel.groupby(["mstar_id", "date"]):
        total = group["weight_pct"].sum()
        norm = group["weight_pct"] / total if total > 0 else group["weight_pct"]

        # Vectorized state-family aggregation (no lambda/apply).
        stage_2_mask = group["state"].isin(("stage_2a", "stage_2b", "stage_2c"))
        stage_3_mask = group["state"] == "stage_3"
        stage_4_mask = group["state"] == "stage_4"

        pct_stage_2 = float(norm[stage_2_mask].sum())
        pct_stage_3 = float(norm[stage_3_mask].sum())
        pct_stage_4 = float(norm[stage_4_mask].sum())

        wsr = group["within_state_rank"].dropna()
        mean_wsr = float(wsr.mean()) if not wsr.empty else None

        if pct_stage_2 >= ALIGNED_THRESHOLD:
            comp = "Aligned"
        elif (pct_stage_3 + pct_stage_4) >= DETERIORATING_THRESHOLD:
            comp = "Deteriorating"
        else:
            comp = "Mixed"

        if mean_wsr is None:
            holdings = "Unknown"
        elif mean_wsr >= STRONG_HOLDINGS_THRESHOLD:
            holdings = "Strong-Holdings"
        elif mean_wsr <= WEAK_HOLDINGS_THRESHOLD:
            holdings = "Weak-Holdings"
        else:
            holdings = "Mixed-Holdings"

        rows.append(
            {
                "mstar_id": mstar_id,
                "date": dt,
                "composition_state": comp,
                "holdings_state": holdings,
                "pct_holdings_stage_2": pct_stage_2,
                "pct_holdings_stage_3": pct_stage_3,
                "pct_holdings_stage_4": pct_stage_4,
                "mean_within_state_rank": mean_wsr,
                "n_holdings": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


# Recommendation lookup table — (nav, composition, holdings) -> recommendation.
# Conservative-first: any "Avoid" condition dominates.
def derive_fund_recommendation(
    nav_state: str | None,
    composition_state: str,
    holdings_state: str,
) -> str:
    """Map the 3-tuple to Recommended / Hold / Avoid."""
    if nav_state == "DISLOCATION_SUSPENDED":
        return "Avoid"
    if composition_state == "Deteriorating" or holdings_state == "Weak-Holdings":
        return "Avoid"
    if (
        composition_state == "Aligned"
        and holdings_state == "Strong-Holdings"
        and (nav_state in ("Leader NAV", "Strong NAV", None))
    ):
        return "Recommended"
    return "Hold"
