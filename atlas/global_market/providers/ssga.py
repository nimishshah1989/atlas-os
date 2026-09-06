"""SSGA SPDR daily holdings — the S&P 500's constituents (SPY) and their GICS sectors (the
eleven Select Sector SPDRs), from State Street's public ``.xlsx`` workbooks.

Source (one workbook per fund, one sheet ``holdings``; SPY was 54,422 bytes on 2026-09-04)::

    https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{spy|xlk|…}.xlsx

(SSGA answers with a 301 to ``/library-content/products/fund-data/…`` — ``requests`` follows
it; observed 2026-09-04.) Layout, verified on the 2026-09-03 files of all twelve funds: three
preamble rows — ``Fund Name:``, ``Ticker Symbol:``, ``Holdings:`` (``As of 03-Sep-2026``) — a
blank row, the header ``Name | Ticker | Identifier | SEDOL | Weight | Sector | Shares Held |
Local Currency``, then one row per holding up to the first blank row; SSGA's disclosure text
follows. ``Identifier`` is the CUSIP. ``Weight`` is a PERCENT (``8.287016`` for NVDA in SPY).
``-`` is SSGA's placeholder for "no value": the cash line (``US DOLLAR``, ticker ``-``) and,
on every 2026-09-03 file, the ``Sector`` cell of EVERY row — the column exists but is no
longer filled, which is why the GICS sector comes from MEMBERSHIP of the Select Sector SPDR
files instead (:func:`sector_by_membership`). Each sector file also carries one index-futures
line (``IXTU6`` in XLK) that is not in SPY; nothing filters it, it simply matches nothing.

Parsing rules: columns are located by header NAME (a reorder cannot shift data silently);
the placeholder becomes ``None``, never the string ``"-"``; ``weight_frac`` is
``Decimal(str(cell)) / 100`` exactly; ``shares_held`` is ``Decimal(str(cell))`` (openpyxl
hands whole shares over as floats, ``295627398.0`` — the value is exact either way). Nothing
is filtered: the cash line and contra/escrow lines (SPY 2026-09-03: ``CONTRA HOLOGIC
INCORPO``, ticker ``2602335D``, no SEDOL, weight 3e-08) are returned as the file has them —
what is a constituent is the identity resolution in
``scripts/global_market/ingest_index_membership.py``, which reports every ticker it cannot
place and counts the equity rows (ticker AND SEDOL present) against the plan's 500–505.

Reuse — SSGA's own notice in the files' disclosure rows: "The whole or any part of this work
may not be reproduced, copied or transmitted or any of its contents disclosed to third parties
without SSGA's express written consent." Internal cross-check only; holdings are never shown
to clients without consent, and no workbook is committed to the repository (the tests fetch
the live files).
"""

from __future__ import annotations

import io
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pandas as pd
import requests

HOLDINGS_URL = (
    "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/"
    "holdings-daily-us-en-{ticker}.xlsx"
)
SPY = "SPY"
PLACEHOLDER = "-"
TIMEOUT = 60

# The eleven Select Sector SPDR ETFs → the GICS sector each holds. GICS (the Global Industry
# Classification Standard of MSCI and S&P Dow Jones Indices) has eleven sectors since the
# 2018 restructuring (Communication Services replaced Telecommunication Services; Real Estate
# was split from Financials in 2016); each S&P Select Sector Index holds exactly the S&P 500
# constituents of one GICS sector (S&P DJI, "S&P Select Sector Indices Methodology"). Verified
# on the 2026-09-03 files: the eleven partition SPY's 504 ticker rows — each in exactly one.
SECTOR_ETFS: dict[str, str] = {
    "XLB": "Materials",
    "XLC": "Communication Services",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Information Technology",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
}

# File header → output column. Every one must be present; extra columns are ignored.
_HEADER: dict[str, str] = {
    "Name": "name",
    "Ticker": "ticker",
    "Identifier": "cusip",
    "SEDOL": "sedol",
    "Weight": "weight_frac",
    "Sector": "sector",
    "Shares Held": "shares_held",
    "Local Currency": "currency",
}
HOLDINGS_COLUMNS: tuple[str, ...] = tuple(_HEADER.values())
SECTOR_MAP_COLUMNS: tuple[str, ...] = ("ticker", "cusip", "sector_gics", "sector_etf", "matches")
_PERCENT = Decimal(100)


def holdings_endpoint(ticker: str) -> str:
    return f"holdings-daily-us-en-{ticker.lower()}.xlsx"


class SsgaProvider:
    """The fetch half: one GET per workbook, counted in ``calls`` by file name (a failed
    request still counts — it spent the request)."""

    name = "ssga"

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()

    def fetch_holdings(self, ticker: str) -> bytes:
        """The fund's workbook bytes, exactly as served. Raises on any HTTP error."""
        self.calls[holdings_endpoint(ticker)] += 1
        r = requests.get(HOLDINGS_URL.format(ticker=ticker.lower()), timeout=TIMEOUT)
        r.raise_for_status()
        return r.content


