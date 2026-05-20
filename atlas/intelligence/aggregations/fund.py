"""Bottom-up fund composition + holdings aggregator.

Reads pre-computed fund lens data from ``atlas_fund_lens_monthly``.
The fund pipeline already aggregates raw AMFI disclosure data and writes
(mstar_id, as_of_date, composition_state, holdings_state, aligned_aum_pct,
avoid_aum_pct, ...) into ``atlas_fund_lens_monthly``.

No raw per-instrument holdings table (instrument_id + weight_pct) exists
in the atlas schema as of 2026-05-19. The lens pipeline produces the
aggregated form; this module lifts it into atlas_fund_state_v2.

Public API:
  load_fund_holdings_panel(engine, as_of_date) -> pd.DataFrame
  aggregate_fund_composition(panel) -> pd.DataFrame
  derive_fund_recommendations_cross_sectional(panel, thresholds) -> dict[str, str]
  derive_fund_recommendation(nav_state, composition_state, holdings_state) -> str
    (compatibility shim — superseded by the cross-sectional function)

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

import math
from decimal import Decimal

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.ranking import RankConfig, hybrid_rank_labels

# Thresholds for composition_state classification (pass-through from lens,
# but also used as fallback if lens composition_state is NULL).
# TODO(P1): migrate these four constants to atlas.atlas_thresholds via migration 091.
ALIGNED_THRESHOLD = 0.60  # >= 60% of AUM in stage 2 -> Aligned
DETERIORATING_THRESHOLD = 0.40  # >= 40% in stage 3/4 -> Deteriorating

# Thresholds for holdings_state classification.
STRONG_HOLDINGS_THRESHOLD = 0.60  # strong_aum_pct >= 0.60
WEAK_HOLDINGS_THRESHOLD = 0.30  # weak_aum_pct > 0.30

# ---------------------------------------------------------------------------
# Inline defaults for fund band thresholds (cross-sectional hybrid rank).
# TODO Wave 4A Task 5: seed fund_band_p20/p50/p80/fund_recommended_floor into
# atlas_thresholds table so they are runtime-tunable.
# ---------------------------------------------------------------------------
_DEFAULT_FUND_BAND_P20 = Decimal("0.20")
_DEFAULT_FUND_BAND_P50 = Decimal("0.50")
_DEFAULT_FUND_BAND_P80 = Decimal("0.80")
_DEFAULT_FUND_RECOMMENDED_FLOOR = Decimal("0.20")  # strong_aum_pct >= 20% for 'Recommended'

# ---------------------------------------------------------------------------
# Legacy state value normalisation
# atlas_fund_lens_monthly may contain holdings_state / composition_state values
# that predate the CHECK constraint on atlas_fund_state_v2.
# Unmapped values fall back to "Unknown" / "Mixed" respectively.
# ---------------------------------------------------------------------------
_HOLDINGS_STATE_MAP: dict[str, str] = {
    "Strong-Holdings": "Strong-Holdings",
    "Weak-Holdings": "Weak-Holdings",
    "Mixed-Holdings": "Mixed-Holdings",
    "Unknown": "Unknown",
    # Legacy variants
    "Decent": "Mixed-Holdings",
    "Aligned": "Strong-Holdings",
}

_COMPOSITION_STATE_MAP: dict[str, str] = {
    "Aligned": "Aligned",
    "Deteriorating": "Deteriorating",
    "Mixed": "Mixed",
    # Legacy variants
    "Misaligned": "Mixed",
    "Conflicted": "Mixed",
}


def _normalize_holdings_state(s: str | None) -> str:
    """Map a raw holdings_state value to a CHECK-constraint-safe value.

    Unknown values (including None/empty) fall back to 'Unknown'.
    """
    return _HOLDINGS_STATE_MAP.get((s or "").strip(), "Unknown")


def _normalize_composition_state(s: str | None) -> str:
    """Map a raw composition_state value to a CHECK-constraint-safe value.

    Unknown values (including None/empty) fall back to 'Mixed'.
    Callers that compute composition_state from thresholds bypass this — it is
    only applied to values read directly from atlas_fund_lens_monthly.
    """
    return _COMPOSITION_STATE_MAP.get((s or "").strip(), "Mixed")


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
    _empty_cols = [
        "mstar_id",
        "date",
        "composition_state",
        "holdings_state",
        "pct_holdings_stage_2",
        "pct_holdings_stage_3",
        "pct_holdings_stage_4",
        "mean_within_state_rank",
        "n_holdings",
        "recommendation",
    ]
    if panel.empty:
        return pd.DataFrame({c: pd.Series([], dtype=object) for c in _empty_cols})

    rows: list[dict[str, object]] = []
    # Monthly cadence -- few hundred rows at most; iterrows is acceptable here.
    for _, row in panel.iterrows():
        mstar_id = row["mstar_id"]
        dt = row["date"]

        pct_stage_2 = float(row.get("aligned_aum_pct") or 0.0)
        pct_stage_4 = float(row.get("avoid_aum_pct") or 0.0)
        # Remainder that is not stage-2, stage-4, or unknown goes to stage-3.
        pct_stage_3 = max(0.0, 1.0 - pct_stage_2 - pct_stage_4)

        # Use lens-computed states directly; derive only if NULL/empty.
        # Normalise via the allowlist maps — atlas_fund_lens_monthly may contain
        # legacy values ("Misaligned", "Decent", etc.) that violate the
        # atlas_fund_state_v2 CHECK constraint.
        raw_comp = row.get("composition_state")
        if raw_comp:
            comp = _normalize_composition_state(raw_comp)
        else:
            if pct_stage_2 >= ALIGNED_THRESHOLD:
                comp = "Aligned"
            elif pct_stage_3 + pct_stage_4 >= DETERIORATING_THRESHOLD:
                comp = "Deteriorating"
            else:
                comp = "Mixed"

        raw_holdings = row.get("holdings_state")
        if raw_holdings:
            holdings = _normalize_holdings_state(raw_holdings)
        else:
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
    agg_df = pd.DataFrame(rows)

    # Attach cross-sectional recommendation labels.
    # Row count before/after must be equal (1-to-1 ranker).
    rows_before = len(agg_df)
    label_map = derive_fund_recommendations_cross_sectional(panel)
    mstar_ids: list[object] = agg_df["mstar_id"].tolist()
    agg_df["recommendation"] = [label_map.get(str(m), "Hold") for m in mstar_ids]
    rows_after = len(agg_df)
    assert (
        rows_before == rows_after
    ), f"recommendation join changed row count: {rows_before} → {rows_after}"

    return agg_df


def _to_decimal(value: object) -> Decimal:
    """Convert scalar to Decimal, returning Decimal("0") for None/NaN.

    Null component → 0 is intentional: missing data penalises rank rather
    than fabricating strength.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, float) and math.isnan(value):
        return Decimal("0")
    return Decimal(str(value))


