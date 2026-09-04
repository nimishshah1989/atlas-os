"""StooqBulkProvider and the importer's pure pieces, proven on the FM's REAL archive.

Set ``STOOQ_ARCHIVE=/path/to/d_us_txt.zip`` (Stooq's daily US bulk download). Every expected
value below is read from the archive itself — the SPY member is re-read here with the stdlib
so the provider's output is checked against an independent parse (rule #0: no fixture).
Unset, the module skips; it never passes vacuously.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from datetime import date
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.providers.base import BAR_COLUMNS, PriceProvider
from atlas.global_market.providers.stooq_bulk import (
    ADJUSTMENT_UNKNOWN,
    ArchiveMember,
    StooqBulkProvider,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts" / "global_market"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import import_stooq  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.integration

ARCHIVE = os.environ.get("STOOQ_ARCHIVE", "")
if not ARCHIVE or not Path(ARCHIVE).is_file():
    pytest.skip(
        "STOOQ_ARCHIVE is not a file — the archive tests need the real zip", allow_module_level=True
    )

WIDE_OPEN = (date(1900, 1, 1), date(2100, 1, 1))
NOT_A_MEMBER = "ATLASNOSUCHTICKER"


@pytest.fixture(scope="module")
def provider() -> StooqBulkProvider:
    return StooqBulkProvider(ARCHIVE)


@pytest.fixture(scope="module")
def spy(provider: StooqBulkProvider) -> pd.DataFrame:
    return provider.bars(["SPY"], *WIDE_OPEN, adjustment=ADJUSTMENT_UNKNOWN)


@pytest.fixture(scope="module")
def spy_file_rows() -> list[list[str]]:
    """The SPY member's data rows, parsed independently of the provider."""
    with zipfile.ZipFile(ARCHIVE) as zf:
        name = next(n for n in zf.namelist() if n.endswith("/spy.us.txt"))
        with zf.open(name) as fh:
            rows = list(csv.reader(io.TextIOWrapper(fh, encoding="ascii", newline="")))
    assert rows[0][0] == "<TICKER>"
    return [r for r in rows[1:] if r[1] == "D"]


