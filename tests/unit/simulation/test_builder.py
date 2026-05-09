# tests/unit/simulation/test_builder.py
"""Unit tests for custom/builder.py — validation rules, no DB required for most tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atlas.simulation.custom.builder import InstrumentWeight, validate_custom_portfolio


def _instruments(n: int, weight: float | None = None) -> list[InstrumentWeight]:
    per = weight if weight is not None else round(100.0 / n, 4)
    return [
        InstrumentWeight(instrument_id=f"INS_{i:03d}", instrument_type="stock", weight_pct=per)
        for i in range(n)
    ]


class TestValidateCustomPortfolio:
    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            validate_custom_portfolio([], engine=MagicMock())

    def test_over_30_instruments_raises(self):
        insts = _instruments(31)
        with pytest.raises(ValueError, match="30"):
            validate_custom_portfolio(insts, engine=MagicMock())

    def test_weights_not_summing_to_100_raises(self):
        insts = [
            InstrumentWeight("A", "stock", 60.0),
            InstrumentWeight("B", "stock", 30.0),
        ]
        with pytest.raises(ValueError, match="sum to 100"):
            validate_custom_portfolio(insts, engine=MagicMock())

    def test_duplicate_instrument_ids_raises(self):
        insts = [
            InstrumentWeight("AAPL", "stock", 50.0),
            InstrumentWeight("AAPL", "stock", 50.0),
        ]
        with pytest.raises(ValueError, match="duplicate"):
            validate_custom_portfolio(insts, engine=MagicMock())

    def test_non_investable_instrument_raises(self):
        insts = [
            InstrumentWeight("INS_000", "stock", 50.0),
            InstrumentWeight("INS_001", "stock", 50.0),
        ]
        mock_conn = MagicMock()
        # DB returns only 1 investable instrument out of 2 requested
        mock_conn.execute.return_value.fetchall.return_value = [("INS_000",)]

        with patch("atlas.simulation.custom.builder.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(ValueError, match="not in Atlas universe"):
                validate_custom_portfolio(insts, engine=MagicMock())

    def test_valid_portfolio_passes(self):
        insts = [
            InstrumentWeight("A", "stock", 40.0),
            InstrumentWeight("B", "stock", 35.0),
            InstrumentWeight("C", "stock", 25.0),
        ]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("A",), ("B",), ("C",)]

        with patch("atlas.simulation.custom.builder.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            validate_custom_portfolio(insts, engine=MagicMock())  # must not raise

    def test_empty_decisions_table_raises(self):
        insts = [InstrumentWeight("A", "stock", 100.0)]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = None  # no MAX(date)

        with patch("atlas.simulation.custom.builder.open_compute_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda _: mock_conn
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(ValueError, match="atlas_stock_decisions_daily is empty"):
                validate_custom_portfolio(insts, engine=MagicMock())
