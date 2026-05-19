"""Tests for atlas/trading/v6/crisis_sleeve.py.

Unit tests use mock sessions (no DB required).
Integration tests use tmp_db_session — skipped when ATLAS_TEST_DB_URL is unset.
"""

from __future__ import annotations

import math
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from atlas.trading.v6.crisis_sleeve import (
    SleeveAllocation,
    allocate,
    compute_sleeve_pct,
    fetch_etf_12m_return,
    fetch_etf_realized_vol_63d,
)

ATLAS_TEST_DB_URL = os.environ.get("ATLAS_TEST_DB_URL")
REF_DATE = date(2024, 6, 28)

# Patch-path prefix (shortens long E501 lines in context managers)
_MOD = "atlas.trading.v6.crisis_sleeve"
_P12M = f"{_MOD}.fetch_etf_12m_return"
_PVOL = f"{_MOD}.fetch_etf_realized_vol_63d"
_PHIST = f"{_MOD}._has_sufficient_history"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Row:
    """Minimal row mock matching SQLAlchemy row attribute access."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mock_session_returning(value):
    """Session whose execute().fetchone() returns a _Row with a single 'v' attribute."""
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = _Row(v=value) if value is not None else None
    session.execute.return_value = result
    return session


def _mock_session_no_row():
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = None
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# Test 1: compute_sleeve_pct — boundary values
# ---------------------------------------------------------------------------


def test_sleeve_pct_by_regime_score():
    """score=0 → 0.05, score=5 → 0.15. Formula: 0.05 + 0.10 × (score / 5)."""
    assert math.isclose(compute_sleeve_pct(0), 0.05, rel_tol=1e-9)
    assert math.isclose(compute_sleeve_pct(5), 0.15, rel_tol=1e-9)
    assert math.isclose(compute_sleeve_pct(1), 0.07, rel_tol=1e-9)
    assert math.isclose(compute_sleeve_pct(3), 0.11, rel_tol=1e-9)


def test_sleeve_pct_monotonically_increasing():
    """Higher regime score → larger sleeve percentage."""
    pcts = [compute_sleeve_pct(s) for s in range(6)]
    for i in range(len(pcts) - 1):
        assert pcts[i] < pcts[i + 1]


# ---------------------------------------------------------------------------
# Test 2: positive_signals_only — long-only sleeve
# ---------------------------------------------------------------------------


def test_positive_signals_only_long_only():
    """When 12m_ret < 0 for a leg, that leg gets weight 0 (excluded from sleeve)."""
    # Gold: negative 12m return → excluded
    # G-Sec: positive 12m return → included
    # Expected: only G-Sec leg in allocation

    target_vol = 0.08
    gsec_ret = 0.12  # positive
    gsec_vol = 0.04  # 4% realized vol → signal = 0.08/0.04 = 2.0
    gold_ret = -0.05  # negative → excluded

    def _mock_fetch_12m(session, ticker, ref_date):
        if ticker == "GOLDBEES":
            return gold_ret
        if ticker in ("GILT5YBEES", "LIQUIDBEES"):
            return gsec_ret
        if ticker == "SETFGOLD":
            return gold_ret
        return None

    def _mock_fetch_vol(session, ticker, ref_date):
        if ticker in ("GILT5YBEES", "LIQUIDBEES"):
            return gsec_vol
        return 0.06  # gold vol (irrelevant since gold excluded)

    def _mock_hist_check(session, ticker, ref_date):
        return True  # GILT5YBEES has sufficient history

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=2, target_asset_vol=target_vol)

    # Gold leg should be absent (negative return)
    tickers_in = {leg.ticker for leg in result.legs}
    assert "GOLDBEES" not in tickers_in
    assert "SETFGOLD" not in tickers_in
    # G-Sec should be present
    assert len(result.legs) == 1
    assert result.legs[0].ticker in ("GILT5YBEES", "LIQUIDBEES")
    assert result.legs[0].weight_in_sleeve == pytest.approx(1.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Test 3: GILT5YBEES fallback to LIQUIDBEES
# ---------------------------------------------------------------------------


def test_priority_fallback_gilt_to_liquidbees():
    """When GILT5YBEES has insufficient history (< 252d), sleeve uses LIQUIDBEES."""

    def _mock_fetch_12m(session, ticker, ref_date):
        return 0.10  # positive for all

    def _mock_fetch_vol(session, ticker, ref_date):
        return 0.03

    def _mock_hist_check(session, ticker, ref_date):
        # GILT5YBEES has insufficient history
        return ticker != "GILT5YBEES"

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=1, target_asset_vol=0.08)

    tickers_in = {leg.ticker for leg in result.legs}
    assert "GILT5YBEES" not in tickers_in
    assert "LIQUIDBEES" in tickers_in
    assert len(result.legs) == 2  # gold + LIQUIDBEES


# ---------------------------------------------------------------------------
# Test 4: both legs zero → empty allocation (sleeve goes to cash)
# ---------------------------------------------------------------------------


def test_both_legs_zero_returns_empty_allocation():
    """When both gold and G-Sec have 12m_ret ≤ 0, legs is empty."""

    def _mock_fetch_12m(session, ticker, ref_date):
        return -0.05  # negative for all

    def _mock_fetch_vol(session, ticker, ref_date):
        return 0.05

    def _mock_hist_check(session, ticker, ref_date):
        return True

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=3, target_asset_vol=0.08)

    assert result.legs == []
    assert result.ref_date == REF_DATE
    assert math.isclose(result.sleeve_pct_of_book, compute_sleeve_pct(3), rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Test 5: exact zero 12m return is also excluded (sign(0) = 0)
# ---------------------------------------------------------------------------


def test_zero_12m_return_is_excluded():
    """sign(0) = 0 → signal = 0 → leg excluded."""

    def _mock_fetch_12m(session, ticker, ref_date):
        return 0.0  # exactly zero

    def _mock_fetch_vol(session, ticker, ref_date):
        return 0.05

    def _mock_hist_check(session, ticker, ref_date):
        return True

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=0, target_asset_vol=0.08)

    assert result.legs == []


# ---------------------------------------------------------------------------
# Test 6: two positive legs normalize to 1.0
# ---------------------------------------------------------------------------


def test_two_positive_legs_normalize_to_one():
    """sleeve_weight[gold] + sleeve_weight[gsec] == 1.0."""
    target_vol = 0.08
    gold_ret = 0.20
    gold_vol = 0.10  # signal = 0.08/0.10 = 0.8
    gsec_ret = 0.05
    gsec_vol = 0.02  # signal = 0.08/0.02 = 4.0
    # total positive = 0.8 + 4.0 = 4.8
    # expected weights: gold=0.8/4.8≈0.1667, gsec=4.0/4.8≈0.8333

    def _mock_fetch_12m(session, ticker, ref_date):
        if ticker in ("GOLDBEES", "SETFGOLD"):
            return gold_ret
        return gsec_ret

    def _mock_fetch_vol(session, ticker, ref_date):
        if ticker in ("GOLDBEES", "SETFGOLD"):
            return gold_vol
        return gsec_vol

    def _mock_hist_check(session, ticker, ref_date):
        return True

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=2, target_asset_vol=target_vol)

    assert len(result.legs) == 2
    total_weight = sum(leg.weight_in_sleeve for leg in result.legs)
    assert math.isclose(total_weight, 1.0, rel_tol=1e-6)

    # Check individual weights
    gold_leg = next(leg for leg in result.legs if leg.ticker == "GOLDBEES")
    gsec_leg = next(leg for leg in result.legs if leg.ticker == "GILT5YBEES")
    assert math.isclose(gold_leg.weight_in_sleeve, 0.8 / 4.8, rel_tol=1e-6)
    assert math.isclose(gsec_leg.weight_in_sleeve, 4.0 / 4.8, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Test 7: fetch helpers — missing row returns None
# ---------------------------------------------------------------------------


def test_fetch_12m_return_missing_row_returns_none():
    """No row in atlas_etf_metrics_daily → returns None."""
    session = _mock_session_no_row()
    result = fetch_etf_12m_return(session, "GOLDBEES", REF_DATE)
    assert result is None


def test_fetch_12m_return_null_value_returns_none():
    """Row exists but ret_12m is NULL → returns None."""
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = _Row(v=None)
    session.execute.return_value = result_mock
    result = fetch_etf_12m_return(session, "GOLDBEES", REF_DATE)
    assert result is None


def test_fetch_realized_vol_missing_row_returns_none():
    """No row → returns None."""
    session = _mock_session_no_row()
    result = fetch_etf_realized_vol_63d(session, "GOLDBEES", REF_DATE)
    assert result is None


def test_fetch_realized_vol_zero_returns_none():
    """vol = 0.0 → returns None (guards division by zero in signal)."""
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = _Row(v=0.0)
    session.execute.return_value = result_mock
    result = fetch_etf_realized_vol_63d(session, "GOLDBEES", REF_DATE)
    assert result is None


# ---------------------------------------------------------------------------
# Test 8: tsmom_signal values on SleeveLeg
# ---------------------------------------------------------------------------


def test_sleeve_leg_tsmom_signal_correct():
    """signal = sign(ret) × target_vol / realized_vol. Verify stored on leg."""
    target_vol = 0.08
    ret = 0.15  # positive
    vol = 0.04  # signal = +1 × 0.08/0.04 = 2.0

    def _mock_fetch_12m(session, ticker, ref_date):
        return ret

    def _mock_fetch_vol(session, ticker, ref_date):
        return vol

    def _mock_hist_check(session, ticker, ref_date):
        return True

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=0, target_asset_vol=target_vol)

    assert len(result.legs) == 2
    for leg in result.legs:
        assert math.isclose(leg.tsmom_signal, 2.0, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Test 9: missing vol → leg excluded (treated same as zero signal)
# ---------------------------------------------------------------------------


def test_missing_vol_excludes_leg():
    """When realized_vol is None (DB NULL), the leg's signal is 0 → excluded."""

    def _mock_fetch_12m(session, ticker, ref_date):
        return 0.10  # positive return

    def _mock_fetch_vol(session, ticker, ref_date):
        return None  # missing vol → can't compute signal

    def _mock_hist_check(session, ticker, ref_date):
        return True

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=2, target_asset_vol=0.08)

    assert result.legs == []


