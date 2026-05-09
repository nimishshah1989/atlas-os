"""Tests for atlas.simulation.custom.builder._validate_universe_membership.

Multi-asset universe validation: stock / etf / fund branches + mixed lists.
These tests use mocked DB connections — no ATLAS_DB_URL required.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from atlas.simulation.custom.builder import InstrumentWeight, _validate_universe_membership

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> MagicMock:
    return MagicMock()


def _make_instruments(*specs: tuple[str, str]) -> list[InstrumentWeight]:
    """Create InstrumentWeight list from (instrument_id, instrument_type) tuples."""
    return [
        InstrumentWeight(instrument_id=iid, instrument_type=itype, weight_pct=10.0)
        for iid, itype in specs
    ]


def _patch_session(rows_by_call: list[list[tuple]]):
    """Patch open_compute_session to return conn whose execute() returns rows per call.

    rows_by_call[0] = rows for first execute call
                      (stock branch may have 2: MAX(date) + SELECT)
    rows_by_call[N] = rows for Nth execute call.

    Each rows item is a list of 1-tuples (the SELECT returns 1 column).
    """
    conn = MagicMock()
    execute_results = []
    for rows in rows_by_call:
        result = MagicMock()
        if rows and isinstance(rows[0], tuple):
            result.fetchall.return_value = rows
            result.scalar.return_value = rows[0][0] if rows else None
        else:
            result.fetchall.return_value = rows
            result.scalar.return_value = rows[0] if rows else None
        execute_results.append(result)

    conn.execute.side_effect = execute_results

    @contextmanager
    def _cm(_engine):
        yield conn

    return _cm


# ---------------------------------------------------------------------------
# Stock branch
# ---------------------------------------------------------------------------


class TestStockBranch:
    def test_stock_instruments_all_found_passes(self) -> None:
        instruments = _make_instruments(("ABC", "stock"), ("DEF", "stock"))
        # Two execute calls: MAX(date) + SELECT instrument_id WHERE ANY
        session_patch = _patch_session(
            [
                [("2026-05-01",)],  # MAX(date) → ref_date
                [("ABC",), ("DEF",)],  # found instruments
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            _validate_universe_membership(instruments, _make_engine())  # should not raise

    def test_stock_instruments_missing_raises(self) -> None:
        instruments = _make_instruments(("ABC", "stock"), ("MISSING", "stock"))
        session_patch = _patch_session(
            [
                [("2026-05-01",)],  # MAX(date)
                [("ABC",)],  # only ABC found — MISSING not returned
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            with pytest.raises(ValueError, match="stock instruments are not in the Atlas universe"):
                _validate_universe_membership(instruments, _make_engine())

    def test_stock_empty_decisions_table_raises(self) -> None:
        instruments = _make_instruments(("ABC", "stock"))
        session_patch = _patch_session(
            [
                [(None,)],  # MAX(date) returns None
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            with pytest.raises(ValueError, match="atlas_stock_decisions_daily is empty"):
                _validate_universe_membership(instruments, _make_engine())


# ---------------------------------------------------------------------------
# ETF branch
# ---------------------------------------------------------------------------


class TestEtfBranch:
    def test_etf_instruments_all_found_passes(self) -> None:
        instruments = _make_instruments(("NIFTYBEES", "etf"), ("GOLDBEES", "etf"))
        session_patch = _patch_session(
            [
                [("NIFTYBEES",), ("GOLDBEES",)],  # tickers found
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            _validate_universe_membership(instruments, _make_engine())  # should not raise

    def test_etf_instrument_missing_raises(self) -> None:
        instruments = _make_instruments(("NIFTYBEES", "etf"), ("FAKEETF", "etf"))
        session_patch = _patch_session(
            [
                [("NIFTYBEES",)],  # only NIFTYBEES found
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            with pytest.raises(ValueError, match="etf instruments are not in the Atlas universe"):
                _validate_universe_membership(instruments, _make_engine())


# ---------------------------------------------------------------------------
# Fund branch
# ---------------------------------------------------------------------------


class TestFundBranch:
    def test_fund_instruments_all_found_passes(self) -> None:
        instruments = _make_instruments(("F00000ABCD", "fund"), ("F00000EFGH", "fund"))
        session_patch = _patch_session(
            [
                [("F00000ABCD",), ("F00000EFGH",)],  # mstar_ids found
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            _validate_universe_membership(instruments, _make_engine())  # should not raise

    def test_fund_instrument_missing_raises(self) -> None:
        instruments = _make_instruments(("F00000ABCD", "fund"), ("NOTEXIST", "fund"))
        session_patch = _patch_session(
            [
                [("F00000ABCD",)],  # only one found
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            with pytest.raises(ValueError, match="fund instruments are not in the Atlas universe"):
                _validate_universe_membership(instruments, _make_engine())


# ---------------------------------------------------------------------------
# Unknown type
# ---------------------------------------------------------------------------


class TestUnknownInstrumentType:
    def test_unknown_type_raises_value_error(self) -> None:
        instruments = _make_instruments(("X", "crypto"))
        session_patch = _patch_session([])  # no DB calls expected
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            with pytest.raises(ValueError, match="unknown instrument_type: crypto"):
                _validate_universe_membership(instruments, _make_engine())


# ---------------------------------------------------------------------------
# Mixed type list
# ---------------------------------------------------------------------------


class TestMixedTypeList:
    def test_mixed_stock_etf_fund_all_found_passes(self) -> None:
        instruments = _make_instruments(
            ("STOCK1", "stock"),
            ("NIFTYBEES", "etf"),
            ("F00000ABCD", "fund"),
        )
        # Calls: MAX(date), stock SELECT, etf SELECT, fund SELECT
        session_patch = _patch_session(
            [
                [("2026-05-01",)],  # stock: MAX(date)
                [("STOCK1",)],  # stock: instrument_id
                [("NIFTYBEES",)],  # etf: ticker
                [("F00000ABCD",)],  # fund: mstar_id
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            _validate_universe_membership(instruments, _make_engine())  # should not raise

    def test_mixed_type_partial_miss_raises(self) -> None:
        """One missing ETF in a mixed list should still raise."""
        instruments = _make_instruments(
            ("STOCK1", "stock"),
            ("FAKEETF", "etf"),
        )
        session_patch = _patch_session(
            [
                [("2026-05-01",)],  # stock: MAX(date)
                [("STOCK1",)],  # stock: found
                [],  # etf: none found
            ]
        )
        with patch("atlas.simulation.custom.builder.open_compute_session", session_patch):
            with pytest.raises(ValueError, match="etf instruments are not in the Atlas universe"):
                _validate_universe_membership(instruments, _make_engine())
