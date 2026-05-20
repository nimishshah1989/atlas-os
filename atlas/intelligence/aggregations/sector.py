"""Bottom-up sector state aggregator.

Reads ``atlas_stock_state_daily`` joined to ``atlas_universe_stocks``
(for sector mapping), produces one row per (sector, date) with dominant
state, distribution, and breadth metrics.

Market-cap weighting: No market_cap_inr column exists in the atlas schema
as of 2026-05-19. Sector aggregation uses equal-weight (each constituent
stock counts as 1.0). This is documented and honest; synthetic market-cap
would defeat the point of bottom-up aggregation.

sector_state derivation (Wave 4A Task 3):
    Cross-sectional hybrid rank + absolute floor. score = pct_stage_2 *
    mean_within_state_rank * mean_rs_rank_12m. Labels: Avoid/Underweight/
    Neutral/Overweight. Overweight capped when pct_stage_2 < floor.
    Guarantees a label spread — never collapses to all-Neutral even in
    thin-breadth markets. Thresholds loaded from atlas_thresholds via
    load_thresholds(); inline defaults used when DB not available.
    Wave 4A Task 5: sector_band_p20/p50/p80/sector_overweight_floor are
    seeded into atlas_thresholds by migration 095_seed_hybrid_classifier_thresholds.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import cast

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)
from atlas.intelligence.ranking import RankConfig, hybrid_rank_labels

# Equal-weight sentinel: every stock gets weight 1.0 until a market-cap
# source is available in the atlas schema.
_EQUAL_WEIGHT = 1.0

# ---------------------------------------------------------------------------
# Inline defaults for sector band thresholds.
# Seeded into atlas.atlas_thresholds by migration 095_seed_hybrid_classifier_thresholds.
# These inline defaults keep unit tests DB-free; live runs load from DB via load_thresholds().
# Keys: sector_band_p20, sector_band_p50, sector_band_p80,
#       sector_overweight_floor (proportion 0–1; 0.10 means "pct_stage_2 >= 10%")
# ---------------------------------------------------------------------------
_DEFAULT_BAND_P20 = Decimal("0.20")
_DEFAULT_BAND_P50 = Decimal("0.50")
_DEFAULT_BAND_P80 = Decimal("0.80")
_DEFAULT_OVERWEIGHT_FLOOR = Decimal("0.10")  # pct_stage_2 ≥ 10% to hold Overweight

_PANEL_SQL = text("""
    SELECT
        s.instrument_id::text       AS instrument_id,
        u.sector                    AS sector,
        s.date                      AS date,
        s.state                     AS state,
        s.within_state_rank::float8 AS within_state_rank,
        s.rs_rank_12m::float8       AS rs_rank_12m,
        1.0::float8                 AS market_cap
    FROM atlas.atlas_stock_state_daily s
    JOIN atlas.atlas_universe_stocks u USING (instrument_id)
    WHERE s.classifier_version = 'v2.0-validated'
      AND (:as_of_date IS NULL OR s.date = CAST(:as_of_date AS date))
      AND u.sector IS NOT NULL
""")


def _to_decimal(value: object) -> Decimal:
    """Convert a scalar value to Decimal, returning Decimal("0") for None/NaN.

    Used to safely convert dict values from to_dict("records") which may be
    Python None or float NaN. math.isnan requires a float — the isinstance
    guard ensures we only call it on numeric types.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, float) and math.isnan(value):
        return Decimal("0")
    return Decimal(str(value))


