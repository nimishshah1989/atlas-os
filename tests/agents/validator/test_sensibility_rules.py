"""Tests for atlas.agents.validator.sensibility_rules.

Each test covers a distinct constraint category. Tests are pure (no I/O).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from atlas.agents.validator.sensibility_rules import check_value

# ---- helpers ---------------------------------------------------------------


def _today() -> date:
    return date.today()


# ---- inf / NaN detection ---------------------------------------------------


@pytest.mark.unit
def test_float_inf_returns_violation() -> None:
    v = check_value("ema_50", float("inf"), "atlas_stock_metrics_daily")
    assert v is not None
    assert "inf" in v.rule.lower() or "finite" in v.rule.lower()


@pytest.mark.unit
def test_float_neg_inf_returns_violation() -> None:
    v = check_value("ema_50", float("-inf"), "atlas_stock_metrics_daily")
    assert v is not None


@pytest.mark.unit
def test_float_nan_returns_violation() -> None:
    v = check_value("rs_3m", float("nan"), "atlas_stock_metrics_daily")
    assert v is not None
    assert "nan" in v.rule.lower() or "finite" in v.rule.lower()


@pytest.mark.unit
def test_decimal_inf_returns_violation() -> None:
    v = check_value("ema_10", Decimal("Infinity"), "atlas_stock_metrics_daily")
    assert v is not None


@pytest.mark.unit
def test_decimal_nan_returns_violation() -> None:
    v = check_value("rs_pct", Decimal("NaN"), "atlas_stock_metrics_daily")
    assert v is not None


# ---- future date -----------------------------------------------------------


@pytest.mark.unit
def test_future_date_returns_violation() -> None:
    future = _today() + timedelta(days=1)
    v = check_value("date", future, "atlas_stock_metrics_daily")
    assert v is not None
    assert "future" in v.message.lower() or "today" in v.message.lower()


@pytest.mark.unit
def test_today_date_is_valid() -> None:
    v = check_value("date", _today(), "atlas_stock_metrics_daily")
    assert v is None


@pytest.mark.unit
def test_past_date_is_valid() -> None:
    v = check_value("date", date(2024, 1, 1), "atlas_stock_metrics_daily")
    assert v is None


# ---- percentile ------------------------------------------------------------


@pytest.mark.unit
def test_percentile_above_one_returns_violation() -> None:
    v = check_value("rs_percentile", 1.5, "atlas_stock_metrics_daily")
    assert v is not None
    assert "percentile" in v.rule.lower()


@pytest.mark.unit
def test_percentile_below_zero_returns_violation() -> None:
    v = check_value("rs_percentile", -0.1, "atlas_stock_metrics_daily")
    assert v is not None


@pytest.mark.unit
def test_percentile_boundary_zero_is_valid() -> None:
    assert check_value("rs_percentile", 0.0, "atlas_stock_metrics_daily") is None


@pytest.mark.unit
def test_percentile_boundary_one_is_valid() -> None:
    assert check_value("rs_percentile", 1.0, "atlas_stock_metrics_daily") is None


# ---- volume ----------------------------------------------------------------


@pytest.mark.unit
def test_negative_volume_returns_violation() -> None:
    v = check_value("volume", -1, "atlas_stock_metrics_daily")
    assert v is not None
    assert "volume" in v.rule.lower()


@pytest.mark.unit
def test_volume_above_cap_returns_violation() -> None:
    v = check_value("volume", 2e12, "atlas_stock_metrics_daily")
    assert v is not None


@pytest.mark.unit
def test_zero_volume_is_valid() -> None:
    assert check_value("volume", 0, "atlas_stock_metrics_daily") is None


@pytest.mark.unit
def test_normal_volume_is_valid() -> None:
    assert check_value("volume", 1_000_000, "atlas_stock_metrics_daily") is None


# ---- aum -------------------------------------------------------------------


@pytest.mark.unit
def test_negative_aum_returns_violation() -> None:
    v = check_value("aum_cr", -100.0, "atlas_fund_lens_daily")
    assert v is not None
    assert "aum" in v.rule.lower()


@pytest.mark.unit
def test_zero_aum_is_valid() -> None:
    assert check_value("aum_cr", 0.0, "atlas_fund_lens_daily") is None


# ---- unknown column / None -------------------------------------------------


@pytest.mark.unit
def test_unknown_column_returns_none() -> None:
    """Unknown column names must never produce false positives."""
    assert check_value("some_random_col", 42.0, "any_table") is None


@pytest.mark.unit
def test_null_value_returns_none() -> None:
    """NULL values are DB-level concerns; sensibility rules skip them."""
    assert check_value("rs_percentile", None, "atlas_stock_metrics_daily") is None


# ---- valid numeric value returns None --------------------------------------


@pytest.mark.unit
def test_valid_numeric_returns_none() -> None:
    assert check_value("ema_50", 1250.75, "atlas_stock_metrics_daily") is None


@pytest.mark.unit
def test_valid_percentile_mid_range_returns_none() -> None:
    assert check_value("rs_percentile", 0.65, "atlas_stock_metrics_daily") is None


# ---- math.nan / math.inf aliases ------------------------------------------


@pytest.mark.unit
def test_math_inf_detected() -> None:
    assert check_value("close_approx", math.inf, "atlas_stock_metrics_daily") is not None


@pytest.mark.unit
def test_math_nan_detected() -> None:
    assert check_value("close_approx", math.nan, "atlas_stock_metrics_daily") is not None
