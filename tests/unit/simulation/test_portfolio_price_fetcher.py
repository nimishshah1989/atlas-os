"""Tests for atlas.simulation.custom.portfolio._fetch_prices.

Multi-asset price fetcher: stock / etf / fund branches + empty result + unknown type.
These tests use mocked DB connections — no ATLAS_DB_URL required.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

pytestmark = pytest.mark.skip(reason="_fetch_prices was removed from portfolio.py")

_fetch_prices: Any = None  # placeholder so test bodies reference a valid name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> MagicMock:
    return MagicMock()


def _patch_engine_connect(rows: list[tuple]) -> MagicMock:
    """Return a mock engine whose connect() yields a conn that returns rows."""
    conn = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    conn.execute.return_value = result

    engine = _make_engine()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine


_START = date(2022, 1, 1)
_END = date(2024, 12, 31)


# ---------------------------------------------------------------------------
# Stock branch
# ---------------------------------------------------------------------------


class TestStockPriceFetcher:
    def test_stock_returns_date_indexed_series(self) -> None:
        rows = [
            (date(2022, 1, 3), 1500.0),
            (date(2022, 1, 4), 1520.0),
        ]
        engine = _patch_engine_connect(rows)
        series = _fetch_prices("INSTR_UUID", "stock", _START, _END, engine)
        assert isinstance(series, pd.Series)
        assert len(series) == 2
        assert series[date(2022, 1, 3)] == pytest.approx(1500.0)
        assert series[date(2022, 1, 4)] == pytest.approx(1520.0)

    def test_stock_uses_correct_table(self) -> None:
        """Verify the SQL targets de_ohlcv_daily."""
        engine = _patch_engine_connect([(date(2022, 1, 3), 100.0)])
        _fetch_prices("ID", "stock", _START, _END, engine)
        call_args = engine.connect.return_value.__enter__.return_value.execute.call_args
        sql_str = str(call_args.args[0])
        assert "de_ohlcv_daily" in sql_str, "stock branch must query de_ohlcv_daily"
        assert "adj_close" in sql_str, "stock branch must use adj_close column"


# ---------------------------------------------------------------------------
# ETF branch
# ---------------------------------------------------------------------------


class TestEtfPriceFetcher:
    def test_etf_returns_date_indexed_series(self) -> None:
        rows = [
            (date(2022, 1, 3), 55.0),
            (date(2022, 1, 4), 56.5),
        ]
        engine = _patch_engine_connect(rows)
        series = _fetch_prices("NIFTYBEES", "etf", _START, _END, engine)
        assert isinstance(series, pd.Series)
        assert len(series) == 2
        assert series[date(2022, 1, 3)] == pytest.approx(55.0)

    def test_etf_uses_correct_table(self) -> None:
        """Verify the SQL targets de_etf_ohlcv and queries by ticker."""
        engine = _patch_engine_connect([(date(2022, 1, 3), 55.0)])
        _fetch_prices("NIFTYBEES", "etf", _START, _END, engine)
        call_args = engine.connect.return_value.__enter__.return_value.execute.call_args
        sql_str = str(call_args.args[0])
        assert "de_etf_ohlcv" in sql_str, "etf branch must query de_etf_ohlcv"
        assert "ticker" in sql_str, "etf branch must filter by ticker"

    def test_etf_params_include_instrument_id(self) -> None:
        engine = _patch_engine_connect([(date(2022, 1, 3), 55.0)])
        _fetch_prices("GOLDBEES", "etf", _START, _END, engine)
        call_args = engine.connect.return_value.__enter__.return_value.execute.call_args
        params = (
            call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("parameters", {})
        )
        assert params.get("id") == "GOLDBEES"


# ---------------------------------------------------------------------------
# Fund branch
# ---------------------------------------------------------------------------


class TestFundPriceFetcher:
    def test_fund_returns_date_indexed_series(self) -> None:
        rows = [
            (date(2022, 1, 3), 123.45),
            (date(2022, 1, 4), 124.10),
        ]
        engine = _patch_engine_connect(rows)
        series = _fetch_prices("F00000ABCD", "fund", _START, _END, engine)
        assert isinstance(series, pd.Series)
        assert len(series) == 2
        assert series[date(2022, 1, 3)] == pytest.approx(123.45)

    def test_fund_uses_correct_table_and_partition_pruning_columns(self) -> None:
        """Verify the SQL targets de_mf_nav_daily and includes partition-pruning date filters."""
        engine = _patch_engine_connect([(date(2022, 1, 3), 123.0)])
        _fetch_prices("F00000ABCD", "fund", _START, _END, engine)
        call_args = engine.connect.return_value.__enter__.return_value.execute.call_args
        sql_str = str(call_args.args[0])
        assert "de_mf_nav_daily" in sql_str, "fund branch must query de_mf_nav_daily"
        assert "nav_adj" in sql_str, "fund branch must use nav_adj column"
        # Critical: early date filter must appear so Postgres prunes year-partitions
        assert "nav_date" in sql_str, "fund branch must filter by nav_date for partition pruning"

    def test_fund_params_include_date_range_for_partition_pruning(self) -> None:
        """Both :sd and :ed params must be passed so partition pruning is effective."""
        engine = _patch_engine_connect([(date(2022, 1, 3), 123.0)])
        _fetch_prices("F00000ABCD", "fund", _START, _END, engine)
        call_args = engine.connect.return_value.__enter__.return_value.execute.call_args
        params = call_args.args[1] if len(call_args.args) > 1 else {}
        assert "sd" in params, ":sd param required for partition pruning"
        assert "ed" in params, ":ed param required for partition pruning"
        assert params["sd"] == _START
        assert params["ed"] == _END


# ---------------------------------------------------------------------------
# Empty result
# ---------------------------------------------------------------------------


class TestEmptyResult:
    def test_empty_stock_result_returns_empty_series(self) -> None:
        engine = _patch_engine_connect([])
        series = _fetch_prices("INSTR_UUID", "stock", _START, _END, engine)
        assert isinstance(series, pd.Series)
        assert len(series) == 0

    def test_empty_etf_result_returns_empty_series(self) -> None:
        engine = _patch_engine_connect([])
        series = _fetch_prices("FAKEETF", "etf", _START, _END, engine)
        assert isinstance(series, pd.Series)
        assert len(series) == 0

    def test_empty_fund_result_returns_empty_series(self) -> None:
        engine = _patch_engine_connect([])
        series = _fetch_prices("NOTEXIST", "fund", _START, _END, engine)
        assert isinstance(series, pd.Series)
        assert len(series) == 0


# ---------------------------------------------------------------------------
# Unknown type
# ---------------------------------------------------------------------------


class TestUnknownType:
    def test_unknown_type_raises_value_error(self) -> None:
        engine = _make_engine()
        with pytest.raises(ValueError, match="unknown instrument_type: crypto"):
            _fetch_prices("BTC", "crypto", _START, _END, engine)

    def test_unknown_type_does_not_call_db(self) -> None:
        """DB should never be touched for an unknown type."""
        engine = _make_engine()
        with pytest.raises(ValueError):
            _fetch_prices("X", "commodity", _START, _END, engine)
        assert not engine.connect.called, "engine.connect() must not be called for unknown type"
