"""Unit tests for M5 decision engine — pure-Python, no DB required.

Covers:
  - Stock investability gates (6)
  - Stock position sizing formula
  - Stock exit triggers (6)
  - ETF gate logic (5, incl. theme-conditional sector gate)
  - ETF exit triggers (5)
  - Fund recommendation taxonomy (4 states)
  - Fund gate columns
  - Fund exit triggers (4)
  - Fund recommendation transition triggers
  - Fund weeks_in_state consecutive streak

Tier 3 hand-validation: boundary cases for each decision branch.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.compute.decisions_etf import (
    _sector_gate_value,
    compute_etf_exit_triggers,
    compute_etf_gates,
)
from atlas.compute.decisions_fund import (
    _UPGRADE_PAIRS,
    compute_fund_exit_triggers,
    compute_fund_recommendations,
    compute_weeks_in_state,
)
from atlas.compute.decisions_stock import (
    MARKET_MULTIPLIERS,
    RISK_MULTIPLIERS,
    add_position_sizing,
    compute_exit_triggers,
    compute_investability_gates,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _stock_row(
    rs_state: str = "Leader",
    momentum_state: str = "Accelerating",
    risk_state: str = "Normal",
    volume_state: str = "Accumulation",
    sector_state: str = "Overweight",
    regime_state: str = "Risk-On",
    dislocation_active: bool = False,
    weinstein_gate_pass: bool = True,
) -> dict:
    return {
        "instrument_id": "I001",
        "date": pd.Timestamp("2024-06-01").date(),
        "rs_state": rs_state,
        "momentum_state": momentum_state,
        "risk_state": risk_state,
        "volume_state": volume_state,
        "sector": "Technology",
        "sector_state": sector_state,
        "regime_state": regime_state,
        "deployment_multiplier": 1.0,
        "dislocation_active": dislocation_active,
        "weinstein_gate_pass": weinstein_gate_pass,
    }


def _etf_row(
    rs_state: str = "Leader",
    momentum_state: str = "Accelerating",
    risk_state: str = "Normal",
    volume_state: str = "Accumulation",
    regime_state: str = "Risk-On",
    dislocation_active: bool = False,
    theme: str = "Broad",
    linked_sector: str | None = None,
    linked_sector_state: str | None = None,
) -> dict:
    return {
        "ticker": "NIFTYBEES",
        "date": pd.Timestamp("2024-06-01").date(),
        "rs_state": rs_state,
        "momentum_state": momentum_state,
        "risk_state": risk_state,
        "volume_state": volume_state,
        "regime_state": regime_state,
        "deployment_multiplier": 1.0,
        "dislocation_active": dislocation_active,
        "theme": theme,
        "linked_sector": linked_sector,
        "linked_sector_state": linked_sector_state,
    }


def _fund_row(
    nav_state: str = "Leader NAV",
    composition_state: str = "Aligned",
    holdings_state: str = "Strong-Holdings",
    regime_state: str = "Risk-On",
    dislocation_active: bool = False,
) -> dict:
    return {
        "mstar_id": "F001",
        "date": pd.Timestamp("2024-06-01").date(),
        "nav_state": nav_state,
        "composition_state": composition_state,
        "holdings_state": holdings_state,
        "regime_state": regime_state,
        "dislocation_active": dislocation_active,
    }


# ---------------------------------------------------------------------------
# Stock — Investability gates
# ---------------------------------------------------------------------------


class TestStockInvestabilityGates:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_stock_row(**kwargs)])  # type: ignore[arg-type]

    def test_all_pass_is_investable(self) -> None:
        result = compute_investability_gates(self._df())
        assert result["is_investable"].iloc[0] is True or result["is_investable"].iloc[0]

    def test_risk_off_fails_market_gate(self) -> None:
        result = compute_investability_gates(self._df(regime_state="Risk-Off"))
        assert not result["market_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_dislocation_fails_market_gate(self) -> None:
        result = compute_investability_gates(self._df(dislocation_active=True))
        assert not result["market_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_avoid_sector_fails_sector_gate(self) -> None:
        result = compute_investability_gates(self._df(sector_state="Avoid"))
        assert not result["sector_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_average_rs_fails_strength_gate(self) -> None:
        result = compute_investability_gates(self._df(rs_state="Average"))
        assert not result["strength_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_flat_momentum_fails_direction_gate(self) -> None:
        result = compute_investability_gates(self._df(momentum_state="Flat"))
        assert not result["direction_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_high_risk_fails_risk_gate(self) -> None:
        result = compute_investability_gates(self._df(risk_state="High"))
        assert not result["risk_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_distribution_fails_volume_gate(self) -> None:
        result = compute_investability_gates(self._df(volume_state="Heavy Distribution"))
        assert not result["volume_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_emerging_rs_passes_strength_gate(self) -> None:
        result = compute_investability_gates(self._df(rs_state="Emerging"))
        assert result["strength_gate"].iloc[0]

    def test_steady_buying_passes_volume_gate(self) -> None:
        result = compute_investability_gates(self._df(volume_state="Steady-Buying"))
        assert result["volume_gate"].iloc[0]
        assert result["is_investable"].iloc[0]

    def test_constructive_regime_passes_market_gate(self) -> None:
        result = compute_investability_gates(self._df(regime_state="Constructive"))
        assert result["market_gate"].iloc[0]

    def test_neutral_sector_passes_sector_gate(self) -> None:
        result = compute_investability_gates(self._df(sector_state="Neutral"))
        assert result["sector_gate"].iloc[0]


# ---------------------------------------------------------------------------
# Stock — Position sizing
# ---------------------------------------------------------------------------


class TestStockPositionSizing:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_stock_row(**kwargs)])  # type: ignore[arg-type]

    def test_risk_on_normal_risk_gives_full_size(self) -> None:
        df = add_position_sizing(self._df(regime_state="Risk-On", risk_state="Normal"))
        assert df["position_size_pct"].iloc[0] == pytest.approx(1.0 * 1.0)

    def test_constructive_regime_scales_down(self) -> None:
        df = add_position_sizing(self._df(regime_state="Constructive", risk_state="Normal"))
        assert df["position_size_pct"].iloc[0] == pytest.approx(0.7)

    def test_cautious_regime_low_risk_size(self) -> None:
        df = add_position_sizing(self._df(regime_state="Cautious", risk_state="Low"))
        assert df["position_size_pct"].iloc[0] == pytest.approx(0.4 * 1.2)

    def test_elevated_risk_scales_down(self) -> None:
        df = add_position_sizing(self._df(regime_state="Risk-On", risk_state="Elevated"))
        assert df["position_size_pct"].iloc[0] == pytest.approx(0.6)

    def test_high_risk_gives_zero_size(self) -> None:
        df = add_position_sizing(self._df(regime_state="Risk-On", risk_state="High"))
        assert df["position_size_pct"].iloc[0] == pytest.approx(0.0)

    def test_risk_off_gives_zero_size(self) -> None:
        df = add_position_sizing(self._df(regime_state="Risk-Off", risk_state="Low"))
        assert df["position_size_pct"].iloc[0] == pytest.approx(0.0)

    def test_all_market_multipliers_present(self) -> None:
        assert set(MARKET_MULTIPLIERS) == {"Risk-On", "Constructive", "Cautious", "Risk-Off"}

    def test_all_risk_multipliers_present(self) -> None:
        assert set(RISK_MULTIPLIERS) == {"Low", "Normal", "Elevated", "High", "Below Trend"}


# ---------------------------------------------------------------------------
# Stock — Exit triggers
# ---------------------------------------------------------------------------


class TestStockExitTriggers:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_stock_row(**kwargs)])  # type: ignore[arg-type]

    def test_risk_off_fires_market_exit(self) -> None:
        result = compute_exit_triggers(self._df(regime_state="Risk-Off"))
        assert result["exit_market_riskoff"].iloc[0]

    def test_avoid_sector_fires_sector_exit(self) -> None:
        result = compute_exit_triggers(self._df(sector_state="Avoid"))
        assert result["exit_sector_avoid"].iloc[0]

    def test_laggard_fires_rs_exit(self) -> None:
        result = compute_exit_triggers(self._df(rs_state="Laggard"))
        assert result["exit_rs_deteriorate"].iloc[0]

    def test_weak_rs_fires_rs_exit(self) -> None:
        result = compute_exit_triggers(self._df(rs_state="Weak"))
        assert result["exit_rs_deteriorate"].iloc[0]

    def test_average_rs_fires_rs_exit(self) -> None:
        result = compute_exit_triggers(self._df(rs_state="Average"))
        assert result["exit_rs_deteriorate"].iloc[0]

    def test_collapsing_fires_momentum_exit(self) -> None:
        result = compute_exit_triggers(self._df(momentum_state="Collapsing"))
        assert result["exit_momentum_collapse"].iloc[0]

    def test_heavy_distribution_fires_volume_exit(self) -> None:
        result = compute_exit_triggers(self._df(volume_state="Heavy Distribution"))
        assert result["exit_volume_distrib"].iloc[0]

    def test_exit_stop_loss_always_false_v0(self) -> None:
        result = compute_exit_triggers(self._df())
        assert not result["exit_stop_loss"].iloc[0]

    def test_no_exit_when_all_pass(self) -> None:
        result = compute_exit_triggers(self._df())
        for col in (
            "exit_market_riskoff",
            "exit_sector_avoid",
            "exit_rs_deteriorate",
            "exit_momentum_collapse",
            "exit_volume_distrib",
        ):
            assert not result[col].iloc[0]


# ---------------------------------------------------------------------------
# ETF — Sector gate (theme-conditional)
# ---------------------------------------------------------------------------


class TestETFSectorGate:
    def test_broad_always_passes(self) -> None:
        assert _sector_gate_value("Broad", None, None) is True
        assert _sector_gate_value("Broad", "Avoid", "Avoid") is True

    def test_sectoral_avoid_fails(self) -> None:
        assert _sector_gate_value("Sectoral", "Avoid", None) is False

    def test_sectoral_none_fails(self) -> None:
        assert _sector_gate_value("Sectoral", None, None) is False

    def test_sectoral_overweight_passes(self) -> None:
        assert _sector_gate_value("Sectoral", "Overweight", None) is True

    def test_sectoral_neutral_passes(self) -> None:
        assert _sector_gate_value("Sectoral", "Neutral", None) is True

    def test_thematic_avoid_dominant_fails(self) -> None:
        assert _sector_gate_value("Thematic", None, "Avoid") is False

    def test_thematic_none_dominant_autopasses(self) -> None:
        assert _sector_gate_value("Thematic", None, None) is True

    def test_thematic_overweight_dominant_passes(self) -> None:
        assert _sector_gate_value("Thematic", None, "Overweight") is True


# ---------------------------------------------------------------------------
# ETF — Full gate computation
# ---------------------------------------------------------------------------


class TestETFGates:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_etf_row(**kwargs)])  # type: ignore[arg-type]

    def test_all_pass_broad_is_investable(self) -> None:
        result = compute_etf_gates(self._df(theme="Broad"))
        assert result["is_investable"].iloc[0]

    def test_risk_off_fails_broad(self) -> None:
        result = compute_etf_gates(self._df(regime_state="Risk-Off"))
        assert not result["market_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_elevated_risk_passes_etf_risk_gate(self) -> None:
        # ETF allows Elevated (broader diversification reduces single-stock risk)
        result = compute_etf_gates(self._df(risk_state="Elevated"))
        assert result["risk_gate"].iloc[0]

    def test_high_risk_fails_etf_risk_gate(self) -> None:
        result = compute_etf_gates(self._df(risk_state="High"))
        assert not result["risk_gate"].iloc[0]

    def test_sectoral_etf_avoid_linked_sector_fails(self) -> None:
        result = compute_etf_gates(
            self._df(theme="Sectoral", linked_sector="Technology", linked_sector_state="Avoid")
        )
        assert not result["sector_gate"].iloc[0]
        assert not result["is_investable"].iloc[0]

    def test_consolidating_rs_passes_etf_strength_gate(self) -> None:
        result = compute_etf_gates(self._df(rs_state="Consolidating"))
        assert result["strength_gate"].iloc[0]


# ---------------------------------------------------------------------------
# ETF — Exit triggers
# ---------------------------------------------------------------------------


class TestETFExitTriggers:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_etf_row(**kwargs)])  # type: ignore[arg-type]

    def test_risk_off_fires_market_exit(self) -> None:
        df = compute_etf_gates(self._df(regime_state="Risk-Off"))
        result = compute_etf_exit_triggers(df)
        assert result["exit_market_riskoff"].iloc[0]

    def test_collapsing_fires_momentum_exit(self) -> None:
        df = compute_etf_gates(self._df(momentum_state="Collapsing"))
        result = compute_etf_exit_triggers(df)
        assert result["exit_momentum_collapse"].iloc[0]

    def test_laggard_rs_fires_rs_exit(self) -> None:
        df = compute_etf_gates(self._df(rs_state="Laggard"))
        result = compute_etf_exit_triggers(df)
        assert result["exit_rs_deteriorate"].iloc[0]

    def test_no_volume_heavy_dist_trigger_for_etf(self) -> None:
        df = compute_etf_gates(self._df())
        result = compute_etf_exit_triggers(df)
        assert "exit_volume_distrib" not in result.columns

    def test_exit_stop_loss_always_false_v0(self) -> None:
        df = compute_etf_gates(self._df())
        result = compute_etf_exit_triggers(df)
        assert not result["exit_stop_loss"].iloc[0]


# ---------------------------------------------------------------------------
# Fund — Recommendation taxonomy
# ---------------------------------------------------------------------------


class TestFundRecommendations:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_fund_row(**kwargs)])  # type: ignore[arg-type]

    def test_recommended_full_pass(self) -> None:
        result = compute_fund_recommendations(self._df())
        assert result["recommendation"].iloc[0] == "Recommended"
        assert result["is_investable"].iloc[0]

    def test_strong_nav_recommended(self) -> None:
        result = compute_fund_recommendations(
            self._df(
                nav_state="Strong NAV",
                composition_state="Aligned",
                holdings_state="Strong-Holdings",
            )
        )
        assert result["recommendation"].iloc[0] == "Recommended"

    def test_risk_off_forces_exit(self) -> None:
        result = compute_fund_recommendations(self._df(regime_state="Risk-Off"))
        assert result["recommendation"].iloc[0] == "Exit"
        assert not result["is_investable"].iloc[0]

    def test_dislocation_forces_exit(self) -> None:
        result = compute_fund_recommendations(self._df(dislocation_active=True))
        assert result["recommendation"].iloc[0] == "Exit"

    def test_laggard_nav_forces_exit(self) -> None:
        result = compute_fund_recommendations(self._df(nav_state="Laggard NAV"))
        assert result["recommendation"].iloc[0] == "Exit"

    def test_weak_nav_gives_reduce(self) -> None:
        result = compute_fund_recommendations(self._df(nav_state="Weak NAV"))
        assert result["recommendation"].iloc[0] == "Reduce"

    def test_misaligned_and_weak_holdings_gives_reduce(self) -> None:
        result = compute_fund_recommendations(
            self._df(
                nav_state="Average NAV",
                composition_state="Misaligned",
                holdings_state="Weak-Holdings",
            )
        )
        assert result["recommendation"].iloc[0] == "Reduce"

    def test_leader_nav_but_misaligned_gives_hold(self) -> None:
        result = compute_fund_recommendations(
            self._df(
                nav_state="Leader NAV",
                composition_state="Misaligned",
                holdings_state="Strong-Holdings",
            )
        )
        assert result["recommendation"].iloc[0] == "Hold"

    def test_average_nav_gives_hold(self) -> None:
        result = compute_fund_recommendations(self._df(nav_state="Average NAV"))
        assert result["recommendation"].iloc[0] == "Hold"

    def test_exit_beats_reduce_when_both_would_trigger(self) -> None:
        # Laggard NAV (Exit) AND Misaligned+Weak-Holdings (Reduce) → Exit wins
        result = compute_fund_recommendations(
            self._df(
                nav_state="Laggard NAV",
                composition_state="Misaligned",
                holdings_state="Weak-Holdings",
            )
        )
        assert result["recommendation"].iloc[0] == "Exit"


# ---------------------------------------------------------------------------
# Fund — Gate columns
# ---------------------------------------------------------------------------


class TestFundGateColumns:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_fund_row(**kwargs)])  # type: ignore[arg-type]

    def test_performance_gate_on_leader(self) -> None:
        result = compute_fund_recommendations(self._df(nav_state="Leader NAV"))
        assert result["performance_gate"].iloc[0]

    def test_performance_gate_off_average(self) -> None:
        result = compute_fund_recommendations(self._df(nav_state="Average NAV"))
        assert not result["performance_gate"].iloc[0]

    def test_sectors_gate_off_when_misaligned(self) -> None:
        result = compute_fund_recommendations(self._df(composition_state="Misaligned"))
        assert not result["sectors_gate"].iloc[0]

    def test_stocks_gate_off_when_weak_holdings(self) -> None:
        result = compute_fund_recommendations(self._df(holdings_state="Weak-Holdings"))
        assert not result["stocks_gate"].iloc[0]

    def test_market_gate_off_when_risk_off(self) -> None:
        result = compute_fund_recommendations(self._df(regime_state="Risk-Off"))
        assert not result["market_gate"].iloc[0]


# ---------------------------------------------------------------------------
# Fund — Lens-level exit triggers
# ---------------------------------------------------------------------------


class TestFundExitTriggers:
    def _df(self, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([_fund_row(**kwargs)])  # type: ignore[arg-type]

    def test_risk_off_fires_market_exit(self) -> None:
        result = compute_fund_exit_triggers(self._df(regime_state="Risk-Off"))
        assert result["exit_market_riskoff"].iloc[0]

    def test_misaligned_fires_composition_exit(self) -> None:
        result = compute_fund_exit_triggers(self._df(composition_state="Misaligned"))
        assert result["exit_composition_misaligned"].iloc[0]

    def test_weak_holdings_fires_holdings_exit(self) -> None:
        result = compute_fund_exit_triggers(self._df(holdings_state="Weak-Holdings"))
        assert result["exit_holdings_weak"].iloc[0]

    def test_weak_nav_fires_nav_deteriorate(self) -> None:
        result = compute_fund_exit_triggers(self._df(nav_state="Weak NAV"))
        assert result["exit_nav_deteriorate"].iloc[0]

    def test_laggard_nav_fires_nav_deteriorate(self) -> None:
        result = compute_fund_exit_triggers(self._df(nav_state="Laggard NAV"))
        assert result["exit_nav_deteriorate"].iloc[0]

    def test_no_exit_on_clean_fund(self) -> None:
        result = compute_fund_exit_triggers(self._df())
        for col in (
            "exit_market_riskoff",
            "exit_composition_misaligned",
            "exit_holdings_weak",
            "exit_nav_deteriorate",
        ):
            assert not result[col].iloc[0]


# ---------------------------------------------------------------------------
# Fund — Weeks in state
# ---------------------------------------------------------------------------


class TestFundWeeksInState:
    def test_streak_increments_on_same_recommendation(self) -> None:
        rows = [
            {
                "mstar_id": "F001",
                "date": pd.Timestamp(f"2024-01-0{i}").date(),
                "recommendation": "Recommended",
            }
            for i in range(1, 6)
        ]
        df = pd.DataFrame(rows)
        result = compute_weeks_in_state(df)
        assert list(result.sort_values("date")["weeks_in_current_state"]) == [1, 2, 3, 4, 5]

    def test_streak_resets_on_recommendation_change(self) -> None:
        rows = [
            {
                "mstar_id": "F001",
                "date": pd.Timestamp("2024-01-01").date(),
                "recommendation": "Hold",
            },
            {
                "mstar_id": "F001",
                "date": pd.Timestamp("2024-01-02").date(),
                "recommendation": "Hold",
            },
            {
                "mstar_id": "F001",
                "date": pd.Timestamp("2024-01-03").date(),
                "recommendation": "Exit",
            },
            {
                "mstar_id": "F001",
                "date": pd.Timestamp("2024-01-04").date(),
                "recommendation": "Exit",
            },
        ]
        df = pd.DataFrame(rows)
        result = compute_weeks_in_state(df.sort_values("date"))
        counts = list(result.sort_values("date")["weeks_in_current_state"])
        assert counts == [1, 2, 1, 2]

    def test_multiple_funds_independent_streaks(self) -> None:
        rows = [
            {
                "mstar_id": "F001",
                "date": pd.Timestamp("2024-01-01").date(),
                "recommendation": "Recommended",
            },
            {
                "mstar_id": "F001",
                "date": pd.Timestamp("2024-01-02").date(),
                "recommendation": "Recommended",
            },
            {
                "mstar_id": "F002",
                "date": pd.Timestamp("2024-01-01").date(),
                "recommendation": "Exit",
            },
            {
                "mstar_id": "F002",
                "date": pd.Timestamp("2024-01-02").date(),
                "recommendation": "Recommended",
            },
        ]
        df = pd.DataFrame(rows)
        result = compute_weeks_in_state(df)
        f1 = (
            result[result["mstar_id"] == "F001"]
            .sort_values("date")["weeks_in_current_state"]
            .tolist()
        )
        f2 = (
            result[result["mstar_id"] == "F002"]
            .sort_values("date")["weeks_in_current_state"]
            .tolist()
        )
        assert f1 == [1, 2]
        assert f2 == [1, 1]  # resets because recommendation changed


# ---------------------------------------------------------------------------
# Fund — Upgrade pairs (add_trigger logic)
# ---------------------------------------------------------------------------


class TestFundUpgradePairs:
    def test_hold_to_recommended_is_upgrade(self) -> None:
        assert ("Hold", "Recommended") in _UPGRADE_PAIRS

    def test_exit_to_recommended_is_upgrade(self) -> None:
        assert ("Exit", "Recommended") in _UPGRADE_PAIRS

    def test_recommended_to_hold_is_not_upgrade(self) -> None:
        assert ("Recommended", "Hold") not in _UPGRADE_PAIRS

    def test_exit_to_reduce_is_upgrade(self) -> None:
        assert ("Exit", "Reduce") in _UPGRADE_PAIRS

    def test_reduce_to_exit_is_not_upgrade(self) -> None:
        assert ("Reduce", "Exit") not in _UPGRADE_PAIRS
