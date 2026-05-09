"""Unit tests verifying compute_investability_gates uses policy loader when engine is provided."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from atlas.compute.decisions_stock import compute_investability_gates


def _make_test_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "regime_state": ["Risk-On", "Risk-On", "Risk-Off"],
            "dislocation_active": [False, False, False],
            "sector_state": ["Overweight", "Avoid", "Overweight"],
            "rs_state": ["Leader", "Average", "Leader"],
            "momentum_state": ["Accelerating", "Flat", "Accelerating"],
            "risk_state": ["Low", "High", "Low"],
            "volume_state": ["Accumulation", "Distribution", "Accumulation"],
        }
    )


def test_no_engine_uses_code_defaults() -> None:
    df = _make_test_frame()
    result = compute_investability_gates(df.copy())
    # row 0: all defaults pass
    assert result.loc[0, "is_investable"]
    # row 1: many fail
    assert not result.loc[1, "is_investable"]
    # row 2: market_gate fails (Risk-Off)
    assert not result.loc[2, "is_investable"]


def test_engine_loads_policy_loosened_direction_admits_flat() -> None:
    """If FM loosens direction_gate to also accept 'Flat', a Flat-momentum stock that
    otherwise passes all gates becomes investable."""
    df = pd.DataFrame(
        {
            "regime_state": ["Risk-On"],
            "dislocation_active": [False],
            "sector_state": ["Overweight"],
            "rs_state": ["Leader"],
            "momentum_state": ["Flat"],
            "risk_state": ["Low"],
            "volume_state": ["Accumulation"],
        }
    )
    # mock load_gate_policy to return loosened sets
    with patch("atlas.compute._policy.load_gate_policy") as mock_load:

        def by_key(key: str, engine: object) -> frozenset[str]:
            if key == "direction_gate_stock":
                return frozenset({"Accelerating", "Improving", "Flat"})
            # all others: defaults
            from atlas.compute._policy import DEFAULT_GATE_POLICIES

            return DEFAULT_GATE_POLICIES[key]

        mock_load.side_effect = by_key

        eng = MagicMock()
        result = compute_investability_gates(df.copy(), engine=eng)
        assert result.loc[0, "is_investable"]


def test_engine_loads_policy_strict_strength_excludes_emerging() -> None:
    df = pd.DataFrame(
        {
            "regime_state": ["Risk-On"],
            "dislocation_active": [False],
            "sector_state": ["Overweight"],
            "rs_state": ["Emerging"],
            "momentum_state": ["Accelerating"],
            "risk_state": ["Low"],
            "volume_state": ["Accumulation"],
        }
    )
    with patch("atlas.compute._policy.load_gate_policy") as mock_load:

        def by_key(key: str, engine: object) -> frozenset[str]:
            if key == "strength_gate_stock":
                return frozenset({"Leader", "Strong"})  # Emerging excluded
            from atlas.compute._policy import DEFAULT_GATE_POLICIES

            return DEFAULT_GATE_POLICIES[key]

        mock_load.side_effect = by_key

        eng = MagicMock()
        result = compute_investability_gates(df.copy(), engine=eng)
        assert not result.loc[0, "is_investable"]
