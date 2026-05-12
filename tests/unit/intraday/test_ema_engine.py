"""Tests for atlas.intraday.ema_engine."""

from __future__ import annotations

from decimal import Decimal

from atlas.intraday.ema_engine import EMAState, compute_k, update_ema


class TestComputeK:
    def test_compute_k_period_20_returns_correct_value(self) -> None:
        k = compute_k(20)
        expected = Decimal(2) / Decimal(21)
        assert k == expected

    def test_compute_k_period_50_returns_correct_value(self) -> None:
        k = compute_k(50)
        expected = Decimal(2) / Decimal(51)
        assert k == expected

    def test_compute_k_returns_decimal_type(self) -> None:
        k = compute_k(10)
        assert isinstance(k, Decimal)

    def test_compute_k_value_between_zero_and_one(self) -> None:
        for period in [5, 10, 20, 50, 200]:
            k = compute_k(period)
            assert Decimal(0) < k < Decimal(1), f"k={k} out of range for period={period}"

    def test_compute_k_larger_period_gives_smaller_k(self) -> None:
        k20 = compute_k(20)
        k50 = compute_k(50)
        assert k20 > k50


class TestUpdateEMA:
    def test_update_ema_returns_new_ema_state(self) -> None:
        state = EMAState(ema_20=Decimal("100"), ema_50=Decimal("100"))
        new_state = update_ema(Decimal("110"), state)
        assert isinstance(new_state, EMAState)

    def test_update_ema_price_above_ema_increases_ema(self) -> None:
        state = EMAState(ema_20=Decimal("100"), ema_50=Decimal("100"))
        new_state = update_ema(Decimal("110"), state)
        assert new_state.ema_20 > state.ema_20
        assert new_state.ema_50 > state.ema_50

    def test_update_ema_price_below_ema_decreases_ema(self) -> None:
        state = EMAState(ema_20=Decimal("100"), ema_50=Decimal("100"))
        new_state = update_ema(Decimal("90"), state)
        assert new_state.ema_20 < state.ema_20
        assert new_state.ema_50 < state.ema_50

    def test_update_ema_price_equals_ema_unchanged(self) -> None:
        state = EMAState(ema_20=Decimal("100"), ema_50=Decimal("100"))
        new_state = update_ema(Decimal("100"), state)
        assert new_state.ema_20 == state.ema_20
        assert new_state.ema_50 == state.ema_50

    def test_update_ema_uses_decimal_arithmetic_not_float(self) -> None:
        state = EMAState(ema_20=Decimal("100.1234"), ema_50=Decimal("99.8765"))
        new_state = update_ema(Decimal("101.5000"), state)
        assert isinstance(new_state.ema_20, Decimal)
        assert isinstance(new_state.ema_50, Decimal)

    def test_update_ema_ema20_moves_faster_than_ema50(self) -> None:
        """EMA20 has higher k so it moves more per bar than EMA50."""
        state = EMAState(ema_20=Decimal("100"), ema_50=Decimal("100"))
        new_state = update_ema(Decimal("200"), state)
        delta_20 = new_state.ema_20 - state.ema_20
        delta_50 = new_state.ema_50 - state.ema_50
        assert delta_20 > delta_50

    def test_update_ema_formula_matches_manual_calculation(self) -> None:
        """Verify: EMA_new = close*k + EMA_old*(1-k)."""
        close = Decimal("105")
        ema_20_old = Decimal("100")
        k20 = Decimal(2) / Decimal(21)
        expected_ema20 = close * k20 + ema_20_old * (Decimal(1) - k20)

        state = EMAState(ema_20=ema_20_old, ema_50=Decimal("100"))
        new_state = update_ema(close, state)
        assert new_state.ema_20 == expected_ema20

    def test_update_ema_does_not_mutate_original_state(self) -> None:
        state = EMAState(ema_20=Decimal("100"), ema_50=Decimal("100"))
        _ = update_ema(Decimal("150"), state)
        # NamedTuple is immutable; original state unchanged
        assert state.ema_20 == Decimal("100")
        assert state.ema_50 == Decimal("100")
