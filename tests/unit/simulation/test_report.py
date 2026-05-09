# tests/unit/simulation/test_report.py
"""Unit tests for backtest/report.py — mocked DB, no real connection."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from atlas.simulation.backtest.engine import BacktestResult


def _make_result() -> BacktestResult:
    return BacktestResult(
        sharpe_ratio=1.45,
        max_drawdown=-0.12,
        total_return=0.28,
        daily_returns=pd.Series([0.01, -0.005, 0.008]),
        start_date=date(2023, 1, 2),
        end_date=date(2024, 12, 31),
        n_trades=42,
    )


class TestWriteBacktestResult:
    def test_returns_uuid(self):
        from atlas.simulation.backtest.report import write_backtest_result

        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        with patch("atlas.simulation.backtest.report.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result_id = write_backtest_result(
                engine=MagicMock(),
                result=_make_result(),
                backtest_type="custom",
                strategy_id=None,
                custom_portfolio_id=None,
            )

        assert result_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_commit_called(self):
        from atlas.simulation.backtest.report import write_backtest_result

        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = "test-uuid"

        with patch("atlas.simulation.backtest.report.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            write_backtest_result(MagicMock(), _make_result(), "custom")

        mock_conn.commit.assert_called_once()
