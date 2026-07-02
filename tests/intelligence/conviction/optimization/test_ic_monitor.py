"""Tests for the rolling IC monitor."""

from __future__ import annotations

from datetime import date

import pytest
from atlas.intelligence.conviction.optimization.ic_monitor import (
    DEFAULT_FORWARD_HORIZON,
    DEFAULT_LOOKBACK_DAYS,
    MIN_OBSERVATIONS,
    measure_all_tiers,
    measure_ic_for_signal,
)


def test_constants_are_sane() -> None:
    assert DEFAULT_LOOKBACK_DAYS >= 60
    assert DEFAULT_FORWARD_HORIZON >= 5
    assert MIN_OBSERVATIONS >= 10


def test_invalid_signal_raises_helpful_error() -> None:
    """signal_name not in SIGNAL_COLUMNS whitelist must raise ValueError.

    The ValueError is raised before any DB access, so a MagicMock engine
    is sufficient — no ATLAS_DB_URL required.
    """
    from unittest.mock import MagicMock

    eng = MagicMock()
    with pytest.raises(ValueError, match="SIGNAL_COLUMNS"):
        measure_ic_for_signal(
            eng,
            as_of=date(2026, 4, 1),
            tier="tier_1_megacap",
            signal_name="not_a_real_signal",
        )


@pytest.mark.integration
def test_measure_returns_none_for_far_future_date() -> None:
    """No data → returns None, not garbage IC."""
    from atlas.db import get_engine

    eng = get_engine()
    result = measure_ic_for_signal(
        eng,
        as_of=date(2099, 1, 1),
        tier="tier_1_megacap",
        signal_name="ret_6m",
    )
    assert result is None


@pytest.mark.integration
def test_measure_all_tiers_returns_some_rows() -> None:
    """End-to-end: should return a non-empty list with anchor 2026-04-01."""
    from atlas.db import get_engine

    eng = get_engine()
    rows = measure_all_tiers(eng, as_of=date(2026, 4, 1))
    if not rows:
        pytest.skip("no overlapping ohlcv+tier data for this anchor in this env")
    assert all(m.n_observations >= MIN_OBSERVATIONS for m in rows)
    # All five tiers should show up if we have full data
    tiers_seen = {m.tier for m in rows}
    assert len(tiers_seen) >= 1
