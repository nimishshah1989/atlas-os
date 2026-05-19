"""Tests for atlas/trading/v6/regime.py.

Unit tests only — mock the session. Integration tests would need real DB.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from atlas.trading.v6.regime import (
    _SCORE_TO_LEVEL,
    _SCORE_TO_MULTIPLIER,
    RegimeState,
    compute_regime,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Row:
    """Simple row mock."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mock_session_with_row(**kwargs):
    """Return a mock session whose execute().fetchone() yields a row with kwargs."""
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = _Row(**kwargs)
    session.execute.return_value = result
    return session


def _mock_session_no_row():
    """Return a mock session with no row (fetchone returns None)."""
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = None
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# Score table constants
# ---------------------------------------------------------------------------


def test_multiplier_table_covers_0_to_5():
    """Every score 0..5 has a gross multiplier."""
    for score in range(6):
        assert score in _SCORE_TO_MULTIPLIER
        assert 0 < _SCORE_TO_MULTIPLIER[score] <= 1.10


def test_level_table_covers_0_to_5():
    """Every score 0..5 has a level label."""
    expected = {"calm", "normal", "yellow", "orange", "red", "crash"}
    assert set(_SCORE_TO_LEVEL.values()) == expected


def test_multipliers_monotonically_decrease():
    """Higher score (more bearish) → lower multiplier."""
    for score in range(5):
        assert _SCORE_TO_MULTIPLIER[score] > _SCORE_TO_MULTIPLIER[score + 1]


# ---------------------------------------------------------------------------
# compute_regime — no row raises ValueError
# ---------------------------------------------------------------------------


def test_compute_regime_no_row_raises():
    """No row for ref_date raises ValueError — regime is required."""
    session = _mock_session_no_row()
    with pytest.raises(ValueError, match="No atlas_market_regime_daily row"):
        compute_regime(session, date(2026, 1, 15))


# ---------------------------------------------------------------------------
# compute_regime — all calm (score 0)
# ---------------------------------------------------------------------------


def test_compute_regime_all_calm_score_0():
    """All signals non-firing → score = 0, level = 'calm', mult = 1.10."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))

    assert isinstance(result, RegimeState)
    assert result.score == 0
    assert result.level == "calm"
    assert result.gross_multiplier == 1.10
    assert len(result.signals) == 5
    assert all(not s["firing"] for s in result.signals)


# ---------------------------------------------------------------------------
# compute_regime — each individual signal
# ---------------------------------------------------------------------------


def test_compute_regime_nifty_below_ema200_fires():
    """nifty500_above_ema_200 = False → score includes 1 bearish signal."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=False,  # FIRING
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 1
    nifty_signal = next(s for s in result.signals if s["name"] == "nifty500_trend")
    assert nifty_signal["firing"] is True


def test_compute_regime_breadth_below_30pct_fires():
    """pct_above_ema_200 < 0.30 → breadth signal fires."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.25,  # FIRING
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 1
    breadth_signal = next(s for s in result.signals if s["name"] == "breadth")
    assert breadth_signal["firing"] is True


def test_compute_regime_breadth_exactly_30pct_not_fires():
    """pct_above_ema_200 = 0.30 (at threshold, not below) → not firing."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.30,  # AT threshold — not < 0.30
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    breadth_signal = next(s for s in result.signals if s["name"] == "breadth")
    assert breadth_signal["firing"] is False


def test_compute_regime_vix_above_22_fires():
    """india_vix > 22 → VIX signal fires."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=23.5,  # FIRING
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 1
    vix_signal = next(s for s in result.signals if s["name"] == "india_vix")
    assert vix_signal["firing"] is True


def test_compute_regime_vix_exactly_22_not_fires():
    """india_vix = 22.0 (not > 22) → VIX signal not firing."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=22.0,  # AT threshold — not > 22
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    vix_signal = next(s for s in result.signals if s["name"] == "india_vix")
    assert vix_signal["firing"] is False


def test_compute_regime_ad_ratio_below_040_fires():
    """ad_ratio < 0.40 → A/D signal fires."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=0.35,  # FIRING
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 1
    ad_signal = next(s for s in result.signals if s["name"] == "ad_ratio")
    assert ad_signal["firing"] is True


def test_compute_regime_dislocation_true_fires():
    """dislocation_active = True → dislocation signal fires."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=True,  # FIRING
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 1
    dis_signal = next(s for s in result.signals if s["name"] == "dislocation")
    assert dis_signal["firing"] is True


# ---------------------------------------------------------------------------
# compute_regime — crash scenario (all 5 signals fire)
# ---------------------------------------------------------------------------


def test_compute_regime_all_signals_fire_score_5():
    """All 5 signals fire → score = 5, level = 'crash', mult = 0.20."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=False,
        pct_above_ema_200=0.10,
        india_vix=35.0,
        ad_ratio=0.15,
        dislocation_active=True,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 5
    assert result.level == "crash"
    assert result.gross_multiplier == 0.20
    assert all(s["firing"] for s in result.signals)


# ---------------------------------------------------------------------------
# compute_regime — NULL handling (fail-open)
# ---------------------------------------------------------------------------


def test_compute_regime_all_nulls_score_0():
    """All fields NULL → all signals fail-open → score = 0, calm."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=None,
        pct_above_ema_200=None,
        india_vix=None,
        ad_ratio=None,
        dislocation_active=None,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 0
    assert result.level == "calm"
    assert all(not s["firing"] for s in result.signals)


def test_compute_regime_partial_nulls_count_only_non_null():
    """3 NULL signals, 2 firing → score = 2."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=None,  # silent
        pct_above_ema_200=None,  # silent
        india_vix=30.0,  # FIRING (> 22)
        ad_ratio=0.20,  # FIRING (< 0.40)
        dislocation_active=None,  # silent
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert result.score == 2
    assert result.level == "yellow"


# ---------------------------------------------------------------------------
# compute_regime — returned dataclass shape
# ---------------------------------------------------------------------------


def test_compute_regime_returns_frozen_dataclass():
    """RegimeState is immutable (frozen dataclass)."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    with pytest.raises((AttributeError, TypeError)):
        result.score = 99  # type: ignore[misc]


def test_compute_regime_signals_list_has_5_items():
    """Signals list always has exactly 5 items."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    assert len(result.signals) == 5


def test_compute_regime_signal_dict_has_required_keys():
    """Each signal dict has name, firing, reading keys."""
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, date(2026, 1, 15))
    for signal in result.signals:
        assert "name" in signal
        assert "firing" in signal
        assert "reading" in signal


def test_compute_regime_date_preserved():
    """RegimeState.date matches the input ref_date."""
    ref_date = date(2025, 12, 31)
    session = _mock_session_with_row(
        nifty500_above_ema_200=True,
        pct_above_ema_200=0.60,
        india_vix=15.0,
        ad_ratio=1.20,
        dislocation_active=False,
    )
    result = compute_regime(session, ref_date)
    assert result.date == ref_date