def _fund_rank_config(thresholds: dict[str, Decimal] | None = None) -> RankConfig:
    """Build a RankConfig for fund cross-sectional labelling.

    Reads band thresholds from the supplied thresholds dict (as returned by
    load_thresholds()). Falls back to inline defaults when the key is absent
    or the dict is None — keeps unit tests DB-free.

    Args:
        thresholds: Optional mapping of threshold_key -> Decimal value.
                    Keys used: fund_band_p20, fund_band_p50, fund_band_p80,
                    fund_recommended_floor.

    Returns:
        RankConfig with Exit/Reduce/Hold/Recommended labels.
    """
    t = thresholds or {}
    p20 = t.get("fund_band_p20", _DEFAULT_FUND_BAND_P20)
    p50 = t.get("fund_band_p50", _DEFAULT_FUND_BAND_P50)
    p80 = t.get("fund_band_p80", _DEFAULT_FUND_BAND_P80)
    floor = t.get("fund_recommended_floor", _DEFAULT_FUND_RECOMMENDED_FLOOR)
    return RankConfig(
        labels=["Exit", "Reduce", "Hold", "Recommended"],
        band_pcts=[p20, p50, p80],
        floor_label="Recommended",
        floor_min=floor,
    )


def derive_fund_recommendations_cross_sectional(
    panel: pd.DataFrame,
    thresholds: dict[str, Decimal] | None = None,
) -> dict[str, str]:
    """Rank all funds cross-sectionally for a single date slice.

    Assigns Exit/Reduce/Hold/Recommended using hybrid_rank_labels.
    Guarantees a label spread — never collapses to one constant label.

    Score = aligned_aum_pct * strong_aum_pct (Decimal; null component → 0).
    Floor = strong_aum_pct. A fund ranked 'Recommended' that fails
    fund_recommended_floor (default 20%) is capped to 'Hold'.

    No nav_state or fund RS is available in the lens panel; composition quality
    (aligned_aum_pct) and holdings quality (strong_aum_pct) are the real columns.

    Args:
        panel: DataFrame with at least mstar_id, aligned_aum_pct, strong_aum_pct.
               Rows must cover a single date (caller's responsibility).
        thresholds: Optional threshold overrides loaded from atlas_thresholds via
                    load_thresholds(). Keys: fund_band_p20/p50/p80,
                    fund_recommended_floor. Defaults applied when absent.

    Returns:
        {mstar_id: label} for every row in the panel.
    """
    if panel.empty:
        return {}

    cfg = _fund_rank_config(thresholds)
    scores: dict[str, Decimal] = {}
    floor_values: dict[str, Decimal] = {}

    for rec in panel.to_dict("records"):
        mstar_id = str(rec["mstar_id"])
        aligned = _to_decimal(rec.get("aligned_aum_pct"))
        strong = _to_decimal(rec.get("strong_aum_pct"))
        scores[mstar_id] = aligned * strong
        floor_values[mstar_id] = strong

    return hybrid_rank_labels(scores, floor_values, cfg)


