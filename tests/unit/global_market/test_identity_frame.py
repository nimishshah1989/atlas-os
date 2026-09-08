"""identity_frame on the REAL 2026-09-04 files: every number below is measured, not assumed.

The DoD thresholds of docs/global/phase1.md P1-A are asserted here on the dated verbatim
snapshot in ``tests/fixtures/global/symbology/`` (the frames come from ``conftest.py``;
``SYMBOLOGY_DIR`` points at fresher files). Without the files the module skips — never a
vacuous pass. The snapshot carries no ``company_tickers_exchange.json`` (optional; measured
to add nothing), so every number here is the build's own.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from atlas.global_market import identity_frame as frame_mod
from tests.unit.global_market.conftest import RUN_DATE

pytestmark = pytest.mark.unit


# ── 1. directories ──


def test_directory_has_the_dod_row_counts_and_an_exchange_on_every_row(
    directory: pd.DataFrame,
) -> None:
    assert list(directory.columns) == list(frame_mod.DIRECTORY_COLUMNS)
    n_etf = int((directory["asset_class"] == "etf").sum())
    n_stock = int((directory["asset_class"] == "stock").sum())
    assert n_etf >= 5000, n_etf  # 5,655 on 2026-09-04
    assert n_stock >= 7000, n_stock  # 7,499 (preferreds, warrants, units, notes included)
    assert directory["symbol"].is_unique
    assert set(directory["exchange"]) == {"NASDAQ", "NYSE", "NYSEARCA", "BATS", "NYSEMKT"}
    assert bool(directory["exchange"].notna().all())


def test_directory_rows_keep_the_act_spelling_and_the_source_columns(
    directory: pd.DataFrame,
) -> None:
    by = directory.set_index("symbol")
    assert by.loc["BRK.B", ["exchange", "asset_class", "cqs_symbol", "nasdaq_symbol"]].tolist() == [
        "NYSE",
        "stock",
        "BRK.B",
        "BRK.B",
    ]
    assert by.loc["AGM$D", ["cqs_symbol", "nasdaq_symbol", "nasdaq_listed"]].tolist() == [
        "AGMpD",
        "AGM-D",
        False,
    ]
    assert str(by.loc["ACHR.W", "cqs_symbol"]) == "ACHR.WS"
    assert by.loc["SPY", ["exchange", "asset_class"]].tolist() == ["NYSEARCA", "etf"]
    assert by.loc["QQQ", ["exchange", "asset_class", "nasdaq_listed"]].tolist() == [
        "NASDAQ",
        "etf",
        True,
    ]
    assert by.loc["AAPL", ["exchange", "asset_class"]].tolist() == ["NASDAQ", "stock"]


def test_a_symbol_in_both_files_is_refused(nasdaq: pd.DataFrame, other: pd.DataFrame) -> None:
    clash = other.copy()
    clash.loc[0, "act_symbol"] = "AAPL"  # Nasdaq-listed Apple also on NYSE: impossible
    with pytest.raises(ValueError, match="duplicated"):
        frame_mod.directory_frame(nasdaq, clash)


# ── 2. SEC identity ──


def test_sec_identity_coverage_meets_the_dod(with_sec: pd.DataFrame) -> None:
    c = frame_mod.coverage(
        with_sec.assign(listing_source=frame_mod.LISTING_SOURCE_RUN_DATE)  # coverage needs it
    )
    assert c["stock_cik"] / c["stock_rows"] >= 0.99, c  # 99.6 percent (7,467 of 7,499)
    assert c["etf_cik"] / c["etf_rows"] >= 0.80, c  # 82.5 percent (4,666 of 5,655) — the floor
    assert c["etf_series"] / c["etf_rows"] >= 0.75, c  # 79.3 percent: 1940-Act funds only
    assert c["etf_cik_via_mf"] >= 4000 and c["etf_cik_via_company_tickers"] >= 100
    assert c["cik_via_exchange_file"] == 0  # the optional file is not in the snapshot


def test_the_stocks_without_a_cik_are_rights_and_non_sec_filers(with_sec: pd.DataFrame) -> None:
    stocks = with_sec.loc[with_sec["asset_class"] == "stock"]
    missing = stocks.loc[stocks["cik"].isna()]
    assert len(missing) < 50, len(missing)  # 32 on 2026-09-04
    # 22 rights (SPAC rights, contingent value rights), 1 warrant tranche, 6 banks that
    # file with their banking regulator rather than the SEC, 3 others (two new foreign
    # issuers and one post-bankruptcy relisting).
    explained = missing["name"].str.contains("Rights|Warrant|Bank|Savings", regex=True)
    assert explained.sum() >= 0.85 * len(missing), missing["symbol"].tolist()
    assert missing["symbol"].str.endswith((".R", ".V")).sum() >= 20


def test_sec_rows_carry_the_spelling_that_matched(with_sec: pd.DataFrame) -> None:
    by = with_sec.set_index("symbol")
    assert by.loc["BRK.B", ["cik", "sec_ticker", "sec_source"]].tolist() == [
        "0001067983",
        "BRK-B",
        "company_tickers",
    ]
    assert by.loc["AGM$D", ["cik", "sec_ticker"]].tolist() == ["0000845877", "AGM-PD"]
    assert by.loc["AAC.U", "sec_ticker"] == "AAC-UN"
    assert by.loc["ACHR.W", "sec_ticker"] == "ACHR-WT"
    assert by.loc["AIIA.R", "cik"] is None  # rights: not in the SEC files
    assert by.loc["AAPL", ["cik", "sec_source"]].tolist() == ["0000320193", "company_tickers"]
    # Funds: the MF file carries CIK + series + class; SPY (a UIT) only a registrant CIK.
    assert by.loc["QQQ", ["cik", "series_id", "class_id", "sec_source"]].tolist() == [
        "0001067839",
        "S000101292",
        "C000271435",
        "company_tickers_mf",
    ]
    assert by.loc["SPY", ["cik", "series_id", "sec_source"]].tolist() == [
        "0000884394",
        None,
        "company_tickers",
    ]


def test_the_four_tickers_the_sec_files_disagree_on_are_recorded(with_sec: pd.DataFrame) -> None:
    """Two real CIKs on file per ticker: the MF file names the fund class, company_tickers
    a registrant that used the ticker before (ISRL, AEMC) or a stock whose ticker a fund
    class also carries (IA, SPCX). The precedence still picks one; the conflict is kept."""
    conflicts = with_sec.loc[with_sec["sec_conflict"].notna()].set_index("symbol")
    assert sorted(conflicts.index) == ["AEMC", "IA", "ISRL", "SPCX"]
    assert conflicts.loc["ISRL", ["asset_class", "cik", "sec_source"]].tolist() == [
        "etf",
        "0002081107",
        "company_tickers_mf",
    ]
    assert conflicts.loc["ISRL", "sec_conflict"] == (
        "company_tickers 0001915328; company_tickers_mf 0002081107"
    )
    assert conflicts.loc["AEMC", ["cik", "sec_conflict"]].tolist() == [
        "0001860434",
        "company_tickers 0001882781; company_tickers_mf 0001860434",
    ]
    # Stock-flagged rows never take the MF file's CIK — but the disagreement is recorded.
    assert conflicts.loc["IA", ["asset_class", "cik", "sec_conflict"]].tolist() == [
        "stock",
        "0000836690",
        "company_tickers 0000836690; company_tickers_mf 0001592900",
    ]
    assert conflicts.loc["SPCX", ["cik", "sec_conflict"]].tolist() == [
        "0001181412",
        "company_tickers 0001181412; company_tickers_mf 0001719812",
    ]


def test_name_agreement_is_checked_against_the_sec_title(with_sec: pd.DataFrame) -> None:
    by = with_sec.set_index("symbol")
    assert by.loc["AAPL", "name_agrees"] is True
    assert by.loc["AEMC", "name_agrees"] is False  # Harbor AlphaEdge … vs C2 Blockchain, Inc.
    assert by.loc["ISRL", "name_agrees"] is True  # both names carry ISRAEL (the token rule)
    assert by.loc["AIIA.R", "name_agrees"] is None  # no SEC title on file for a right
    assert by.loc["BZZ", "name_agrees"] is None
    checked = int(with_sec["name_agrees"].notna().sum())
    disagree = int((with_sec["name_agrees"] == False).sum())  # noqa: E712 -- object column
    assert checked > 7500 and disagree < 0.02 * checked, (checked, disagree)  # 117 of 7,650
    # The disagreements the rule is for: stale SEC tickers (a delisted registrant's ticker
    # reused by a new listing) — BTLN is Brightline Interactive in the directory, Glimpse
    # Group in company_tickers.json; the rest are bank-issued ETNs and translated titles.
    assert by.loc["BTLN", "name_agrees"] is False
    assert by.loc["FIXX", "name_agrees"] is False  # Leverage Shares 2X Long FIX vs Q32 Bio


def test_an_ambiguous_sec_mapping_is_refused(company_tickers_mf: pd.DataFrame) -> None:
    """One file naming two identities for one ticker is refused outright. Built from the
    two REAL ISRL records: the MF file's fund class (0002081107) and the registrant
    company_tickers.json still lists under ISRL (0001915328), placed in one MF-shaped
    frame — the values are the files' own, only their co-location is the scenario."""
    isrl = company_tickers_mf.loc[company_tickers_mf["symbol"] == "ISRL"]
    assert len(isrl) == 1
    spac = pd.DataFrame(
        {"cik": ["0001915328"], "series_id": [None], "class_id": [None], "symbol": ["ISRL"]}
    )
    with pytest.raises(ValueError, match="ISRL maps to two identities"):
        frame_mod._unique_map(
            pd.concat([isrl, spac], ignore_index=True),
            "symbol",
            ["cik", "series_id", "class_id"],
            "company_tickers_mf.json",
        )


