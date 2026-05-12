"""Tests for the per-stock hit-rate primitive."""

from __future__ import annotations

from datetime import date

import pytest

from atlas.intelligence.conviction.monitoring.hit_rate_engine import (
    DEFAULT_LOOKBACK_WINDOW,
    MIN_OBSERVATIONS,
    compute_hit_rates_batch,
)


def test_constants_are_sane() -> None:
    assert DEFAULT_LOOKBACK_WINDOW >= 10
    assert MIN_OBSERVATIONS >= 3


@pytest.mark.integration
def test_batch_returns_list() -> None:
    from atlas.db import get_engine

    eng = get_engine()
    rows = compute_hit_rates_batch(eng, as_of=date(2026, 4, 9))
    assert isinstance(rows, list)


@pytest.mark.integration
def test_hit_rate_values_in_unit_interval_when_present() -> None:
    from atlas.db import get_engine

    eng = get_engine()
    rows = compute_hit_rates_batch(eng, as_of=date(2026, 4, 9))
    for r in rows:
        if r.hit_rate is not None:
            assert 0.0 <= r.hit_rate <= 1.0
            assert r.n_positive_outcomes <= r.n_high_conviction_days


@pytest.mark.integration
def test_low_n_rows_have_null_hit_rate() -> None:
    from atlas.db import get_engine

    eng = get_engine()
    rows = compute_hit_rates_batch(eng, as_of=date(2026, 4, 9))
    for r in rows:
        if r.n_high_conviction_days < MIN_OBSERVATIONS:
            assert r.hit_rate is None