def _as_of(value: object) -> date:
    try:
        return datetime.strptime(str(value).strip(), "As of %d-%b-%Y").date()
    except ValueError as e:
        raise ValueError(f"Holdings: preamble is not 'As of DD-Mon-YYYY': {value!r}") from e


def _cell(value: object) -> object:
    """Strip strings; SSGA's ``-`` placeholder → None; numbers pass through untouched."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return None if s in ("", PLACEHOLDER) else s
    return value


def _decimal(value: object, what: str, row: int) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"row {row}: {what} is missing")
    return Decimal(str(value))  # str() first: a float's repr is what the cell shows


def parse_holdings(xlsx_bytes: bytes, expect_ticker: str) -> tuple[date, pd.DataFrame]:
    """``(as_of, DataFrame[HOLDINGS_COLUMNS])`` — every holding row in file order.

    Refuses a workbook whose ``Ticker Symbol:`` is not ``expect_ticker`` (the same layout
    serves every SPDR fund) and one whose header lacks any expected column.
    """
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    try:
        rows = [tuple(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]
    finally:
        wb.close()
    preamble = {
        str(r[0]).strip(): r[1]
        for r in rows[:6]
        if r and isinstance(r[0], str) and r[0].strip().endswith(":")
    }
    fund = preamble.get("Ticker Symbol:")
    if fund != expect_ticker:
        raise ValueError(f"not the {expect_ticker} holdings workbook: Ticker Symbol = {fund!r}")
    as_of = _as_of(preamble.get("Holdings:"))

    header_at = next(
        (i for i, r in enumerate(rows) if r and r[0] == "Name" and "Ticker" in r), None
    )
    if header_at is None:
        raise ValueError("no header row starting with 'Name' … 'Ticker'")
    header = [str(c).strip() if c is not None else "" for c in rows[header_at]]
    missing = [h for h in _HEADER if h not in header]
    if missing:
        raise ValueError(f"header lacks {missing}; got {[h for h in header if h]}")
    at = {out: header.index(h) for h, out in _HEADER.items()}

    records: list[dict[str, object]] = []
    for n, r in enumerate(rows[header_at + 1 :], start=header_at + 2):  # 1-based sheet row
        name = _cell(r[at["name"]] if at["name"] < len(r) else None)
        if name is None:
            break  # the first blank row ends the holdings block; disclosures follow
        rec: dict[str, object] = {out: _cell(r[i] if i < len(r) else None) for out, i in at.items()}
        rec["weight_frac"] = _decimal(rec["weight_frac"], "Weight", n) / _PERCENT
        rec["shares_held"] = _decimal(rec["shares_held"], "Shares Held", n)
        records.append(rec)
    if not records:
        raise ValueError("no holdings rows under the header")
    return as_of, pd.DataFrame.from_records(records, columns=list(HOLDINGS_COLUMNS))


def parse_sector_holdings(xlsx_bytes: bytes, ticker: str) -> tuple[date, pd.DataFrame]:
    """A Select Sector SPDR workbook → ``(as_of, DataFrame[HOLDINGS_COLUMNS])`` of the rows
    that carry a ticker (the cash line has none; the index-futures line stays)."""
    if ticker not in SECTOR_ETFS:
        raise ValueError(f"{ticker!r} is not one of the Select Sector SPDRs {sorted(SECTOR_ETFS)}")
    as_of, df = parse_holdings(xlsx_bytes, ticker)
    return as_of, df.loc[df["ticker"].notna()].reset_index(drop=True)


def sector_by_membership(
    spy_holdings: pd.DataFrame, sectors: Mapping[str, pd.DataFrame]
) -> pd.DataFrame:
    """GICS sector of every SPY ticker row by which Select Sector SPDR file lists its CUSIP.

    ``DataFrame[ticker, cusip, sector_gics, sector_etf, matches]`` — ``matches`` is the tuple
    of sector ETFs whose file carries the CUSIP; ``sector_gics`` / ``sector_etf`` are filled
    only when that tuple has exactly ONE entry. Zero or several → ``None`` (the caller reports
    the row; nothing guesses). A ``sectors`` key outside :data:`SECTOR_ETFS` is refused.
    """
    unknown = sorted(set(sectors) - set(SECTOR_ETFS))
    if unknown:
        raise ValueError(f"not Select Sector SPDRs: {unknown}")
    by_cusip: dict[str, list[str]] = {}
    for etf in sorted(sectors):
        for cusip in sectors[etf]["cusip"].dropna():
            by_cusip.setdefault(str(cusip), []).append(etf)
    rows: list[tuple[object, ...]] = []
    spy = spy_holdings.loc[spy_holdings["ticker"].notna()]
    for ticker, cusip in spy[["ticker", "cusip"]].itertuples(index=False):
        matches = tuple(by_cusip.get(str(cusip), ())) if cusip is not None else ()
        etf = matches[0] if len(matches) == 1 else None
        rows.append((ticker, cusip, SECTOR_ETFS[etf] if etf else None, etf, matches))
    return pd.DataFrame.from_records(rows, columns=list(SECTOR_MAP_COLUMNS)).astype(object)
