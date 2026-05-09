# tests/unit/simulation/test_engine.py
"""Unit tests for backtest/engine.py — uses synthetic SignalMatrix, no DB."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from atlas.simulation.core.signal_adapter import SignalMatrix


def _make_synthetic_signal_matrix(n_days: int = 60, n_instruments: int = 3) -> SignalMatrix:
    """3 instruments, 60 trading days, deterministic signals."""
    rng = np.random.default_rng(seed=42)
    dates = pd.date_range(start="2024-01-02", periods=n_days, freq="B")
    prices = 100.0 + np.cumsum(rng.normal(0, 1, (n_days, n_instruments)), axis=0)
    entries = np.zeros((n_days, n_instruments), dtype=bool)
    exits = np.zeros((n_days, n_instruments), dtype=bool)
    # Enter on day 5, exit on day 20 for all instruments
    entries[5, :] = True
    exits[20, :] = True
    return SignalMatrix(
        prices=prices,
        entries=entries,
        exits=exits,
        dates=dates,
        instruments=["INST_A", "INST_B", "INST_C"],
    )


class TestRunBacktest:
    def test_returns_backtest_result_with_required_fields(self):
        from atlas.simulation.backtest.engine import BacktestResult, run_backtest

        sm = _make_synthetic_signal_matrix()
        result = run_backtest(sm, init_cash=1_000_000.0, fees_pct=0.001)

        assert isinstance(result, BacktestResult)
        assert result.sharpe_ratio is not None
        assert result.max_drawdown is not None
        assert result.total_return is not None
        assert isinstance(result.daily_returns, pd.Series)
        assert len(result.daily_returns) > 0

    def test_empty_signal_matrix_returns_zero_result(self):
        from atlas.simulation.backtest.engine import run_backtest

        empty_sm = SignalMatrix(
            prices=np.empty((0, 0)),
            entries=np.empty((0, 0), dtype=bool),
            exits=np.empty((0, 0), dtype=bool),
            dates=pd.DatetimeIndex([]),
            instruments=[],
        )
        result = run_backtest(empty_sm, init_cash=1_000_000.0, fees_pct=0.001)
        assert result.total_return == 0.0
        assert result.sharpe_ratio is None

    def test_result_includes_start_end_dates(self):
        from atlas.simulation.backtest.engine import run_backtest

        sm = _make_synthetic_signal_matrix()
        result = run_backtest(sm, init_cash=1_000_000.0, fees_pct=0.001)

        assert result.start_date == date(2024, 1, 2)
        assert result.end_date is not None
        assert result.end_date >= result.start_date
