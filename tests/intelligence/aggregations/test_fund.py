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
    aggregate_fund_composition,
    derive_fund_recommendation,
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


def test_derive_fund_recommendation_deteriorating_recommends_avoid() -> None:
    rec = derive_fund_recommendation(
        nav_state="Weak NAV",
        composition_state="Deteriorating",
        holdings_state="Weak-Holdings",
    )
    assert rec == "Avoid"


def test_derive_fund_recommendation_weak_holdings_avoid() -> None:
    rec = derive_fund_recommendation(
        nav_state="Strong NAV",
        composition_state="Aligned",
        holdings_state="Weak-Holdings",
    )
    assert rec == "Avoid"


def test_derive_fund_recommendation_dislocation_suspended_avoid() -> None:
    rec = derive_fund_recommendation(
        nav_state="DISLOCATION_SUSPENDED",
        composition_state="Aligned",
        holdings_state="Strong-Holdings",
    )
    assert rec == "Avoid"


def test_derive_fund_recommendation_mixed_composition_hold() -> None:
    rec = derive_fund_recommendation(
        nav_state="Average NAV",
        composition_state="Mixed",
        holdings_state="Mixed-Holdings",
    )
    assert rec == "Hold"
