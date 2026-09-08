"""Assemble the DESIRED identity frame from the parsed directories — pure, DataFrames in and
out, no I/O. The script reads the files and the database; the planner (``identity_plan``)
diffs this frame against what the database holds.

Steps, each a function so the numbers can be measured and asserted on the real files:

1. :func:`directory_frame` — the two Nasdaq Trader files merged: canonical symbol, name,
   exchange name (the file's legend, refused when unknown), ``asset_class`` from the ETF
   flag, the CQS / NASDAQ spellings the alias rules need.
2. :func:`attach_sec` — the SEC identity: stocks from ``company_tickers.json`` (then the
   optional exchange file), funds from ``company_tickers_mf.json`` (CIK + series + class) then
   the two issuer files (trusts and commodity pools — SPY, GLD, USO — are registrants, not
   1940-Act funds). The ticker is looked up under the SEC's own spelling
   (:func:`identity.sec_spelling`); the spelling that matched is kept as ``sec_ticker``.
   Every CIK the files carry for the ticker is looked at: when they disagree the row gets a
   ``sec_conflict`` note listing them all (the precedence above still picks one), and
   ``name_agrees`` says whether the directory name and the SEC title describe one issuer
   (:func:`identity.names_agree`; ``None`` when no title-bearing file lists the ticker).
3. :func:`tiingo_listings` + :func:`attach_listing_dates` — ``listing_date`` from Tiingo's
   ``startDate`` for the ticker's CURRENT listing period on a US exchange, else the run
   date; ``listing_source`` says which.

Measured on the 2026-09-04 files (asserted in tests/unit/global_market/test_identity_frame.py):
13,154 listings = 5,655 ETFs + 7,499 stock-flagged (preferreds, warrants, units and notes
included); CIK on 99.6 percent of stock-flagged rows (the rest: rights, which the SEC does
not list, and a handful of bank holding companies that file with their regulator, not the
SEC); an SEC identity on 82.5 percent of ETFs (79.3 percent with a series/class id —
1940-Act funds only); the exchange file adds no identity the other two lack; four tickers
carry two CIKs across the files (IA, SPCX, AEMC, ISRL); 117 names disagree with the SEC
title under their ticker; Tiingo lists 99.4 percent of the directory on a US exchange.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from atlas.global_market import identity as ident

DIRECTORY_COLUMNS = (
    "symbol",
    "name",
    "exchange",
    "asset_class",
    "cqs_symbol",
    "nasdaq_symbol",
    "nasdaq_listed",
)
DESIRED_COLUMNS = (
    *DIRECTORY_COLUMNS,
    "cik",
    "series_id",
    "class_id",
    "sec_ticker",
    "sec_source",
    "sec_conflict",
    "name_agrees",
    "listing_date",
    "listing_source",
    "tiingo_ticker",
)

SEC_SOURCE_COMPANY_TICKERS = "company_tickers"
SEC_SOURCE_MF = "company_tickers_mf"
SEC_SOURCE_EXCHANGE = "company_tickers_exchange"
LISTING_SOURCE_TIINGO = "tiingo"
LISTING_SOURCE_RUN_DATE = "run_date"

# Tiingo "exchange" values that are US listing venues (the file's own spellings, seen
# 2026-09-04). PINK / OTC* / EXPM rows are over-the-counter lines that may carry a
# recycled ticker: never the proof that Tiingo lists THIS listing.
TIINGO_US_EXCHANGES = frozenset(
    {"NASDAQ", "NYSE", "NYSE ARCA", "BATS", "AMEX", "NYSE MKT", "NYSE NAT", "IEX"}
)
TIINGO_ASSET_TYPES = frozenset({"Stock", "ETF"})
TIINGO_CURRENCY = "USD"

_ASSET_CLASS = {True: "etf", False: "stock"}


# ── 1. directories ──


def directory_frame(nasdaq: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    """One row per listing with :data:`DIRECTORY_COLUMNS`; test issues are already gone
    (the parser drops them). A symbol present in both files, or twice in one, raises —
    one ACTIVE row per symbol is the table's invariant, and a duplicate is a fact to look
    at, not a row to pick."""
    left = pd.DataFrame(
        {
            "symbol": nasdaq["symbol"],
            "name": nasdaq["security_name"],
            "exchange": ident.NASDAQ,
            "asset_class": nasdaq["etf"].map(_ASSET_CLASS.__getitem__),
            "cqs_symbol": nasdaq["symbol"],
            "nasdaq_symbol": nasdaq["symbol"],
            "nasdaq_listed": True,
        }
    )
    right = pd.DataFrame(
        {
            "symbol": other["act_symbol"],
            "name": other["security_name"],
            "exchange": [
                ident.exchange_name(code, sym)
                for code, sym in zip(other["exchange"], other["act_symbol"], strict=True)
            ],
            "asset_class": other["etf"].map(_ASSET_CLASS.__getitem__),
            "cqs_symbol": other["cqs_symbol"],
            "nasdaq_symbol": other["nasdaq_symbol"],
            "nasdaq_listed": False,
        }
    )
    frame = pd.concat([left, right], ignore_index=True)
    dup = sorted(set(frame.loc[frame["symbol"].duplicated(keep=False), "symbol"]))
    if dup:
        raise ValueError(f"symbol directory: {len(dup)} duplicated symbol(s): {dup[:10]}")
    return frame


# ── 2. SEC identity ──


def _unique_map(frame: pd.DataFrame, key: str, values: list[str], name: str) -> dict[str, tuple]:
    """``key → tuple(values)`` refusing a key that maps to two DIFFERENT value tuples (an
    ambiguous identity is no identity)."""
    out: dict[str, tuple] = {}
    for row in frame.loc[frame[key].notna(), [key, *values]].itertuples(index=False):
        k = str(row[0])
        v = tuple(row[1:])
        if k in out and out[k] != v:
            raise ValueError(f"{name}: {k} maps to two identities {out[k]} and {v}")
        out[k] = v
    return out


def _sec_row(
    symbol: str,
    spelled: str | None,
    asset_class: str,
    name: str,
    by_ct: dict[str, tuple],
    by_mf: dict[str, tuple],
    by_ex: dict[str, tuple],
) -> tuple:
    """(cik, series_id, class_id, sec_ticker, sec_source, sec_conflict, name_agrees)."""
    mf = by_mf.get(symbol)
    ct = by_ct.get(spelled) if spelled else None
    ex = by_ex.get(spelled) if spelled else None
    if asset_class == "etf" and mf:
        hit: tuple = (*mf, symbol, SEC_SOURCE_MF)
    elif ct:
        hit = (ct[0], None, None, spelled, SEC_SOURCE_COMPANY_TICKERS)
    elif ex:
        hit = (ex[0], None, None, spelled, SEC_SOURCE_EXCHANGE)
    else:
        hit = (None, None, None, None, None)
    seen = [
        (source, x[0])
        for source, x in (
            (SEC_SOURCE_COMPANY_TICKERS, ct),
            (SEC_SOURCE_MF, mf),
            (SEC_SOURCE_EXCHANGE, ex),
        )
        if x
    ]
    conflict = "; ".join(f"{s} {c}" for s, c in seen) if len({c for _s, c in seen}) > 1 else None
    title = (ct or ex or (None, None))[1]
    agrees = ident.names_agree(name, title) if title else None
    return (*hit, conflict, agrees)


def attach_sec(
    frame: pd.DataFrame,
    company_tickers: pd.DataFrame,
    mf: pd.DataFrame,
    exchange: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add the SEC columns (see the module docstring). Funds: the MF file first (CIK +
    series + class), then the registrant files; stocks: ``company_tickers.json`` then the
    optional ``company_tickers_exchange.json``. A row no file lists keeps ``None``
    everywhere — the fallback key, never a guess."""
    by_ct = _unique_map(company_tickers, "ticker", ["cik", "name"], "company_tickers.json")
    by_mf = _unique_map(mf, "symbol", ["cik", "series_id", "class_id"], "company_tickers_mf.json")
    by_ex = (
        _unique_map(exchange, "ticker", ["cik", "name"], "company_tickers_exchange.json")
        if exchange is not None
        else {}
    )
    spelled = frame["cqs_symbol"].map(ident.sec_spelling)
    sec = pd.DataFrame.from_records(
        [
            _sec_row(sym, sp, cls, nm, by_ct, by_mf, by_ex)
            for sym, sp, cls, nm in zip(
                frame["symbol"], spelled, frame["asset_class"], frame["name"], strict=True
            )
        ],
        columns=[
            "cik",
            "series_id",
            "class_id",
            "sec_ticker",
            "sec_source",
            "sec_conflict",
            "name_agrees",
        ],
        index=frame.index,
    ).astype(object)
    return pd.concat([frame, sec], axis=1)