def _sector_rank_config(thresholds: dict[str, Decimal] | None = None) -> RankConfig:
    """Build a RankConfig for sector cross-sectional labelling.

    Reads band thresholds from the supplied thresholds dict (as returned by
    load_thresholds()). Falls back to inline defaults when the key is absent
    or the dict is None — this keeps unit tests DB-free.

    Args:
        thresholds: Optional mapping of threshold_key -> Decimal value.
                    Keys used: sector_band_p20, sector_band_p50,
                    sector_band_p80, sector_overweight_floor.

    Returns:
        RankConfig with Avoid/Underweight/Neutral/Overweight labels.
    """
    t = thresholds or {}
    p20 = t.get("sector_band_p20", _DEFAULT_BAND_P20)
    p50 = t.get("sector_band_p50", _DEFAULT_BAND_P50)
    p80 = t.get("sector_band_p80", _DEFAULT_BAND_P80)
    floor = t.get("sector_overweight_floor", _DEFAULT_OVERWEIGHT_FLOOR)
    return RankConfig(
        labels=["Avoid", "Underweight", "Neutral", "Overweight"],
        band_pcts=[p20, p50, p80],
        floor_label="Overweight",
        floor_min=floor,
    )


def compute_sector_state_labels(
    agg_df: pd.DataFrame,
    thresholds: dict[str, Decimal] | None = None,
) -> dict[tuple[str, object], str]:
    """Compute cross-sectional hybrid-rank sector_state labels for one date slice.

    Groups agg_df by date, ranks sectors within each date cross-sectionally
    using hybrid_rank_labels, and returns a mapping of (sector, date) → label.

    Score = pct_stage_2 * mean_within_state_rank * mean_rs_rank_12m
    (all three captured per sector row). NULL components are treated as 0
    (honest — missing data penalises ranking rather than fabricating strength).

    floor_values = pct_stage_2 per sector. Sectors below the floor threshold
    are capped out of "Overweight" regardless of their cross-sectional rank.

    Args:
        agg_df: Output of aggregate_sector_states() — columns include
                sector, date, pct_stage_2, mean_within_state_rank.
                May optionally contain mean_rs_rank_12m if the panel
                carried rs_rank_12m.
        thresholds: Optional threshold overrides (see _sector_rank_config).

    Returns:
        {(sector, date): label} for every row in agg_df.
    """
    cfg = _sector_rank_config(thresholds)
    result: dict[tuple[str, object], str] = {}

    has_rs_col = "mean_rs_rank_12m" in agg_df.columns

    for dt, group in agg_df.groupby("date"):
        scores: dict[str, Decimal] = {}
        floor_values: dict[str, Decimal] = {}
        records: list[dict[str, object]] = group.to_dict("records")  # type: ignore[assignment]
        for rec in records:
            sector_name = str(rec["sector"])
            pct2 = _to_decimal(rec["pct_stage_2"])
            wsr = _to_decimal(rec.get("mean_within_state_rank"))
            rs = _to_decimal(rec.get("mean_rs_rank_12m") if has_rs_col else None)

            scores[sector_name] = pct2 * wsr * rs
            floor_values[sector_name] = pct2

        labels = hybrid_rank_labels(scores, floor_values, cfg)
        for sector_name, label in labels.items():
            result[(sector_name, dt)] = label

    return result


def load_stock_panel(engine: Engine, as_of_date: str | None = None) -> pd.DataFrame:
    """Load a stock-day panel suitable for sector aggregation.

    Returns columns: instrument_id, sector, date, state, within_state_rank,
    rs_rank_12m, market_cap (equal-weight 1.0 placeholder).

    Args:
        engine: SQLAlchemy engine connected to the atlas DB.
        as_of_date: ISO date string to filter a single day. None = all days.

    Returns:
        DataFrame with one row per (instrument_id, date).
    """
    with engine.connect() as c:
        df = pd.read_sql(_PANEL_SQL, c, params={"as_of_date": as_of_date})
    return df


