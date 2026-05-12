"""Tests for the live IC tracker."""

from __future__ import annotations

from datetime import date

import pytest

from atlas.intelligence.conviction.monitoring.live_ic_tracker import (
    DEFAULT_FORWARD_HORIZON,
    DEFAULT_LOOKBACK_DAYS,
    MIN_OBSERVATIONS,
    measure_all_active_versions,
)


def test_constants_are_sane() -> None:
    assert DEFAULT_LOOKBACK_DAYS >= 60
    assert DEFAULT_FORWARD_HORIZON >= 5
    assert MIN_OBSERVATIONS >= 10


@pytest.mark.integration
def test_measure_returns_empty_for_far_future() -> None:
    from atlas.db import get_engine

    eng = get_engine()
    rows = measure_all_active_versions(eng, as_of=date(2099, 1, 1))
    assert rows == []


@pytest.mark.integration
def test_measure_returns_list_for_real_anchor() -> None:
    from atlas.db import get_engine

    eng = get_engine()
    rows = measure_all_active_versions(eng, as_of=date(2026, 4, 9))
    # Stage 4a active sets exist on this anchor; some may not produce
    # measurements if forward-return data is incomplete. The contract is
    # just "list of LiveICMeasurement, no crash."
    assert isinstance(rows, list)
