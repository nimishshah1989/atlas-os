"""SSGA holdings parsers and the sector map — on the LIVE workbooks (rule #0; none is committed).

SSGA's notice forbids reproducing its files, so each session fetches SPY and the eleven
Select Sector SPDR workbooks (``conftest`` / ``live_files``): every test here is ``live``.
Assertions are the invariants of the files' shape and the facts that do not move day to day
(CUSIPs, spellings, the GICS partition); the numbers that do move (as-of, row count, weight
sum) are printed beside what the 2026-09-03 files held.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from atlas.global_market.providers.ssga import (
    HOLDINGS_COLUMNS,
    PLACEHOLDER,
    SECTOR_ETFS,
    SECTOR_MAP_COLUMNS,
    parse_holdings,
    parse_sector_holdings,
    sector_by_membership,
)

pytestmark = pytest.mark.live

# Measured on the files "As of 03-Sep-2026" (fetched 2026-09-04) — printed, not asserted.
REF_AS_OF = date(2026, 9, 3)
REF_ROWS, REF_EQUITIES, REF_WEIGHT_SUM, REF_MAPPED = 505, 503, Decimal("0.99936168"), 504


# ── SPY ──


def test_as_of_is_read_from_the_preamble_and_is_a_recent_session(
    spy_holdings: tuple[date, pd.DataFrame],
) -> None:
    as_of, _ = spy_holdings
    print(f"live as_of={as_of} (2026-09-03 on the reference file)")
    assert REF_AS_OF <= as_of <= datetime.now(UTC).date()
    assert as_of.weekday() < 5  # holdings are as of a trading day


def test_columns_follow_the_contract(spy_holdings: tuple[date, pd.DataFrame]) -> None:
    assert list(spy_holdings[1].columns) == list(HOLDINGS_COLUMNS)


def test_row_count_is_the_index_plus_the_cash_and_contra_lines(
    spy_holdings: tuple[date, pd.DataFrame],
) -> None:
    df = spy_holdings[1]
    cash = df.loc[df["ticker"].isna()]
    equities = df.loc[df["ticker"].notna() & df["sedol"].notna()]
    print(f"live rows={len(df)} equities={len(equities)} (reference: {REF_ROWS} / {REF_EQUITIES})")
    # 505 on 2026-09-03 = 503 equities + cash + ONE contra line; a corporate action can add
    # another contra/escrow line, and that must not read as a parser failure — the
    # 500–505 gate on EQUITY rows is the script's (holdings_gate), not this one.
    assert 500 <= len(df) <= 510
    assert cash["name"].tolist() == ["US DOLLAR"]  # ticker "-" → None, never the string "-"
    assert 500 <= len(equities) <= 505


def test_weights_are_exact_decimal_fractions_that_sum_to_about_one(
    spy_holdings: tuple[date, pd.DataFrame],
) -> None:
    df = spy_holdings[1]
    assert all(isinstance(w, Decimal) for w in df["weight_frac"])
    total = sum(df["weight_frac"], Decimal(0))
    print(f"live Σ weight_frac={total} (reference: {REF_WEIGHT_SUM})")
    assert Decimal("0.99") <= total <= Decimal("1.01")
    assert all(Decimal(0) <= w <= Decimal(1) for w in df["weight_frac"])


def test_the_largest_names_carry_their_cusips(spy_holdings: tuple[date, pd.DataFrame]) -> None:
    df = spy_holdings[1].set_index("ticker")
    assert df.loc["NVDA", "cusip"] == "67066G104"
    assert df.loc["AAPL", "cusip"] == "037833100"
    assert df.loc["MSFT", "cusip"] == "594918104"
    assert bool(spy_holdings[1]["cusip"].str.len().eq(9).all())


def test_class_shares_use_the_directory_spelling(spy_holdings: tuple[date, pd.DataFrame]) -> None:
    tickers = spy_holdings[1]["ticker"].dropna()
    assert {"BRK.B", "BF.B"} <= set(tickers)  # the Nasdaq ACT spelling, no alias needed
    assert tickers.is_unique


def test_the_placeholder_becomes_none_and_the_sector_column_is_unfilled(
    spy_holdings: tuple[date, pd.DataFrame],
) -> None:
    """SSGA ships the Sector column but writes ``-`` in every cell (every 2026-09-03 file);
    that is why sector_gics comes from the Select Sector SPDR files. If this ever fails
    because SSGA filled the column again, the membership map gains a cross-check — it is not
    a parser bug."""
    df = spy_holdings[1]
    for col in ("ticker", "sector", "sedol", "cusip"):
        assert not bool(df[col].eq(PLACEHOLDER).any()), col
    assert int(df["sector"].notna().sum()) == 0


def test_currency_and_share_counts(spy_holdings: tuple[date, pd.DataFrame]) -> None:
    df = spy_holdings[1]
    assert bool(df["currency"].eq("USD").all())
    assert all(isinstance(s, Decimal) for s in df["shares_held"])
    equities = df.loc[df["ticker"].notna(), "shares_held"]
    assert all(s == s.to_integral_value() and s > 0 for s in equities)  # whole shares
    print(f"live NVDA shares={df.loc[df['ticker'] == 'NVDA', 'shares_held'].item()}")


def test_a_workbook_of_another_fund_is_refused(spy_bytes: bytes) -> None:
    with pytest.raises(ValueError, match="not the XLK holdings workbook"):
        parse_holdings(spy_bytes, "XLK")
    with pytest.raises(ValueError, match="not one of the Select Sector SPDRs"):
        parse_sector_holdings(spy_bytes, "SPY")


# ── the eleven Select Sector SPDRs → GICS sector by membership ──


def test_the_eleven_sector_files_are_dated_within_a_week_of_spy(
    spy_holdings: tuple[date, pd.DataFrame], sector_holdings: dict[str, tuple[date, pd.DataFrame]]
) -> None:
    """SSGA publishes the twelve files on the same cycle but not atomically: the script
    tolerates a sector file up to seven days from SPY's as-of (and records the mismatch in
    ingest_state), so this asserts what the script tolerates, not a single date."""
    assert set(sector_holdings) == set(SECTOR_ETFS) and len(SECTOR_ETFS) == 11
    spy_as_of = spy_holdings[0]
    as_ofs = {etf: a for etf, (a, _) in sector_holdings.items()}
    mismatched = sorted(etf for etf, a in as_ofs.items() if a != spy_as_of)
    print(
        f"sector as-of dates: {sorted(set(as_ofs.values()))} (SPY {spy_as_of}); "
        f"differ: {mismatched}"
    )
    for etf, a in as_ofs.items():
        assert a.weekday() < 5 and a >= REF_AS_OF, etf
        assert abs(a - spy_as_of) <= timedelta(days=7), etf
    for etf, (_, df) in sector_holdings.items():
        assert list(df.columns) == list(HOLDINGS_COLUMNS), etf
        assert bool(df["ticker"].notna().all()) and 10 <= len(df) <= 120, etf
        assert Decimal("0.99") <= sum(df["weight_frac"], Decimal(0)) <= Decimal("1.01"), etf


def test_every_spy_ticker_row_maps_to_exactly_one_sector_file(
    spy_holdings: tuple[date, pd.DataFrame], sector_frames: dict[str, pd.DataFrame]
) -> None:
    m = sector_by_membership(spy_holdings[1], sector_frames)
    n_ticker_rows = int(spy_holdings[1]["ticker"].notna().sum())
    mapped = int(m["sector_gics"].notna().sum())
    n_matches = m["matches"].map(len)
    zero, multi = m.loc[n_matches == 0], m.loc[n_matches >= 2]
    print(
        f"live: {mapped} of {len(m)} ticker rows in exactly one sector file, "
        f"{len(zero)} in none {zero['ticker'].tolist()}, {len(multi)} in several "
        f"{multi[['ticker', 'matches']].values.tolist()} (reference: {REF_MAPPED} of {REF_MAPPED})"
    )
    assert list(m.columns) == list(SECTOR_MAP_COLUMNS) and len(m) == n_ticker_rows
    assert mapped >= 0.98 * n_ticker_rows  # the DoD floor
    assert len(multi) == 0  # a double mapping never becomes a sector
    # Every unmapped row carries the reason (its matches tuple) — the script reports it.
    assert bool((m["sector_gics"].isna() == (n_matches != 1)).all())


def test_the_map_names_the_gics_sector_of_well_known_members(
    spy_holdings: tuple[date, pd.DataFrame], sector_frames: dict[str, pd.DataFrame]
) -> None:
    m = sector_by_membership(spy_holdings[1], sector_frames)
    by = dict(zip(m["ticker"], m["sector_gics"], strict=True))
    assert by["NVDA"] == by["AAPL"] == by["MSFT"] == "Information Technology"
    assert by["GOOGL"] == by["GOOG"] == "Communication Services"  # both classes, one sector
    assert by["JPM"] == by["BRK.B"] == "Financials"
    assert by["XOM"] == "Energy" and by["AMZN"] == "Consumer Discretionary"
    assert by["PG"] == "Consumer Staples" and by["LLY"] == "Health Care"
    assert by["PLD"] == "Real Estate" and by["NEE"] == "Utilities" and by["LIN"] == "Materials"


def test_the_map_refuses_a_fund_that_is_not_a_sector_spdr(
    spy_holdings: tuple[date, pd.DataFrame],
) -> None:
    with pytest.raises(ValueError, match="not Select Sector SPDRs"):
        sector_by_membership(spy_holdings[1], {"SPY": spy_holdings[1]})
