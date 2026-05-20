"""Tests for atlas/intelligence/aggregations/fund.py.

Panel shape post-rewrite: one row per (mstar_id, date) from
atlas_fund_lens_monthly. Columns: mstar_id, date, aligned_aum_pct,
avoid_aum_pct, strong_aum_pct, weak_aum_pct, composition_state,
holdings_state.
"""

from datetime import date

import pandas as pd
import pytest

from atlas.intelligence.aggregations.fund import (
    _normalize_composition_state,
    _normalize_holdings_state,
    aggregate_fund_composition,
    derive_fund_recommendation,
    derive_fund_recommendations_cross_sectional,
)


def _lens_panel() -> pd.DataFrame:
    """Synthetic atlas_fund_lens_monthly panel for tests."""
    return pd.DataFrame(
        [
            {
                # F1: heavily aligned (stage-2), weak holdings
                "mstar_id": "F1",
                "date": date(2024, 12, 31),
                "aligned_aum_pct": 0.75,
                "avoid_aum_pct": 0.05,
                "strong_aum_pct": 0.10,
                "weak_aum_pct": 0.40,
                "composition_state": "Aligned",
                "holdings_state": "Weak-Holdings",
            },
            {
                # F2: avoid-heavy, weak holdings; Misaligned normalised to Mixed
                "mstar_id": "F2",
                "date": date(2024, 12, 31),
                "aligned_aum_pct": 0.10,
                "avoid_aum_pct": 0.60,
                "strong_aum_pct": 0.05,
                "weak_aum_pct": 0.50,
                "composition_state": "Misaligned",
                "holdings_state": "Weak-Holdings",
            },
            {
                # F3: strong holdings, aligned
                "mstar_id": "F3",
                "date": date(2024, 12, 31),
                "aligned_aum_pct": 0.80,
                "avoid_aum_pct": 0.05,
                "strong_aum_pct": 0.70,
                "weak_aum_pct": 0.05,
                "composition_state": "Aligned",
                "holdings_state": "Strong-Holdings",
            },
            {
                # F4: NULL lens states -> fallback derivation
                "mstar_id": "F4",
                "date": date(2024, 12, 31),
                "aligned_aum_pct": 0.65,
                "avoid_aum_pct": 0.10,
                "strong_aum_pct": 0.20,
                "weak_aum_pct": 0.10,
                "composition_state": None,
                "holdings_state": None,
            },
        ]
    )


def test_aggregate_fund_composition_yields_one_row_per_fund() -> None:
    out = aggregate_fund_composition(_lens_panel())
    assert len(out) == 4
    assert set(out["mstar_id"]) == {"F1", "F2", "F3", "F4"}


def test_aggregate_fund_composition_f1_aligned() -> None:
    out = aggregate_fund_composition(_lens_panel())
    f1 = out[out["mstar_id"] == "F1"].iloc[0]
    assert f1["composition_state"] == "Aligned"
    assert f1["pct_holdings_stage_2"] == pytest.approx(0.75)
    assert f1["pct_holdings_stage_4"] == pytest.approx(0.05)
    # stage_3 = 1.0 - 0.75 - 0.05 = 0.20
    assert f1["pct_holdings_stage_3"] == pytest.approx(0.20, abs=1e-9)


def test_aggregate_fund_composition_f2_misaligned_holdings_weak() -> None:
    """Lens state Misaligned is normalised to Mixed for CHECK constraint."""
    out = aggregate_fund_composition(_lens_panel())
    f2 = out[out["mstar_id"] == "F2"].iloc[0]
    # Misaligned from lens -> normalised to Mixed
    # (CHECK constraint allows only Aligned/Mixed/Deteriorating)
    assert f2["composition_state"] == "Mixed"
    assert f2["holdings_state"] == "Weak-Holdings"


