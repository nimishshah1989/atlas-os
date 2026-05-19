"""Bottom-up fund composition + holdings aggregator.

Reads pre-computed fund lens data from ``atlas_fund_lens_monthly``.
The fund pipeline already aggregates raw AMFI disclosure data and writes
(mstar_id, as_of_date, composition_state, holdings_state, aligned_aum_pct,
avoid_aum_pct, ...) into ``atlas_fund_lens_monthly``.

No raw per-instrument holdings table (instrument_id + weight_pct) exists
in the atlas schema as of 2026-05-19. The lens pipeline produces the
aggregated form; this module lifts it into atlas_fund_state_v2.

Public API is unchanged -- callers use:
  load_fund_holdings_panel(engine, as_of_date) -> pd.DataFrame
  aggregate_fund_composition(panel) -> pd.DataFrame
  derive_fund_recommendation(nav_state, composition_state, holdings_state) -> str

Column mapping from atlas_fund_lens_monthly:
  aligned_aum_pct  -> pct_holdings_stage_2  (% of AUM in stage-2 state)
  avoid_aum_pct    -> pct_holdings_stage_4  (% in avoid / stage-4)
  remainder        -> pct_holdings_stage_3  (100% - stage2 - stage4 - unknown)
  n_holdings       -> 0 (NOT NULL sentinel; no per-constituent data in lens)
  mean_within_state_rank -> NULL (not available in lens)

nav_state remains a fund-internal NAV-vs-category computation produced by
``atlas/compute/lens_nav.py``; this module only consumes it.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Thresholds for composition_state classification (pass-through from lens,
# but also used as fallback if lens composition_state is NULL).
ALIGNED_THRESHOLD = 0.60  # >= 60% of AUM in stage 2 -> Aligned
DETERIORATING_THRESHOLD = 0.40  # >= 40% in stage 3/4 -> Deteriorating

# Thresholds for holdings_state classification.
STRONG_HOLDINGS_THRESHOLD = 0.60  # strong_aum_pct >= 0.60
WEAK_HOLDINGS_THRESHOLD = 0.30  # weak_aum_pct > 0.30


_HOLDINGS_SQL = text("""
    SELECT
        mstar_id::text               AS mstar_id,
        as_of_date                   AS date,
        aligned_aum_pct::float8      AS aligned_aum_pct,
        avoid_aum_pct::float8        AS avoid_aum_pct,
        strong_aum_pct::float8       AS strong_aum_pct,
        weak_aum_pct::float8         AS weak_aum_pct,
        composition_state            AS composition_state,
        holdings_state               AS holdings_state
    FROM atlas.atlas_fund_lens_monthly
    WHERE (:as_of_date IS NULL OR as_of_date = CAST(:as_of_date AS date))
      AND composition_state IS NOT NULL
""")


def load_fund_holdings_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a fund-month panel from atlas_fund_lens_monthly.

    Returns one row per (mstar_id, as_of_date) with columns:
    mstar_id, date, aligned_aum_pct, avoid_aum_pct, strong_aum_pct,
    weak_aum_pct, composition_state, holdings_state.

    The panel covers monthly disclosure cadence. For daily v2 population,
    callers should use the most-recent-on-or-before disclosure date.

    Args:
        engine: SQLAlchemy engine connected to the atlas DB.
        as_of_date: ISO date string to filter a single disclosure month.
            None = all months in the table.

    Returns:
        DataFrame with one row per (mstar_id, disclosure date).
    """
    with engine.connect() as c:
        return pd.read_sql(_HOLDINGS_SQL, c, params={"as_of_date": as_of_date})


def aggregate_fund_composition(panel: pd.DataFrame) -> pd.DataFrame:
    """Lift pre-computed fund lens data into the fund_state_v2 shape.

    Accepts the panel returned by ``load_fund_holdings_panel`` (or a
    synthetic DataFrame with the same column set for tests).

    For each (mstar_id, date) row:
    - composition_state: taken directly from the lens (Aligned/Mixed/Misaligned).
      Misaligned is normalised to Mixed (CHECK constraint on atlas_fund_state_v2
      only allows Aligned/Mixed/Deteriorating). Falls back to threshold logic if NULL.
    - holdings_state: taken directly from the lens.
    - pct_holdings_stage_2: aligned_aum_pct (already a 0-1 fraction).
    - pct_holdings_stage_4: avoid_aum_pct.
    - pct_holdings_stage_3: remainder after removing stage-2, stage-4, unknown.
    - mean_within_state_rank: NULL (not available at lens grain).
    - n_holdings: 0 (NOT NULL sentinel; no constituent count in lens).

    Returns:
        DataFrame with columns matching atlas_fund_state_v2 schema.
    """
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
    # Monthly cadence -- few hundred rows at most; iterrows is acceptable here.
    for _, row in panel.iterrows():
        mstar_id = row["mstar_id"]
        dt = row["date"]

        pct_stage_2 = float(row.get("aligned_aum_pct") or 0.0)
        pct_stage_4 = float(row.get("avoid_aum_pct") or 0.0)
        # Remainder that is not stage-2, stage-4, or unknown goes to stage-3.
        pct_stage_3 = max(0.0, 1.0 - pct_stage_2 - pct_stage_4)

        # Use lens-computed states directly; derive only if NULL.
        # Normalise: atlas_fund_lens_monthly uses "Misaligned" but
        # atlas_fund_state_v2 CHECK constraint only allows Aligned/Mixed/Deteriorating.
        # Misaligned (avg aligned_aum_pct ~35%) maps to Mixed semantically.
        comp = row.get("composition_state")
        if comp == "Misaligned":
            comp = "Mixed"
        if not comp:
            if pct_stage_2 >= ALIGNED_THRESHOLD:
                comp = "Aligned"
            elif pct_stage_3 + pct_stage_4 >= DETERIORATING_THRESHOLD:
                comp = "Deteriorating"
            else:
                comp = "Mixed"

        holdings = row.get("holdings_state")
        if not holdings:
            strong = float(row.get("strong_aum_pct") or 0.0)
            weak = float(row.get("weak_aum_pct") or 0.0)
            if strong >= STRONG_HOLDINGS_THRESHOLD:
                holdings = "Strong-Holdings"
            elif weak > WEAK_HOLDINGS_THRESHOLD:
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
                "mean_within_state_rank": None,
                # Lens pipeline does not track per-instrument holding count.
                # 0 is used as a NOT-NULL sentinel -- the column is NOT NULL in
                # atlas_fund_state_v2 but we have no constituent-level data.
                "n_holdings": 0,
            }
        )
    return pd.DataFrame(rows)


# Recommendation lookup table -- (nav, composition, holdings) -> recommendation.
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