# ── 3. listing dates ──


def test_tiingo_listings_keep_one_current_us_row_per_ticker(listings: pd.DataFrame) -> None:
    assert listings["ticker"].is_unique
    assert set(listings["exchange"]) <= frame_mod.TIINGO_US_EXCHANGES
    by = listings.set_index("ticker")
    assert by.loc["SPY", "start_date"] == date(1993, 1, 29)
    assert by.loc["AAPL", "start_date"] == date(1980, 12, 12)
    # ACHR-WS has two overlapping rows; the one with the later end_date wins.
    assert by.loc["ACHR-WS", "start_date"] == date(2021, 9, 17)
    # LEND has two periods (2019-05-09 → 2021-06-25, then 2026-05-18 →): the current one.
    assert by.loc["LEND", "start_date"] == date(2026, 5, 18)
    # A ticker Tiingo lists only over the counter is not a US listing here.
    assert "AGMFF" not in by.index


def test_listing_dates_come_from_tiingo_for_nearly_every_row(desired: pd.DataFrame) -> None:
    assert list(desired.columns) == list(frame_mod.DESIRED_COLUMNS)
    c = frame_mod.coverage(desired)
    assert c["listing_date_tiingo"] / c["rows"] >= 0.98, c  # 99.4 percent on 2026-09-04
    by = desired.set_index("symbol")
    assert by.loc["SPY", ["listing_date", "listing_source", "tiingo_ticker"]].tolist() == [
        date(1993, 1, 29),
        "tiingo",
        "SPY",
    ]
    assert by.loc["BRK.B", "tiingo_ticker"] == "BRK-B"
    assert by.loc["AGM$D", ["listing_date", "tiingo_ticker"]].tolist() == [
        date(2019, 5, 9),
        "AGM-P-D",
    ]
    # The directory ETFs Tiingo does not list fall to the run date.
    for s in ("BZZ", "BLCK", "GASZ", "OWN", "USSX"):
        assert by.loc[s, ["listing_date", "listing_source"]].tolist() == [RUN_DATE, "run_date"], s
    assert by.loc["NMCO.V", "listing_source"] == "run_date"  # no Tiingo spelling for r/w
    assert by.loc["IA", "listing_source"] == "run_date"  # Tiingo's IA row has no exchange


def test_coverage_is_counts_only(desired: pd.DataFrame) -> None:
    c = frame_mod.coverage(desired)
    assert all(isinstance(v, int) for v in c.values()), c
    assert c["rows"] == c["etf_rows"] + c["stock_rows"] == 13154
    assert (c["etf_rows"], c["stock_rows"], c["stock_cik"], c["etf_cik"]) == (
        5655,
        7499,
        7467,
        4666,
    )
    assert (c["sec_conflicts"], c["names_checked"], c["name_disagreements"]) == (4, 7650, 117)