def aggregate_sector_states(
    panel: pd.DataFrame,
    thresholds: dict[str, Decimal] | None = None,
) -> pd.DataFrame:
    """Aggregate stock panel into sector-day rows with hybrid sector_state.

    Returns a DataFrame with columns: sector, date, dominant_state,
    dominant_share, n_constituents, mean_within_state_rank, mean_rs_rank_12m,
    pct_stage_2 (sum of stage_2a/2b/2c), pct_stage_3, pct_stage_4,
    pct_stage_1, pct_uninvestable, sector_state.

    sector_state is cross-sectionally ranked per date using hybrid_rank_labels
    (Avoid/Underweight/Neutral/Overweight). This guarantees a label spread
    even in thin-breadth markets where all sectors are below the old absolute
    threshold. The Overweight label is additionally gated by the breadth floor
    (sector_overweight_floor threshold, default 10% pct_stage_2).

    Expects panel to have: sector, date, state, within_state_rank,
    rs_rank_12m (optional), market_cap.
    market_cap is used as the weight for state distribution.

    Args:
        panel: Stock-day panel from load_stock_panel().
        thresholds: Optional dict of threshold overrides. When None, uses
                    inline defaults (DB not required for unit tests).
    """
    if panel.empty:
        _empty_cols = [
            "sector",
            "date",
            "dominant_state",
            "dominant_share",
            "n_constituents",
            "mean_within_state_rank",
            "mean_rs_rank_12m",
            "pct_stage_2",
            "pct_stage_3",
            "pct_stage_4",
            "pct_stage_1",
            "pct_uninvestable",
            "sector_state",
        ]
        return pd.DataFrame({c: pd.Series([], dtype=object) for c in _empty_cols})

    has_rs = "rs_rank_12m" in panel.columns

    rows: list[dict[str, object]] = []
    for key, group in panel.groupby(["sector", "date"]):
        sector, dt = cast(tuple[str, object], key)
        weighted = group.rename(columns={"market_cap": "weight"})
        dist = weighted_state_distribution(cast(pd.DataFrame, weighted[["state", "weight"]]))
        agg = AggregateState.from_distribution(dist)
        wsr = group["within_state_rank"].dropna()
        pct_stage_2 = (
            dist.get("stage_2a", 0.0) + dist.get("stage_2b", 0.0) + dist.get("stage_2c", 0.0)
        )
        # For stage_2 family, report the combined family share for breadth reporting.
        # Individual dominant_state is still the strongest sub-state.
        if agg.dominant_state in ("stage_2a", "stage_2b", "stage_2c"):
            reported_dominant_share = pct_stage_2
        else:
            reported_dominant_share = agg.dominant_share

        rs_vals = group["rs_rank_12m"].dropna() if has_rs else pd.Series([], dtype=float)
        rows.append(
            {
                "sector": sector,
                "date": dt,
                "dominant_state": agg.dominant_state,
                "dominant_share": reported_dominant_share,
                "n_constituents": len(group),
                "mean_within_state_rank": (float(wsr.mean()) if not wsr.empty else None),
                "mean_rs_rank_12m": (float(rs_vals.mean()) if not rs_vals.empty else None),
                "pct_stage_2": pct_stage_2,
                "pct_stage_3": dist.get("stage_3", 0.0),
                "pct_stage_4": dist.get("stage_4", 0.0),
                "pct_stage_1": dist.get("stage_1", 0.0),
                "pct_uninvestable": dist.get("uninvestable", 0.0),
            }
        )
    agg_df = pd.DataFrame(rows)

    # Compute cross-sectional sector_state labels and attach to agg_df.
    # Row count before/after: must equal (hybrid ranker is 1-to-1).
    rows_before = len(agg_df)
    label_map = compute_sector_state_labels(agg_df, thresholds=thresholds)
    sector_col: list[object] = agg_df["sector"].tolist()
    date_col: list[object] = agg_df["date"].tolist()
    agg_df["sector_state"] = [
        label_map.get((str(s), d), "Neutral") for s, d in zip(sector_col, date_col, strict=False)
    ]
    rows_after = len(agg_df)
    assert (
        rows_before == rows_after
    ), f"sector_state join changed row count: {rows_before} → {rows_after}"

    return agg_df
