"""Symbol-string normalisation (pure) and the directory parsers (real files only).

Ticker strings are not market data: ``SPY.US → SPY`` is a spelling rule, so those tests are
plain unit tests. The two parsers are tested ONLY against the real Nasdaq Trader and SEC
files (rule #0 — no fabricated fixture). By default that is the dated verbatim snapshot in
``tests/fixtures/global/symbology/`` (provenance and hashes in its ``SOURCE.md``), so CI
exercises the parsers on real records; ``SYMBOLOGY_DIR=<dir>`` points the same tests at
fresher downloads of ``nasdaqlisted.txt``, ``otherlisted.txt`` and ``company_tickers.json``
(and, for the newer parsers, ``company_tickers_mf.json``, ``company_tickers_exchange.json``,
``supported_tickers.zip``). If the directory lacks a file, the tests that need it skip — they
never pass vacuously.
"""

from __future__ import annotations

import os
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.providers.symbology import (
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers,
    parse_sec_company_tickers_exchange,
    parse_sec_company_tickers_mf,
    parse_tiingo_supported_tickers,
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


def _needs(name: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not (Path(SYMBOLOGY_DIR) / name).is_file(), reason=f"{SYMBOLOGY_DIR}/{name} missing"
    )


real_mf = _needs("company_tickers_mf.json")
real_exchange = _needs("company_tickers_exchange.json")
real_tiingo = _needs("supported_tickers.zip")


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


# ── the columnar SEC files and Tiingo's list: real files or nothing ──


@pytest.fixture(scope="module")
def mf() -> pd.DataFrame:
    return parse_sec_company_tickers_mf(
        (Path(SYMBOLOGY_DIR) / "company_tickers_mf.json").read_text()
    )


@pytest.fixture(scope="module")
def exchange() -> pd.DataFrame:
    return parse_sec_company_tickers_exchange(
        (Path(SYMBOLOGY_DIR) / "company_tickers_exchange.json").read_text()
    )


@pytest.fixture(scope="module")
def tiingo() -> pd.DataFrame:
    with zipfile.ZipFile(Path(SYMBOLOGY_DIR) / "supported_tickers.zip") as zf:
        (member,) = zf.namelist()
        return parse_tiingo_supported_tickers(zf.read(member).decode("utf-8"))


@real_mf
@pytest.mark.unit
class TestSecCompanyTickersMf:
    def test_columns_and_cik_shape(self, mf: pd.DataFrame) -> None:
        assert list(mf.columns) == ["cik", "series_id", "class_id", "symbol"]
        assert len(mf) >= 25_000  # 28,500 on 2026-09-04
        assert mf["cik"].str.fullmatch(r"\d{10}").all()
        assert mf["series_id"].str.fullmatch(r"S\d{9}").all()
        assert mf["class_id"].str.fullmatch(r"C\d{9}").all()

    def test_etfs_carry_cik_series_and_class(self, mf: pd.DataFrame) -> None:
        # Invesco QQQ Trust and iShares Core S&P 500 — 1940-Act funds with one class each.
        qqq = mf.loc[mf["symbol"] == "QQQ"]
        assert len(qqq) == 1 and qqq["cik"].item() == "0001067839"
        ivv = mf.loc[mf["symbol"] == "IVV"]
        assert ivv["series_id"].item() == "S000004310" and ivv["class_id"].item() == "C000012040"

    def test_trusts_and_commodity_pools_are_absent(self, mf: pd.DataFrame) -> None:
        # SPY is a unit investment trust, GLD a grantor trust, USO a commodity pool — not
        # 1940-Act funds, so the MF file has no row; build_identity takes their CIK from
        # company_tickers.json instead.
        assert not bool(mf["symbol"].isin(["SPY", "GLD", "USO"]).any())

    def test_symbols_are_upper_cased_and_never_empty_strings(self, mf: pd.DataFrame) -> None:
        # The file carries a handful of lower-case tickers (elfnx) and one class without one.
        present = mf["symbol"].dropna()
        assert (present == present.str.upper()).all()
        assert not (present == "").any()

    def test_a_renamed_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="expected fields"):
            parse_sec_company_tickers_mf(
                '{"fields": ["cik", "series", "class", "symbol"], "data": []}'
            )


@real_exchange
@pytest.mark.unit
class TestSecCompanyTickersExchange:
    def test_columns_and_hyphen_spelling(self, exchange: pd.DataFrame) -> None:
        assert list(exchange.columns) == ["cik", "name", "ticker", "exchange"]
        assert len(exchange) >= 5000
        assert exchange["ticker"].is_unique
        assert exchange["cik"].str.fullmatch(r"\d{10}").all()
        brk = exchange.loc[exchange["ticker"] == "BRK-B"]  # the SEC's spelling of BRK.B
        assert brk["cik"].item() == "0001067983" and brk["exchange"].item() == "NYSE"

    def test_exchange_values_are_the_secs_own(self, exchange: pd.DataFrame) -> None:
        assert set(exchange["exchange"].dropna()) <= {"Nasdaq", "NYSE", "OTC", "CBOE"}
        assert exchange.loc[exchange["ticker"] == "AAPL", "exchange"].item() == "Nasdaq"

    def test_agrees_with_company_tickers_on_every_shared_ticker(
        self, exchange: pd.DataFrame, sec: pd.DataFrame
    ) -> None:
        merged = exchange.merge(sec, on="ticker", suffixes=("_x", "_ct"))
        assert len(merged) >= 5000
        assert (merged["cik_x"] == merged["cik_ct"]).all()


@real_tiingo
@pytest.mark.unit
class TestTiingoSupportedTickers:
    def test_columns_and_dates(self, tiingo: pd.DataFrame) -> None:
        assert list(tiingo.columns) == [
            "ticker",
            "exchange",
            "asset_type",
            "price_currency",
            "start_date",
            "end_date",
        ]
        assert len(tiingo) >= 100_000  # 108,553 rows on 2026-09-04
        spy = tiingo.loc[tiingo["ticker"] == "SPY"]  # one row; Tiingo files it under NYSE
        assert spy["start_date"].item() == date(1993, 1, 29) and spy["asset_type"].item() == "ETF"
        assert spy["exchange"].item() == "NYSE" and spy["price_currency"].item() == "USD"
        aapl = tiingo.loc[tiingo["ticker"] == "AAPL"]
        assert aapl["start_date"].item() == date(1980, 12, 12)

    def test_tiingo_spellings_of_the_punctuation_tickers(self, tiingo: pd.DataFrame) -> None:
        present = set(tiingo["ticker"])
        assert {"BRK-B", "AAC-U", "ACHR-WS", "AGM-P-D", "ETI-P", "AIIA-R"} <= present
        assert "BRK.B" not in present and "AGM-D" not in present  # not Tiingo's spellings

    def test_a_ticker_may_carry_several_listing_periods(self, tiingo: pd.DataFrame) -> None:
        # ACHR-WS has two overlapping rows (a data gap, not two instruments); the identity
        # build picks the row with the latest end_date.
        rows = tiingo.loc[tiingo["ticker"] == "ACHR-WS"]
        assert len(rows) >= 2 and rows["end_date"].notna().all()

    def test_an_unexpected_header_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unexpected header"):
            parse_tiingo_supported_tickers("ticker,exchange\nSPY,NYSE ARCA\n")
