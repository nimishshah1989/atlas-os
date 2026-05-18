"""Tests for atlas/intelligence/aggregations/base.py."""

from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.base import (
    AggregateState,
    weighted_state_distribution,
)


def test_weighted_state_distribution_handles_simple_cap_weighting() -> None:
    df = pd.DataFrame(
        {
            "instrument_id": ["a", "b", "c"],
            "state": ["stage_2a", "stage_2a", "stage_4"],
            "weight": [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
        }
    )
    dist = weighted_state_distribution(df)
    assert dist["stage_2a"] == pytest.approx(0.8)
    assert dist["stage_4"] == pytest.approx(0.2)


def test_weighted_state_distribution_zero_weight_returns_empty() -> None:
    df = pd.DataFrame(
        {
            "instrument_id": ["a"],
            "state": ["stage_2a"],
            "weight": [Decimal("0")],
        }
    )
    dist = weighted_state_distribution(df)
    assert dist == {}


def test_aggregate_state_dominant_state() -> None:
    dist = {"stage_2a": 0.45, "stage_2b": 0.35, "stage_3": 0.20}
    agg = AggregateState.from_distribution(dist)
    assert agg.dominant_state == "stage_2a"
    assert agg.dominant_share == pytest.approx(0.45)
    assert agg.is_mixed is True  # no state > 0.50
