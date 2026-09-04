"""Symbol-string normalisation (pure) and the directory parsers (real files only).

Ticker strings are not market data: ``SPY.US → SPY`` is a spelling rule, so those tests are
plain unit tests. The two parsers are tested ONLY against the real Nasdaq Trader and SEC
files (rule #0 — no fabricated fixture). By default that is the dated verbatim snapshot in
``tests/fixtures/global/symbology/`` (provenance and hashes in its ``SOURCE.md``), so CI
exercises the parsers on real records; ``SYMBOLOGY_DIR=<dir>`` points the same tests at
fresher downloads of ``nasdaqlisted.txt``, ``otherlisted.txt`` and ``company_tickers.json``.
If the directory lacks any of the three, those tests skip — they never pass vacuously.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.providers.symbology import (
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers,
    stooq_symbol,
)

# ── stooq_symbol: pure spelling rules ──


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("SPY.US", "SPY"),
        ("spy.us", "SPY"),  # archive file stems are lower-case
        ("BRK-B.US", "BRK.B"),  # Stooq's class-share marker is "-", the directory's is "."
        ("brk-b", "BRK.B"),  # a bare stem (no market suffix) is accepted too
        ("aapl", "AAPL"),
        (" qqq.us\n", "QQQ"),
        ("AAC-U.US", "AAC.U"),  # units: otherlisted.txt ACT symbol is AAC.U
    ],
)
def test_stooq_symbol_normalises_spelling(ticker: str, expected: str) -> None:
    assert stooq_symbol(ticker) == expected


@pytest.mark.unit
def test_stooq_symbol_leaves_the_preferred_marker_alone() -> None:
    """Stooq spells preferred series with "_" (``agm_d.us.txt`` = AGM Series D preferred, which
    is ``AGM$D`` in Nasdaq's ACT column and ``AGM-D`` in its NASDAQ Symbol column). Which of
    those is canonical is build_identity's decision, so the normaliser makes none: the
    alias table bridges these and the importer reports them unmapped until it does."""
    assert stooq_symbol("AGM_D.US") == "AGM_D"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "   ", ".US", "SPY.UK", "SPY.US.US", "BRK.B.US", "SPY-"])
def test_stooq_symbol_rejects_what_is_not_a_stooq_us_ticker(bad: str) -> None:
    with pytest.raises(ValueError):
        stooq_symbol(bad)


# ── parsers: the real files or nothing ──

_SNAPSHOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "symbology"
SYMBOLOGY_DIR = os.environ.get("SYMBOLOGY_DIR", "") or str(_SNAPSHOT)
_FILES = ("nasdaqlisted.txt", "otherlisted.txt", "company_tickers.json")
_have_files = all((Path(SYMBOLOGY_DIR) / f).is_file() for f in _FILES)

real_files = pytest.mark.skipif(
    not _have_files,
    reason=f"{SYMBOLOGY_DIR} must hold the three real files: " + ", ".join(_FILES),
)


@pytest.fixture(scope="module")
def nasdaq() -> pd.DataFrame:
    return parse_nasdaq_symbol_directory((Path(SYMBOLOGY_DIR) / "nasdaqlisted.txt").read_text())


@pytest.fixture(scope="module")
def other() -> pd.DataFrame:
    return parse_nasdaq_symbol_directory((Path(SYMBOLOGY_DIR) / "otherlisted.txt").read_text())


@pytest.fixture(scope="module")
def sec() -> pd.DataFrame:
    return parse_sec_company_tickers((Path(SYMBOLOGY_DIR) / "company_tickers.json").read_text())


@real_files
@pytest.mark.unit  # real files on disk, no DB or network — runs in `make test`
class TestRealDirectories:
    def test_nasdaqlisted_columns_follow_the_file_header(self, nasdaq: pd.DataFrame) -> None:
        assert list(nasdaq.columns) == [
            "symbol",
            "security_name",
            "market_category",
            "test_issue",
            "financial_status",
            "round_lot_size",
            "etf",
            "nextshares",
        ]

    def test_otherlisted_columns_follow_the_file_header(self, other: pd.DataFrame) -> None:
        assert list(other.columns) == [
            "act_symbol",
            "security_name",
            "exchange",
            "cqs_symbol",
            "etf",
            "round_lot_size",
            "test_issue",
            "nasdaq_symbol",
        ]

    def test_the_file_creation_time_trailer_is_dropped(
        self, nasdaq: pd.DataFrame, other: pd.DataFrame
    ) -> None:
        for frame, col in ((nasdaq, "symbol"), (other, "act_symbol")):
            assert not frame[col].str.startswith("File Creation Time").any()
            assert frame[col].str.len().between(1, 16).all()

    def test_test_issues_are_filtered_out(self, nasdaq: pd.DataFrame, other: pd.DataFrame) -> None:
        for frame in (nasdaq, other):
            assert frame["test_issue"].dtype == bool
            assert not any(frame["test_issue"].tolist())
        # Nasdaq's own tick-pilot test symbols must not survive.
        assert "ZAZZT" not in set(nasdaq["symbol"])
        assert "ATEST" not in set(other["act_symbol"])

    def test_etf_flag_is_boolean_and_marks_real_etfs(
        self, nasdaq: pd.DataFrame, other: pd.DataFrame
    ) -> None:
        assert nasdaq["etf"].dtype == bool and other["etf"].dtype == bool
        assert bool(nasdaq.loc[nasdaq["symbol"] == "QQQ", "etf"].item())
        assert not bool(nasdaq.loc[nasdaq["symbol"] == "AAPL", "etf"].item())
        spy = other.loc[other["act_symbol"] == "SPY"]
        assert bool(spy["etf"].item()) and spy["exchange"].item() == "P"  # NYSE Arca

    def test_round_lot_size_is_an_integer(self, nasdaq: pd.DataFrame, other: pd.DataFrame) -> None:
        for frame in (nasdaq, other):
            assert pd.api.types.is_integer_dtype(frame["round_lot_size"])
            assert (frame["round_lot_size"] > 0).all()

    def test_combined_etf_count_clears_the_universe_gate(
        self, nasdaq: pd.DataFrame, other: pd.DataFrame
    ) -> None:
        # docs/global/data-sources.md, "ETF universe" gate: ≥ 5,000 rows, every one with an
        # exchange (5,655 on the 2026-09-04 files). nasdaqlisted rows are Nasdaq-listed by
        # construction.
        n_etf = int(nasdaq["etf"].sum()) + int(other["etf"].sum())
        assert n_etf >= 5000, n_etf
        assert all(len(code) == 1 for code in other["exchange"].tolist())

    def test_stooq_class_share_spelling_is_the_directory_spelling(
        self, other: pd.DataFrame
    ) -> None:
        # The archive member is brk-b.us.txt; the directory lists Berkshire B as BRK.B.
        assert stooq_symbol("brk-b.us") in set(other["act_symbol"])

    def test_sec_company_tickers_are_cik_ticker_name(self, sec: pd.DataFrame) -> None:
        assert list(sec.columns) == ["cik", "ticker", "name"]
        assert len(sec) >= 5000
        assert sec["ticker"].is_unique
        assert sec["cik"].str.fullmatch(r"\d{10}").all()  # zero-padded, as EDGAR URLs need
        assert sec.loc[sec["ticker"] == "AAPL", "cik"].item() == "0000320193"
        assert sec.loc[sec["ticker"] == "AAPL", "name"].item() == "Apple Inc."