# ---------------------------------------------------------------------------
# Test 10: SETFGOLD fallback when GOLDBEES has insufficient history
# ---------------------------------------------------------------------------


def test_setfgold_fallback_when_goldbees_insufficient():
    """When GOLDBEES has < 252d history, use SETFGOLD as gold proxy."""

    def _mock_fetch_12m(session, ticker, ref_date):
        return 0.10

    def _mock_fetch_vol(session, ticker, ref_date):
        return 0.05

    def _mock_hist_check(session, ticker, ref_date):
        # GOLDBEES insufficient, SETFGOLD ok
        return ticker != "GOLDBEES"

    session = MagicMock()

    with (
        patch(_P12M, side_effect=_mock_fetch_12m),
        patch(_PVOL, side_effect=_mock_fetch_vol),
        patch(_PHIST, side_effect=_mock_hist_check),
    ):
        result = allocate(session, REF_DATE, regime_score=1, target_asset_vol=0.08)

    tickers_in = {leg.ticker for leg in result.legs}
    assert "GOLDBEES" not in tickers_in
    assert "SETFGOLD" in tickers_in


# ---------------------------------------------------------------------------
# Integration tests — skipped when no DB URL
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ATLAS_TEST_DB_URL, reason="ATLAS_TEST_DB_URL not set")
def test_fetch_etf_12m_return_integration(tmp_db_session):
    """Real DB: GOLDBEES ret_12m is a float or None (not raises)."""
    from sqlalchemy import text

    # Find latest available date for GOLDBEES
    row = tmp_db_session.execute(
        text("SELECT MAX(date) FROM atlas.atlas_etf_metrics_daily WHERE ticker = 'GOLDBEES'")
    ).fetchone()
    if row is None or row[0] is None:
        pytest.skip("No GOLDBEES data in DB")

    latest = row[0]
    val = fetch_etf_12m_return(tmp_db_session, "GOLDBEES", latest)
    assert val is None or isinstance(val, float)


@pytest.mark.skipif(not ATLAS_TEST_DB_URL, reason="ATLAS_TEST_DB_URL not set")
def test_allocate_integration_goldbees(tmp_db_session):
    """Real DB: allocate() on latest date does not raise and returns valid structure."""
    from sqlalchemy import text

    row = tmp_db_session.execute(
        text("SELECT MAX(date) FROM atlas.atlas_etf_metrics_daily WHERE ticker = 'GOLDBEES'")
    ).fetchone()
    if row is None or row[0] is None:
        pytest.skip("No GOLDBEES data in DB")

    latest = row[0]
    result = allocate(tmp_db_session, latest, regime_score=2, target_asset_vol=0.08)

    assert isinstance(result, SleeveAllocation)
    assert 0.05 <= result.sleeve_pct_of_book <= 0.15
    assert isinstance(result.legs, list)

    if result.legs:
        total_weight = sum(leg.weight_in_sleeve for leg in result.legs)
        assert math.isclose(total_weight, 1.0, rel_tol=1e-6)
        for leg in result.legs:
            assert leg.tsmom_signal >= 0.0  # long-only
