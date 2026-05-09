# tests/unit/simulation/test_signal_adapter.py
"""Unit tests for signal_adapter.py — parameterization and allowlist guards."""

from __future__ import annotations

import pytest


class TestBuildStockEtfSignalMatrixAllowlist:
    def test_invalid_decisions_table_raises_value_error(self):
        from datetime import date
        from unittest.mock import MagicMock

        from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix

        with pytest.raises(ValueError, match="Invalid decisions_table"):
            build_stock_etf_signal_matrix(
                engine=MagicMock(),
                instrument_ids=["A", "B"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                decisions_table="evil_table; DROP TABLE atlas.strategy_fm_custom_portfolios;--",
            )

    def test_valid_stock_decisions_table_accepted(self):
        from datetime import date
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix

        empty_df = pd.DataFrame(
            columns=["date", "instrument_id", "price", "entry_signal", "exit_signal"]
        )
        with patch("atlas.simulation.core.signal_adapter.open_compute_session") as mock_ctx:
            mock_conn = MagicMock()
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("pandas.read_sql", return_value=empty_df):
                result = build_stock_etf_signal_matrix(
                    engine=MagicMock(),
                    instrument_ids=["A"],
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 12, 31),
                    decisions_table="atlas_stock_decisions_daily",
                )
        assert result.instruments == []

    def test_valid_etf_decisions_table_accepted(self):
        from datetime import date
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from atlas.simulation.core.signal_adapter import build_stock_etf_signal_matrix

        empty_df = pd.DataFrame(
            columns=["date", "instrument_id", "price", "entry_signal", "exit_signal"]
        )
        with patch("pandas.read_sql", return_value=empty_df):
            result = build_stock_etf_signal_matrix(
                engine=MagicMock(),
                instrument_ids=["ETF1"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                decisions_table="atlas_etf_decisions_daily",
            )
        assert result.instruments == []