# ---------------------------------------------------------------------------
# Compatibility shim (superseded by derive_fund_recommendations_cross_sectional)
#
# derive_fund_recommendation remains public so that callers that have not yet
# migrated to the cross-sectional API (and existing tests) continue to compile.
# New callers should use derive_fund_recommendations_cross_sectional.
#
# The shim no longer contains the short-circuit
#   "holdings_state == 'Weak-Holdings' → Reduce"
# which caused 100% of real funds to return "Reduce" in thin markets.
# ---------------------------------------------------------------------------
def derive_fund_recommendation(
    nav_state: str | None,
    composition_state: str,
    holdings_state: str,
) -> str:
    """Map the 3-tuple to Recommended / Hold / Reduce / Exit.

    Compatibility shim. Superseded by derive_fund_recommendations_cross_sectional
    which ranks funds cross-sectionally and guarantees a label spread.

    This shim no longer short-circuits on Weak-Holdings alone. The short-circuit
    (holdings_state == "Weak-Holdings" → "Reduce") was removed because it caused
    100% of funds to return "Reduce" when the strong_aum_pct < 0.40 bar is
    unreachable in a thin market (Wave 4A Task 4).
    """
    if nav_state == "DISLOCATION_SUSPENDED":
        return "Exit"
    if composition_state == "Deteriorating" and holdings_state == "Weak-Holdings":
        return "Exit"
    if composition_state == "Deteriorating":
        return "Reduce"
    if (
        composition_state == "Aligned"
        and holdings_state == "Strong-Holdings"
        and (nav_state in ("Leader NAV", "Strong NAV", None))
    ):
        return "Recommended"
    return "Hold"
