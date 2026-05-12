"""Tests for atlas.intraday.rs_engine."""

from __future__ import annotations

from decimal import Decimal

from atlas.intraday.rs_engine import (
    NIFTY50_TOKEN,
    compute_return_since_open,
    compute_rs,
)


class TestNifty50Token:
    def test_nifty50_token_is_correct_constant(self) -> None:
        assert NIFTY50_TOKEN == 256265

    def test_nifty50_token_is_int(self) -> None:
        assert isinstance(NIFTY50_TOKEN, int)


class TestComputeReturnSinceOpen:
    def test_positive_return_calculation(self) -> None:
        result = compute_return_since_open(Decimal("105"), Decimal("100"))
        assert result == Decimal("0.05")

    def test_negative_return_calculation(self) -> None:
        result = compute_return_since_open(Decimal("95"), Decimal("100"))
        assert result == Decimal("-0.05")

    def test_zero_return_when_price_unchanged(self) -> None:
        result = compute_return_since_open(Decimal("100"), Decimal("100"))
        assert result == Decimal("0")

    def test_zero_open_price_returns_none(self) -> None:
        """Zero open must return None, not ZeroDivisionError or Inf."""
        result = compute_return_since_open(Decimal("100"), Decimal("0"))
        assert result is None

    def test_none_current_price_returns_none(self) -> None:
        result = compute_return_since_open(None, Decimal("100"))
        assert result is None

    def test_none_open_price_returns_none(self) -> None:
        result = compute_return_since_open(Decimal("100"), None)
        assert result is None

    def test_both_none_returns_none(self) -> None:
        result = compute_return_since_open(None, None)
        assert result is None

    def test_result_is_decimal_type(self) -> None:
        result = compute_return_since_open(Decimal("110"), Decimal("100"))
        assert isinstance(result, Decimal)

    def test_large_price_values_decimal_precision(self) -> None:
        """Verify no float precision loss on large NSE prices."""
        result = compute_return_since_open(Decimal("23456.78"), Decimal("23000.00"))
        assert result is not None
        # (23456.78 - 23000) / 23000 ≈ 0.01986...
        assert abs(result - Decimal("23456.78") / Decimal("23000.00") + 1) < Decimal("0.0001")


class TestComputeRS:
    def test_positive_rs_when_stock_outperforms(self) -> None:
        stock_return = Decimal("0.05")
        nifty_return = Decimal("0.02")
        result = compute_rs(stock_return, nifty_return)
        assert result is not None
        assert result == Decimal("0.05") / Decimal("0.02")

    def test_negative_rs_when_stock_underperforms(self) -> None:
        stock_return = Decimal("0.01")
        nifty_return = Decimal("0.05")
        result = compute_rs(stock_return, nifty_return)
        assert result is not None
        assert result < Decimal("1")

    def test_zero_nifty_return_returns_none(self) -> None:
        """Critical: zero denominator must produce None, not ZeroDivisionError."""
        result = compute_rs(Decimal("0.03"), Decimal("0"))
        assert result is None

    def test_none_stock_return_returns_none(self) -> None:
        result = compute_rs(None, Decimal("0.02"))
        assert result is None

    def test_none_nifty_return_returns_none(self) -> None:
        result = compute_rs(Decimal("0.03"), None)
        assert result is None

    def test_both_none_returns_none(self) -> None:
        result = compute_rs(None, None)
        assert result is None

    def test_result_is_decimal_type_when_valid(self) -> None:
        result = compute_rs(Decimal("0.04"), Decimal("0.02"))
        assert isinstance(result, Decimal)

    def test_equal_returns_give_rs_of_one(self) -> None:
        result = compute_rs(Decimal("0.03"), Decimal("0.03"))
        assert result == Decimal("1")

    def test_negative_stock_negative_nifty_both_down(self) -> None:
        """Both falling: stock falls more → RS < 1."""
        result = compute_rs(Decimal("-0.04"), Decimal("-0.02"))
        assert result is not None
        assert result == Decimal("2")  # -0.04 / -0.02 = 2 (ratio, not absolute RS)