def _ymd(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


# ── provider ──


def test_provider_satisfies_the_price_protocol(provider: StooqBulkProvider) -> None:
    # Structural conformance is checked by pyright on this assignment (a Protocol without
    # @runtime_checkable has no isinstance); the runtime assertion is the contract's surface.
    as_protocol: PriceProvider = provider
    assert as_protocol.name == "stooq_bulk"
    assert callable(as_protocol.bars)


def test_list_symbols_covers_the_archive_with_both_kinds(provider: StooqBulkProvider) -> None:
    syms = provider.list_symbols()
    assert len(syms) > 10_000
    assert {kind for _, kind, _ in syms} == {"stock", "etf"}
    exchanges = {ex for _, _, ex in syms}
    assert exchanges <= {"NASDAQ", "NYSE", "NYSEMKT"} and len(exchanges) >= 2
    assert len({s for s, _, _ in syms}) == len(syms), "a symbol maps to two members"
    assert ("SPY", "etf", "NYSE") in syms
    assert ("AAPL", "stock", "NASDAQ") in syms
    assert ("BRK.B", "stock", "NYSE") in syms  # brk-b.us.txt → the directory spelling
    assert NOT_A_MEMBER not in {s for s, _, _ in syms}


def test_spy_bars_are_exactly_the_file_rows(
    spy: pd.DataFrame, spy_file_rows: list[list[str]]
) -> None:
    assert list(spy.columns) == list(BAR_COLUMNS)
    assert len(spy) >= 5000
    assert len(spy) == len(spy_file_rows)
    assert (spy["symbol"] == "SPY").all()
    dates = spy["date"].tolist()
    assert all(b > a for a, b in pairwise(dates)), "dates not strictly increasing"
    assert dates[0] == _ymd(spy_file_rows[0][2])
    assert dates[-1] == _ymd(spy_file_rows[-1][2])
    assert all(h >= lo for h, lo in zip(spy["high"].tolist(), spy["low"].tolist(), strict=True))
    assert all(c > 0 for c in spy["close"].tolist())
    assert pd.api.types.is_integer_dtype(spy["volume"])
    assert set(spy["trade_count"].tolist()) == {None} and set(spy["vwap"].tolist()) == {None}


def test_prices_are_exact_decimals_of_the_file_text(
    spy: pd.DataFrame, spy_file_rows: list[list[str]]
) -> None:
    """No float round-trip: the Decimal is the file's own digits (money is Decimal)."""
    first = spy.iloc[0]
    assert isinstance(first["close"], Decimal)
    assert first["open"] == Decimal(spy_file_rows[0][4])
    assert first["close"] == Decimal(spy_file_rows[0][7])
    assert int(first["volume"]) == int(spy_file_rows[0][8])


def test_bars_window_is_inclusive_on_both_ends(
    provider: StooqBulkProvider, spy_file_rows: list[list[str]]
) -> None:
    start, end = date(2026, 1, 2), date(2026, 1, 30)
    sub = provider.bars(["SPY"], start, end, adjustment=ADJUSTMENT_UNKNOWN)
    expected = [r for r in spy_file_rows if start <= _ymd(r[2]) <= end]
    assert len(sub) == len(expected) > 0
    assert sub["date"].iloc[0] == _ymd(expected[0][2])
    assert sub["date"].iloc[-1] == _ymd(expected[-1][2])


def test_bars_reads_several_members_in_one_call(provider: StooqBulkProvider) -> None:
    both = provider.bars(
        ["AAPL", "SPY"], date(2026, 8, 1), date(2026, 8, 31), adjustment=ADJUSTMENT_UNKNOWN
    )
    assert set(both["symbol"]) == {"AAPL", "SPY"}
    assert both.equals(both.sort_values(["symbol", "date"], ignore_index=True))


def test_bars_for_a_symbol_not_in_the_archive_is_empty_with_the_contract_columns(
    provider: StooqBulkProvider,
) -> None:
    out = provider.bars([NOT_A_MEMBER], *WIDE_OPEN, adjustment=ADJUSTMENT_UNKNOWN)
    assert out.empty
    assert list(out.columns) == list(BAR_COLUMNS)


@pytest.mark.parametrize("adjustment", ["all", "split", "raw", "", "UNKNOWN"])
def test_only_the_unknown_adjustment_is_accepted(
    provider: StooqBulkProvider, adjustment: str
) -> None:
    with pytest.raises(ValueError, match="unknown"):
        provider.bars(["SPY"], *WIDE_OPEN, adjustment=adjustment)


def test_members_carry_the_zip_fingerprint(provider: StooqBulkProvider) -> None:
    members = provider.members()
    by_symbol = {m.symbol: m for m in members}
    spy = by_symbol["SPY"]
    assert isinstance(spy, ArchiveMember)
    assert spy.stooq_ticker == "SPY.US" and spy.kind == "etf" and spy.exchange == "NYSE"
    with zipfile.ZipFile(ARCHIVE) as zf:
        info = zf.getinfo(spy.name)
    assert (spy.size, spy.crc) == (info.file_size, info.CRC)
    assert spy.size > 0
    assert any(m.size == 0 for m in members), (
        "the archive's zero-byte members must be listed, not hidden"
    )


# ── importer: the pure pieces (identity mapping + resume), no DB ──


def test_every_member_is_reported_when_identity_is_empty(provider: StooqBulkProvider) -> None:
    """Nothing is dropped silently: with no instrument_master rows at all, every member
    lands in the unmapped report with a reason."""
    members = provider.members()
    mapped, unmapped = import_stooq.map_members(members, by_alias={}, by_symbol={})
    assert mapped == []
    assert len(unmapped) == len(members)
    assert {u.reason for u in unmapped} == {import_stooq.REASON_NO_IDENTITY}


def test_resume_state_round_trips_through_the_member_fingerprint(
    provider: StooqBulkProvider,
) -> None:
    spy = next(m for m in provider.members() if m.symbol == "SPY")
    full = import_stooq.state_value(
        spy,
        since=None,
        rows_sent=5,
        rows_written=5,
        first_date=date(2005, 2, 25),
        last_date=date(2026, 9, 3),
    )
    assert import_stooq.should_skip(spy, full, since=None)
    assert import_stooq.should_skip(
        spy, full, since=date(2020, 1, 1)
    )  # a full import covers any --since
    partial = import_stooq.state_value(
        spy,
        since=date(2020, 1, 1),
        rows_sent=1,
        rows_written=1,
        first_date=date(2020, 1, 2),
        last_date=date(2026, 9, 3),
    )
    assert not import_stooq.should_skip(spy, partial, since=None)  # needs the older rows
    assert import_stooq.should_skip(spy, partial, since=date(2021, 1, 1))
    changed = dict(full, crc=full["crc"] + 1)
    assert not import_stooq.should_skip(spy, changed, since=None)  # a different file re-imports
    assert not import_stooq.should_skip(spy, None, since=None)
