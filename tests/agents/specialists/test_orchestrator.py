"""Tests for the SP07 orchestrator (intent classification + invoke_routed)."""

from __future__ import annotations

import pytest

from atlas.agents.specialists import (
    SPECIALISTS,
    classify_specialist,
    get_specialist,
    list_specialists,
)


def test_specialists_registry_has_4_agents() -> None:
    assert set(SPECIALISTS.keys()) == {
        "sector_rotation",
        "stock_screener",
        "regime_watcher",
        "drift_detector",
    }


def test_get_specialist_returns_instance() -> None:
    agent = get_specialist("regime_watcher")
    assert agent.name == "regime_watcher"


def test_get_specialist_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="unknown specialist"):
        get_specialist("totally_made_up")


def test_list_specialists_returns_dicts() -> None:
    out = list_specialists()
    assert len(out) == 4
    for item in out:
        assert "name" in item
        assert "description" in item


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What is the current market regime?", "regime_watcher"),
        ("Are we in Risk-On?", "regime_watcher"),
        ("How is the deployment multiplier?", "regime_watcher"),
        ("Show me the market state today", "regime_watcher"),
        ("Which sectors are rotating?", "sector_rotation"),
        ("RRG quadrants", "sector_rotation"),
        ("Show me leading sectors", "sector_rotation"),
        ("Show me weakening sectors", "sector_rotation"),
        ("Are there any data anomalies?", "drift_detector"),
        ("Recent validator findings", "drift_detector"),
        ("Distribution drift today", "drift_detector"),
        ("Top RS stocks in IT", "stock_screener"),
        ("Best performers", "stock_screener"),
        ("Strongest stocks today", "stock_screener"),
        ("Random thing that matches nothing", "stock_screener"),
    ],
)
def test_classify_specialist_routes_correctly(question: str, expected: str) -> None:
    assert classify_specialist(question) == expected


def test_classify_specialist_is_case_insensitive() -> None:
    assert classify_specialist("WHICH SECTORS ARE ROTATING?") == "sector_rotation"
    assert classify_specialist("Regime?") == "regime_watcher"


def test_specific_match_beats_general() -> None:
    """A query mentioning both 'regime' and 'sector rotation' should route to
    the more specific specialist (sector_rotation) because it appears first
    in the intent table after drift_detector."""
    # 'sector rotation' triggers sector_rotation, which comes before regime
    # in the intent table.
    result = classify_specialist("How does the regime affect sector rotation?")
    assert result == "sector_rotation"


def test_drift_detector_is_first_match() -> None:
    """'anomaly in sectors' must route to drift_detector, not sector_rotation."""
    assert classify_specialist("Any anomaly in sector data?") == "drift_detector"