# ── 3. listing dates ──


def tiingo_listings(tiingo: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker — its CURRENT US listing period: rows on a US exchange, priced in
    USD, typed Stock/ETF, with a start date; when a ticker has several (a data gap or a
    recycled ticker) the one with the latest ``end_date`` wins, ties to the earliest start.
    Columns: ``ticker, exchange, asset_type, start_date, end_date``."""
    keep = (
        tiingo["exchange"].isin(sorted(TIINGO_US_EXCHANGES))
        & (tiingo["price_currency"] == TIINGO_CURRENCY)
        & tiingo["asset_type"].isin(sorted(TIINGO_ASSET_TYPES))
        & tiingo["start_date"].notna()
    )
    rows = tiingo.loc[keep, ["ticker", "exchange", "asset_type", "start_date", "end_date"]]
    rows = rows.assign(_end=rows["end_date"].fillna(date.max))
    rows = rows.sort_values(["ticker", "_end", "start_date"], ascending=[True, False, True])
    rows = rows.drop_duplicates("ticker", keep="first").drop(columns="_end")
    return rows.reset_index(drop=True)


def attach_listing_dates(
    frame: pd.DataFrame, listings: pd.DataFrame, run_date: date
) -> pd.DataFrame:
    """Add ``listing_date, listing_source, tiingo_ticker``: Tiingo's ``start_date`` under
    Tiingo's spelling of the CQS symbol when :func:`tiingo_listings` has it, else ``run_date``
    (the first date WE saw the listing — honest, and stable across re-runs only through the
    planner, which never re-mints)."""
    start = dict(zip(listings["ticker"], listings["start_date"], strict=True))
    tiingo = frame["cqs_symbol"].map(ident.tiingo_spelling).astype(object)
    dates = tiingo.map(start.get).astype(object)
    listed = dates.notna()
    return frame.assign(
        listing_date=dates.where(listed, run_date),
        listing_source=pd.Series(LISTING_SOURCE_TIINGO, index=frame.index, dtype=object).where(
            listed, LISTING_SOURCE_RUN_DATE
        ),
        tiingo_ticker=tiingo.where(listed, None),
    )


# ── measurement ──


def coverage(frame: pd.DataFrame) -> dict[str, int]:
    """The counts the DoD asks for, measured on the assembled frame (printed every run;
    the script turns them into percentages)."""
    etf = frame["asset_class"] == "etf"
    stock = ~etf
    has_cik = frame["cik"].notna()
    return {
        "rows": len(frame),
        "etf_rows": int(etf.sum()),
        "stock_rows": int(stock.sum()),
        "rows_with_exchange": int(frame["exchange"].notna().sum()),
        "stock_cik": int((stock & has_cik).sum()),
        "etf_cik": int((etf & has_cik).sum()),
        "etf_series": int((etf & frame["series_id"].notna()).sum()),
        "etf_cik_via_mf": int((etf & (frame["sec_source"] == SEC_SOURCE_MF)).sum()),
        "etf_cik_via_company_tickers": int(
            (etf & (frame["sec_source"] == SEC_SOURCE_COMPANY_TICKERS)).sum()
        ),
        "cik_via_exchange_file": int((frame["sec_source"] == SEC_SOURCE_EXCHANGE).sum()),
        "sec_conflicts": int(frame["sec_conflict"].notna().sum()),
        "names_checked": int(frame["name_agrees"].notna().sum()),
        "name_disagreements": int((frame["name_agrees"] == False).sum()),  # noqa: E712 -- object column: None is neither
        "listing_date_tiingo": int((frame["listing_source"] == LISTING_SOURCE_TIINGO).sum()),
    }
