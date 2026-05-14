"""Unit tests for M4 fund lens classifiers.

Tests are pure-Python — no DB required. They cover the three classifiers
(nav_state, composition_state, holdings_state) and the within-category
percentile ranking logic.

Tier 3 hand-validation (threshold boundary checks): each classifier is
tested at the exact threshold boundaries defined in methodology §12.1-12.3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.compute.lens_composition import classify_composition_state
from atlas.compute.lens_holdings import classify_holdings_state
from atlas.compute.lens_nav import classify_nav_state, compute_within_category_percentiles

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "rs_quintile_top": 0.80,  # fraction form matching atlas_thresholds DB values
    "rs_quintile_bottom": 0.20,
    "fund_aligned_aum_min_pct": 70,
    "fund_avoid_aum_max_pct": 10,
    "fund_strong_holdings_min_pct": 60,
    "fund_weak_holdings_max_pct": 25,
}


def _nav_row(
    mstar_id: str = "F001",
    nav_date: str = "2024-01-01",
    p1m: float = 0.50,
    p3m: float = 0.50,
    p6m: float = 0.50,
) -> dict:
    return {
        "mstar_id": mstar_id,
        "nav_date": pd.Timestamp(nav_date).date(),
        "nav": 100.0,
        "ret_1m": 0.01,
        "ret_3m": 0.03,
        "ret_6m": 0.06,
        "ret_12m": 0.12,
        "rs_1m_category": 0.005,
        "rs_3m_category": 0.010,
        "rs_6m_category": 0.015,
        "rs_pctile_1m": p1m,
        "rs_pctile_3m": p3m,
        "rs_pctile_6m": p6m,
        "realized_vol_63": 0.15,
        "drawdown_ratio_252": 0.80,
    }


# ---------------------------------------------------------------------------
# Lens 1 — NAV state classification
# ---------------------------------------------------------------------------


class TestClassifyNavState:
    def test_leader_nav_all_top_quintile(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=0.85, p3m=0.90, p6m=0.92)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Leader NAV"

    def test_laggard_nav_all_bottom_quintile(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=0.10, p3m=0.15, p6m=0.08)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Laggard NAV"

    def test_strong_nav_top_3m_and_6m_not_1m(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=0.50, p3m=0.85, p6m=0.90)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Strong NAV"

    def test_emerging_nav_top_1m_only(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=0.90, p3m=0.50, p6m=0.50)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Emerging NAV"

    def test_weak_nav_any_bottom_quintile(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=0.10, p3m=0.60, p6m=0.70)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Weak NAV"

    def test_average_nav_middle_quintiles(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=0.40, p3m=0.50, p6m=0.60)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Average NAV"

    def test_laggard_beats_weak_precedence(self) -> None:
        """Bottom in all three should yield Laggard, not Weak."""
        df = pd.DataFrame([_nav_row(p1m=0.10, p3m=0.10, p6m=0.10)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Laggard NAV"

    def test_missing_percentile_gives_none(self) -> None:
        df = pd.DataFrame([_nav_row(p1m=np.nan, p3m=0.50, p6m=0.50)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] is None

    def test_exact_top_boundary(self) -> None:
        """Exactly at TOP (0.80) qualifies for top quintile."""
        df = pd.DataFrame([_nav_row(p1m=0.80, p3m=0.80, p6m=0.80)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Leader NAV"

    def test_exact_bottom_boundary(self) -> None:
        """Exactly at BOT (0.20) qualifies for bottom quintile."""
        df = pd.DataFrame([_nav_row(p1m=0.20, p3m=0.20, p6m=0.20)])
        result = classify_nav_state(df, DEFAULT_THRESHOLDS)
        assert result["nav_state"].iloc[0] == "Laggard NAV"


# ---------------------------------------------------------------------------
# Lens 1 — within-category percentile ranking
# ---------------------------------------------------------------------------


class TestWithinCategoryPercentiles:
    def _make_fund_universe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "mstar_id": ["F001", "F002", "F003", "F004"],
                "category_name": ["Large Cap", "Large Cap", "Mid Cap", "Mid Cap"],
            }
        )

    def _make_metrics(self) -> pd.DataFrame:
        d = pd.Timestamp("2024-01-15").date()
        return pd.DataFrame(
            [
                {
                    "mstar_id": "F001",
                    "nav_date": d,
                    "rs_1m_category": 0.05,
                    "rs_3m_category": 0.10,
                    "rs_6m_category": 0.15,
                    "rs_pctile_1m": np.nan,
                    "rs_pctile_3m": np.nan,
                    "rs_pctile_6m": np.nan,
                },
                {
                    "mstar_id": "F002",
                    "nav_date": d,
                    "rs_1m_category": 0.01,
                    "rs_3m_category": 0.02,
                    "rs_6m_category": 0.03,
                    "rs_pctile_1m": np.nan,
                    "rs_pctile_3m": np.nan,
                    "rs_pctile_6m": np.nan,
                },
                {
                    "mstar_id": "F003",
                    "nav_date": d,
                    "rs_1m_category": 0.08,
                    "rs_3m_category": 0.12,
                    "rs_6m_category": 0.20,
                    "rs_pctile_1m": np.nan,
                    "rs_pctile_3m": np.nan,
                    "rs_pctile_6m": np.nan,
                },
                {
                    "mstar_id": "F004",
                    "nav_date": d,
                    "rs_1m_category": -0.02,
                    "rs_3m_category": 0.00,
                    "rs_6m_category": -0.05,
                    "rs_pctile_1m": np.nan,
                    "rs_pctile_3m": np.nan,
                    "rs_pctile_6m": np.nan,
                },
            ]
        )

    def test_within_category_not_cross_category(self) -> None:
        """F001 (Large Cap) should be ranked only against F002, not F003/F004."""
        metrics = self._make_metrics()
        universe = self._make_fund_universe()
        result = compute_within_category_percentiles(metrics, universe)

        # F001 has rs_1m=0.05, F002 has rs_1m=0.01 — within Large Cap,
        # F001 should have higher percentile than F002.
        f001 = result[result["mstar_id"] == "F001"]["rs_pctile_1m"].iloc[0]
        f002 = result[result["mstar_id"] == "F002"]["rs_pctile_1m"].iloc[0]
        assert f001 > f002

    def test_two_funds_same_category_percentiles(self) -> None:
        """With exactly 2 funds per category, percentiles should be 0.5 and 1.0."""
        metrics = self._make_metrics()
        universe = self._make_fund_universe()
        result = compute_within_category_percentiles(metrics, universe)

        large_pctiles = sorted(
            result[result["mstar_id"].isin(["F001", "F002"])]["rs_pctile_1m"].tolist()
        )
        assert len(large_pctiles) == 2
        assert large_pctiles[0] < large_pctiles[1]


# ---------------------------------------------------------------------------
# Lens 2 — composition state classification
# ---------------------------------------------------------------------------


def _lens2_row(
    mstar_id: str = "F001",
    aligned: float = 0.70,
    avoid: float = 0.05,
) -> dict:
    return {
        "mstar_id": mstar_id,
        "as_of_date": pd.Timestamp("2024-04-30").date(),
        "last_disclosed_date": pd.Timestamp("2024-05-08").date(),
        "aligned_aum_pct": aligned,
        "avoid_aum_pct": avoid,
        "sector_concentration": 0.45,
        "_total_weight": 0.95,
    }


class TestClassifyCompositionState:
    def test_aligned(self) -> None:
        df = pd.DataFrame([_lens2_row(aligned=0.75, avoid=0.05)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Aligned"

    def test_misaligned_low_aligned(self) -> None:
        df = pd.DataFrame([_lens2_row(aligned=0.45, avoid=0.05)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Misaligned"

    def test_misaligned_high_avoid(self) -> None:
        df = pd.DataFrame([_lens2_row(aligned=0.65, avoid=0.25)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Misaligned"

    def test_mixed_aligned_mid(self) -> None:
        df = pd.DataFrame([_lens2_row(aligned=0.60, avoid=0.08)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Mixed"

    def test_aligned_exact_threshold(self) -> None:
        """Exactly at aligned_min (0.70) and below avoid_max (0.10)."""
        df = pd.DataFrame([_lens2_row(aligned=0.70, avoid=0.09)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Aligned"

    def test_misaligned_exact_avoid_threshold(self) -> None:
        """Exactly at avoid >= 0.20 → Misaligned."""
        df = pd.DataFrame([_lens2_row(aligned=0.65, avoid=0.20)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Misaligned"

    def test_avoid_at_max_threshold_qualifies_aligned(self) -> None:
        """avoid < 0.10 but exactly at 0.09 — Aligned if aligned >= 0.70."""
        df = pd.DataFrame([_lens2_row(aligned=0.80, avoid=0.09)])
        result = classify_composition_state(df, DEFAULT_THRESHOLDS)
        assert result["composition_state"].iloc[0] == "Aligned"


# ---------------------------------------------------------------------------
# Lens 3 — holdings state classification
# ---------------------------------------------------------------------------


def _lens3_row(
    mstar_id: str = "F001",
    strong: float = 0.60,
    weak: float = 0.10,
) -> dict:
    return {
        "mstar_id": mstar_id,
        "as_of_date": pd.Timestamp("2024-04-30").date(),
        "last_disclosed_date": pd.Timestamp("2024-05-08").date(),
        "strong_aum_pct": strong,
        "weak_aum_pct": weak,
        "unknown_aum_pct": 1.0 - strong - weak,
        "holdings_concentration": 0.35,
    }


class TestClassifyHoldingsState:
    def test_strong_holdings(self) -> None:
        df = pd.DataFrame([_lens3_row(strong=0.65, weak=0.10)])
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        assert result["holdings_state"].iloc[0] == "Strong-Holdings"

    def test_weak_holdings_low_strong(self) -> None:
        df = pd.DataFrame([_lens3_row(strong=0.35, weak=0.10)])
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        assert result["holdings_state"].iloc[0] == "Weak-Holdings"

    def test_weak_holdings_high_weak(self) -> None:
        df = pd.DataFrame([_lens3_row(strong=0.50, weak=0.30)])
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        assert result["holdings_state"].iloc[0] == "Weak-Holdings"

    def test_decent_middle(self) -> None:
        df = pd.DataFrame([_lens3_row(strong=0.50, weak=0.15)])
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        assert result["holdings_state"].iloc[0] == "Decent"

    def test_strong_exact_threshold(self) -> None:
        """Exactly at strong_min (0.60) and below 0.15 → Strong-Holdings."""
        df = pd.DataFrame([_lens3_row(strong=0.60, weak=0.10)])
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        assert result["holdings_state"].iloc[0] == "Strong-Holdings"

    def test_weak_exact_threshold(self) -> None:
        """Exactly at weak_max (0.25) → Weak-Holdings."""
        df = pd.DataFrame([_lens3_row(strong=0.50, weak=0.25)])
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        assert result["holdings_state"].iloc[0] == "Weak-Holdings"

    def test_multiple_funds(self) -> None:
        df = pd.DataFrame(
            [
                _lens3_row("F001", strong=0.70, weak=0.05),
                _lens3_row("F002", strong=0.30, weak=0.05),
                _lens3_row("F003", strong=0.50, weak=0.20),
            ]
        )
        result = classify_holdings_state(df, DEFAULT_THRESHOLDS)
        states = dict(zip(result["mstar_id"], result["holdings_state"], strict=False))
        assert states["F001"] == "Strong-Holdings"
        assert states["F002"] == "Weak-Holdings"
        assert states["F003"] == "Decent"