def test_aggregate_fund_composition_f4_null_states_derived() -> None:
    """Null lens states fall back to threshold-based derivation."""
    out = aggregate_fund_composition(_lens_panel())
    f4 = out[out["mstar_id"] == "F4"].iloc[0]
    # aligned_aum_pct=0.65 >= 0.60 -> Aligned
    assert f4["composition_state"] == "Aligned"
    # strong_aum_pct=0.20 < 0.60 and weak_aum_pct=0.10 <= 0.30 -> Mixed-Holdings
    assert f4["holdings_state"] == "Mixed-Holdings"


def test_aggregate_fund_composition_empty_returns_schema() -> None:
    out = aggregate_fund_composition(pd.DataFrame())
    assert list(out.columns) == [
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
    assert len(out) == 0


def test_aggregate_fund_composition_mean_within_state_rank_is_null() -> None:
    """mean_within_state_rank is always NULL -- no per-instrument data."""
    out = aggregate_fund_composition(_lens_panel())
    assert out["mean_within_state_rank"].isna().all()


def test_aggregate_fund_composition_n_holdings_is_zero_sentinel() -> None:
    """n_holdings is 0 (NOT NULL sentinel) since lens has no constituent count."""
    out = aggregate_fund_composition(_lens_panel())
    assert (out["n_holdings"] == 0).all()


def test_derive_fund_recommendation_aligned_strong_holdings_recommends() -> None:
    rec = derive_fund_recommendation(
        nav_state="Leader NAV",
        composition_state="Aligned",
        holdings_state="Strong-Holdings",
    )
    assert rec == "Recommended"


def test_derive_fund_recommendation_deteriorating_weak_holdings_exit() -> None:
    # Deteriorating composition + Weak-Holdings = worst combo -> Exit.
    # Wave 4A Task 4: shim no longer has short-circuit on Weak-Holdings alone.
    # Deteriorating AND Weak-Holdings is the most severe state → Exit.
    rec = derive_fund_recommendation(
        nav_state="Weak NAV",
        composition_state="Deteriorating",
        holdings_state="Weak-Holdings",
    )
    assert rec == "Exit"


def test_derive_fund_recommendation_deteriorating_alone_recommends_reduce() -> None:
    # Deteriorating composition without Weak-Holdings -> Reduce
    rec = derive_fund_recommendation(
        nav_state="Weak NAV",
        composition_state="Deteriorating",
        holdings_state="Mixed-Holdings",
    )
    assert rec == "Reduce"


def test_derive_fund_recommendation_weak_holdings_no_longer_short_circuits() -> None:
    # Wave 4A Task 4: Weak-Holdings alone no longer short-circuits to Reduce.
    # Aligned composition + Weak-Holdings + Strong NAV -> Hold
    # (use derive_fund_recommendations_cross_sectional for production ranking)
    rec = derive_fund_recommendation(
        nav_state="Strong NAV",
        composition_state="Aligned",
        holdings_state="Weak-Holdings",
    )
    assert rec == "Hold"


def test_derive_fund_recommendation_dislocation_suspended_exit() -> None:
    # DISLOCATION_SUSPENDED is the worst state -> Exit (was "Avoid")
    rec = derive_fund_recommendation(
        nav_state="DISLOCATION_SUSPENDED",
        composition_state="Aligned",
        holdings_state="Strong-Holdings",
    )
    assert rec == "Exit"


def test_derive_fund_recommendation_mixed_composition_hold() -> None:
    rec = derive_fund_recommendation(
        nav_state="Average NAV",
        composition_state="Mixed",
        holdings_state="Mixed-Holdings",
    )
    assert rec == "Hold"


# ---------------------------------------------------------------------------
# Normalization helper tests (Fix 3)
# ---------------------------------------------------------------------------


def test_normalize_holdings_state_known_values() -> None:
    """All valid CHECK-constraint values pass through unchanged."""
    for v in ("Strong-Holdings", "Weak-Holdings", "Mixed-Holdings", "Unknown"):
        assert _normalize_holdings_state(v) == v


def test_normalize_holdings_state_legacy_decent_maps_to_mixed() -> None:
    assert _normalize_holdings_state("Decent") == "Mixed-Holdings"


def test_normalize_holdings_state_legacy_aligned_maps_to_strong() -> None:
    assert _normalize_holdings_state("Aligned") == "Strong-Holdings"


def test_normalize_holdings_state_unknown_maps_to_unknown() -> None:
    assert _normalize_holdings_state("SomethingNew") == "Unknown"


def test_normalize_holdings_state_none_maps_to_unknown() -> None:
    assert _normalize_holdings_state(None) == "Unknown"


def test_normalize_composition_state_known_values() -> None:
    for v in ("Aligned", "Deteriorating", "Mixed"):
        assert _normalize_composition_state(v) == v


def test_normalize_composition_state_misaligned_maps_to_mixed() -> None:
    assert _normalize_composition_state("Misaligned") == "Mixed"


def test_normalize_composition_state_conflicted_maps_to_mixed() -> None:
    assert _normalize_composition_state("Conflicted") == "Mixed"


def test_normalize_composition_state_unknown_maps_to_mixed() -> None:
    assert _normalize_composition_state("GarbageValue") == "Mixed"


def test_aggregate_fund_composition_legacy_holdings_state_normalised() -> None:
    """'Decent' holdings_state from legacy lens is normalised to Mixed-Holdings."""
    panel = pd.DataFrame(
        [
            {
                "mstar_id": "LEGACY1",
                "date": date(2024, 12, 31),
                "aligned_aum_pct": 0.50,
                "avoid_aum_pct": 0.10,
                "strong_aum_pct": 0.20,
                "weak_aum_pct": 0.15,
                "composition_state": "Aligned",
                "holdings_state": "Decent",  # legacy value
            }
        ]
    )
    out = aggregate_fund_composition(panel)
    assert len(out) == 1
    assert out.iloc[0]["holdings_state"] == "Mixed-Holdings"


# ---------------------------------------------------------------------------
# Wave 4A Task 4 — cross-sectional hybrid-rank tests
# ---------------------------------------------------------------------------


def _all_weak_holdings_panel() -> pd.DataFrame:
    """Four funds, ALL with holdings_state == 'Weak-Holdings'.

    Expected cross-sectional scores (aligned_aum_pct * strong_aum_pct):
      F2: 0.10 * 0.05 = 0.005  (rank 0/3, pct 0.000 → band 0 → 'Exit')
      F4: 0.40 * 0.15 = 0.060  (rank 1/3, pct 0.333 → band 1 → 'Reduce')
      F3: 0.60 * 0.25 = 0.150  (rank 2/3, pct 0.667 → band 2 → 'Hold')
      F1: 0.70 * 0.30 = 0.210  (rank 3/3, pct 1.000 → band 3 → 'Recommended',
                                  floor strong_aum_pct=0.30 >= 0.20 → passes)
    """
    return pd.DataFrame(
        [
            {
                "mstar_id": "F1",
                "date": date(2025, 1, 31),
                "aligned_aum_pct": 0.70,
                "avoid_aum_pct": 0.05,
                "strong_aum_pct": 0.30,
                "weak_aum_pct": 0.35,
                "composition_state": "Aligned",
                "holdings_state": "Weak-Holdings",
            },
            {
                "mstar_id": "F2",
                "date": date(2025, 1, 31),
                "aligned_aum_pct": 0.10,
                "avoid_aum_pct": 0.50,
                "strong_aum_pct": 0.05,
                "weak_aum_pct": 0.60,
                "composition_state": "Deteriorating",
                "holdings_state": "Weak-Holdings",
            },
            {
                "mstar_id": "F3",
                "date": date(2025, 1, 31),
                "aligned_aum_pct": 0.60,
                "avoid_aum_pct": 0.10,
                "strong_aum_pct": 0.25,
                "weak_aum_pct": 0.40,
                "composition_state": "Mixed",
                "holdings_state": "Weak-Holdings",
            },
            {
                "mstar_id": "F4",
                "date": date(2025, 1, 31),
                "aligned_aum_pct": 0.40,
                "avoid_aum_pct": 0.20,
                "strong_aum_pct": 0.15,
                "weak_aum_pct": 0.50,
                "composition_state": "Mixed",
                "holdings_state": "Weak-Holdings",
            },
        ]
    )


def test_cross_sectional_all_weak_holdings_produces_spread() -> None:
    """When every fund has Weak-Holdings the old shim returned all-Reduce.

    The cross-sectional ranker must produce a spread of labels.
    """
    panel = _all_weak_holdings_panel()
    labels = derive_fund_recommendations_cross_sectional(panel)

    # Must NOT collapse to a single label
    unique_labels = set(labels.values())
    assert len(unique_labels) > 1, f"All funds got same label: {unique_labels}"

    # Hand-computed expected values (see docstring on _all_weak_holdings_panel)
    assert labels["F1"] == "Recommended"
    assert labels["F2"] == "Exit"
    assert labels["F3"] == "Hold"
    assert labels["F4"] == "Reduce"


def test_cross_sectional_floor_blocks_recommended() -> None:
    """Top-ranked fund with strong_aum_pct below floor is capped at 'Hold'.

    2-fund fixture:
      FA: aligned=0.80, strong=0.10 → score=0.08 (top rank, pct=1.0 → 'Recommended')
          floor check: strong_aum_pct=0.10 < default floor 0.20 → capped to 'Hold'
      FB: aligned=0.10, strong=0.05 → score=0.005 (bottom rank, pct=0.0 → 'Exit')
    """
    panel = pd.DataFrame(
        [
            {
                "mstar_id": "FA",
                "date": date(2025, 2, 28),
                "aligned_aum_pct": 0.80,
                "avoid_aum_pct": 0.05,
                "strong_aum_pct": 0.10,  # below floor_min=0.20
                "weak_aum_pct": 0.45,
                "composition_state": "Aligned",
                "holdings_state": "Weak-Holdings",
            },
            {
                "mstar_id": "FB",
                "date": date(2025, 2, 28),
                "aligned_aum_pct": 0.10,
                "avoid_aum_pct": 0.60,
                "strong_aum_pct": 0.05,
                "weak_aum_pct": 0.70,
                "composition_state": "Deteriorating",
                "holdings_state": "Weak-Holdings",
            },
        ]
    )
    labels = derive_fund_recommendations_cross_sectional(panel)
    # FA ranks top but fails the absolute floor → capped to 'Hold'
    assert labels["FA"] == "Hold"
    # FB ranks bottom → 'Exit'
    assert labels["FB"] == "Exit"


def test_aggregate_fund_composition_includes_recommendation_column() -> None:
    """aggregate_fund_composition returns a 'recommendation' column."""
    out = aggregate_fund_composition(_all_weak_holdings_panel())
    assert "recommendation" in out.columns, "Missing recommendation column"
    # The spread test: must not all be the same value
    unique_recs = set(out["recommendation"].tolist())
    assert len(unique_recs) > 1, f"All recommendations identical: {unique_recs}"


def test_aggregate_fund_composition_recommendation_not_all_reduce() -> None:
    """Old short-circuit made every fund 'Reduce'. New approach must produce a spread."""
    out = aggregate_fund_composition(_all_weak_holdings_panel())
    recs = set(out["recommendation"].tolist())
    assert (
        "Reduce" not in recs or len(recs) > 1
    ), "All funds got 'Reduce' — short-circuit not removed"


def test_aggregate_fund_composition_empty_recommendation_column() -> None:
    """Empty panel returns empty DataFrame that still has recommendation column."""
    out = aggregate_fund_composition(pd.DataFrame())
    assert "recommendation" in out.columns
