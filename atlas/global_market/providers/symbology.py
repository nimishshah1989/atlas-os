"""Symbol spelling rules and the identity-directory parsers — pure functions, no I/O.

Three sources spell one listing three ways. The identity bridge (``build_identity.py`` →
``instrument_master`` + ``symbol_alias``) is where the spellings meet; this module only
parses and normalises, and it invents nothing: a spelling it cannot map is left as it is
and the alias table bridges it.

* **Stooq** — ``<stem>.us.txt`` file stems: ``spy.us``; ``brk-b.us`` (class B); ``aac-u.us``
  (units); ``ne-ws-a.us`` (warrants); ``agm_d.us`` (preferred series D); ``eti_.us``
  (preferred, no series).
* **Nasdaq Trader symbol directory** — ``nasdaqlisted.txt`` (Nasdaq-listed; ``Symbol`` uses
  Nasdaq's suffix letters, no punctuation) and ``otherlisted.txt`` (every other exchange;
  ``ACT Symbol`` ``BRK.B`` / ``AGM$D`` / ``AAC.U``, ``CQS Symbol`` ``AGMpD`` / ``ACHR.WS``,
  ``NASDAQ Symbol`` ``AGM-D`` / ``AAC=`` / ``ACHR+``). Pipe-delimited, last line
  ``File Creation Time: MMDDYYYYHH:MM``.
  https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt and .../otherlisted.txt
* **SEC** — ``company_tickers.json``: ``{"0": {"cik_str": 320193, "ticker": "AAPL",
  "title": "Apple Inc."}, …}``. https://www.sec.gov/files/company_tickers.json (SEC's
  fair-access rule wants a ``User-Agent`` carrying a contact address). The two columnar
  siblings, ``{"fields": [...], "data": [[...], …]}`` (shapes verified 2026-09-04):
  ``company_tickers_mf.json`` (``cik, seriesId, classId, symbol`` — 1940-Act funds, 28,500
  rows) and ``company_tickers_exchange.json`` (``cik, name, ticker, exchange``; tickers spelled
  with a HYPHEN, ``BRK-B``). SEC spells class shares ``BRK-B``, preferreds ``AGM-PD`` /
  ``ETI-P``, warrants ``ACHR-WT``, units ``AAC-UN``; rights are absent.
* **Tiingo** — ``supported_tickers.zip`` (one CSV: ``ticker, exchange, assetType,
  priceCurrency, startDate, endDate``; ~108k rows, several per ticker when a listing was
  interrupted or the ticker recycled). Spellings ``BRK-B``, ``AAC-U``, ``ACHR-WS``,
  ``AGM-P-D``, ``ETI-P``, ``AIIA-R``.
  https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date

import pandas as pd

STOOQ_MARKET_SUFFIX = ".US"
# base, any number of "-x" segments (class / unit / warrant), an optional "_y" (preferred).
_STOOQ_STEM = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*(_[A-Z0-9]*)?$")

_DIRECTORY_TRAILER = "File Creation Time"
_DIRECTORY_FIRST_COLUMNS = ("symbol", "act_symbol")
_DIRECTORY_FLAG_COLUMNS = ("etf", "test_issue", "nextshares")
_DIRECTORY_INT_COLUMNS = ("round_lot_size",)

SEC_COLUMNS = ("cik", "ticker", "name")
SEC_MF_FIELDS = ("cik", "seriesId", "classId", "symbol")  # the file's own field names
SEC_MF_COLUMNS = ("cik", "series_id", "class_id", "symbol")
SEC_EXCHANGE_FIELDS = ("cik", "name", "ticker", "exchange")  # the file's fields ARE the columns
TIINGO_FIELDS = ("ticker", "exchange", "assetType", "priceCurrency", "startDate", "endDate")
TIINGO_COLUMNS = ("ticker", "exchange", "asset_type", "price_currency", "start_date", "end_date")


def stooq_symbol(stooq_ticker: str) -> str:
    """``SPY.US`` / ``spy.us`` / ``spy`` → ``SPY``; ``BRK-B.US`` → ``BRK.B``.

    Stooq's ``-`` is the class / unit / warrant separator that Nasdaq's ACT and CQS symbols
    spell ``.`` (``BRK.B``, ``AAC.U``, ``ACHR.WS``) — the ``instrument_master.symbol`` form.
    Stooq's ``_`` marks a preferred series (``AGM_D`` is ``AGM$D`` in the ACT column and
    ``AGM-D`` in the NASDAQ Symbol column); which of those is canonical is build_identity's
    decision, so ``_`` is left untouched and the alias table bridges it.

    Raises ``ValueError`` for anything that is not a Stooq US ticker or file stem.
    """
    s = stooq_ticker.strip().upper()
    if s.endswith(STOOQ_MARKET_SUFFIX):
        s = s[: -len(STOOQ_MARKET_SUFFIX)]
    if not _STOOQ_STEM.match(s):
        raise ValueError(f"not a Stooq US ticker: {stooq_ticker!r}")
    return s.replace("-", ".")


def _snake(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _yes_no(values: list[str], name: str) -> list[bool]:
    unexpected = sorted(set(values) - {"Y", "N"})
    if unexpected:
        raise ValueError(f"{name}: expected Y/N flags, found {unexpected}")
    return [v == "Y" for v in values]


def parse_nasdaq_symbol_directory(text: str) -> pd.DataFrame:
    """``nasdaqlisted.txt`` / ``otherlisted.txt`` → one row per listing.

    Columns follow the file's own header, snake_cased (``symbol … nextshares`` for the
    Nasdaq file, ``act_symbol … nasdaq_symbol`` for the other-exchange file). Y/N flags
    become bool and ``round_lot_size`` int; test issues (Nasdaq's tick-pilot dummies such as
    ``ZAZZT`` / ``ATEST``) are filtered out. The ``File Creation Time`` trailer is REQUIRED
    as the last line — a download cut short has no trailer and must not parse into a
    shorter market (the identity build would delist what is missing). A header this parser
    does not recognise, or a row whose field count differs from the header's, raises
    ``ValueError`` rather than being guessed at.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("symbol directory: empty file")
    if not lines[-1].startswith(_DIRECTORY_TRAILER):
        raise ValueError(
            f"symbol directory: no '{_DIRECTORY_TRAILER}' trailer on the last line — "
            "truncated download?"
        )
    columns = [_snake(h) for h in lines[0].split("|")]
    if columns[0] not in _DIRECTORY_FIRST_COLUMNS or not {"etf", "test_issue"} <= set(columns):
        raise ValueError(f"symbol directory: unrecognised header {lines[0]!r}")
    table: dict[str, list[str]] = {c: [] for c in columns}
    for ln in lines[1:-1]:
        fields = ln.split("|")
        if len(fields) != len(columns):
            raise ValueError(
                f"symbol directory: {len(fields)} fields against {len(columns)} header "
                f"columns: {ln!r}"
            )
        for c, f in zip(columns, fields, strict=True):
            table[c].append(f.strip())
    data: dict[str, list[str] | list[bool] | list[int]] = {}
    for c, values in table.items():
        if c in _DIRECTORY_FLAG_COLUMNS:
            data[c] = _yes_no(values, c)
        elif c in _DIRECTORY_INT_COLUMNS:
            data[c] = [int(v) for v in values]
        else:
            data[c] = values
    keep = [not t for t in data["test_issue"]]
    return pd.DataFrame(data).loc[keep].reset_index(drop=True)  # dict order = header order


def parse_sec_company_tickers(json_text: str) -> pd.DataFrame:
    """``company_tickers.json`` → ``DataFrame[cik, ticker, name]``.

    ``cik`` is the 10-digit zero-padded TEXT that EDGAR URLs and ``instrument_master.cik``
    use (``0000320193`` for Apple) — leading zeros matter, so never an int downstream.
    """
    payload = json.loads(json_text)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("company_tickers.json: expected a non-empty JSON object")
    rows: list[tuple[str, str, str]] = []
    for entry in payload.values():
        try:
            rows.append(
                (
                    _cik(entry["cik_str"], "company_tickers.json"),
                    str(entry["ticker"]).strip().upper(),
                    str(entry["title"]).strip(),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"company_tickers.json: unexpected entry {entry!r}") from e
    return pd.DataFrame.from_records(rows, columns=list(SEC_COLUMNS))


def _cik(value: object, where: str) -> str:
    """CIK as the 10-digit zero-padded TEXT EDGAR uses; anything non-numeric is refused."""
    try:
        return f"{int(str(value)):010d}"
    except (TypeError, ValueError) as e:
        raise ValueError(f"{where}: not a CIK: {value!r}") from e


def _text(value: object) -> str | None:
    """A trimmed, upper-cased ticker-like string; ``None`` for an empty or null field."""
    if value is None:
        return None
    text = str(value).strip()
    return text.upper() or None


def _columnar(json_text: str, name: str, fields: tuple[str, ...]) -> list[list[object]]:
    """The SEC's columnar shape ``{"fields": [...], "data": [[...], …]}`` — the field list
    must be EXACTLY the one verified on 2026-09-04; a reordered or renamed field means the
    SEC changed the file and every column below would be misread."""
    payload = json.loads(json_text)
    if (
        not isinstance(payload, dict)
        or list(payload.get("fields", [])) != list(fields)
        or not isinstance(payload.get("data"), list)
    ):
        raise ValueError(f"{name}: expected fields {list(fields)} and a data list")
    rows = payload["data"]
    bad = [r for r in rows if not isinstance(r, list) or len(r) != len(fields)]
    if bad:
        raise ValueError(f"{name}: {len(bad)} row(s) do not match the field list: {bad[:3]!r}")
    return rows


def parse_sec_company_tickers_mf(json_text: str) -> pd.DataFrame:
    """``company_tickers_mf.json`` → ``DataFrame[cik, series_id, class_id, symbol]``.

    One row per share CLASS of a 1940-Act fund (an ETF has one class, so one row). ``cik``
    is the 10-digit zero-padded text; ``symbol`` is upper-cased (the file carries a few
    lower-case tickers) and ``None`` where the class has none. Unit investment trusts,
    grantor trusts, commodity pools and ETNs (SPY, GLD, USO, …) are not in this file.
    """
    rows = _columnar(json_text, "company_tickers_mf.json", SEC_MF_FIELDS)
    records = [
        (_cik(cik, "company_tickers_mf.json"), _text(series), _text(klass), _text(symbol))
        for cik, series, klass, symbol in rows
    ]
    return pd.DataFrame.from_records(records, columns=list(SEC_MF_COLUMNS))


def parse_sec_company_tickers_exchange(json_text: str) -> pd.DataFrame:
    """``company_tickers_exchange.json`` → ``DataFrame[cik, name, ticker, exchange]``.

    Same issuers as ``company_tickers.json`` plus the listing exchange as the SEC records it
    (``Nasdaq | NYSE | OTC | CBOE`` or ``None``). ``ticker`` keeps the SEC's own hyphen
    spelling (``BRK-B``, ``AGM-PD``); ``cik`` is 10-digit zero-padded text.
    """
    rows = _columnar(json_text, "company_tickers_exchange.json", SEC_EXCHANGE_FIELDS)
    records = [
        (
            _cik(cik, "company_tickers_exchange.json"),
            str(name).strip() if name is not None else None,
            _text(ticker),
            str(exchange).strip() if exchange is not None else None,
        )
        for cik, name, ticker, exchange in rows
    ]
    return pd.DataFrame.from_records(records, columns=list(SEC_EXCHANGE_FIELDS))


def _iso_date(value: str, where: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as e:
        raise ValueError(f"{where}: not a YYYY-MM-DD date: {value!r}") from e


def parse_tiingo_supported_tickers(csv_text: str) -> pd.DataFrame:
    """Tiingo's ``supported_tickers.csv`` → one row per (ticker, listing period) with
    :data:`TIINGO_COLUMNS`; ``start_date`` / ``end_date`` are ``date`` or ``None`` (a
    ticker Tiingo lists without prices carries neither). Tickers are upper-cased; the
    other text columns are kept as the file spells them (``NYSE ARCA``, ``Mutual Fund``).
    The header must be exactly the six columns verified on 2026-09-04.
    """
    reader = csv.reader(io.StringIO(csv_text, newline=""))
    header = next(reader, None)
    if tuple(h.strip() for h in header or ()) != TIINGO_FIELDS:
        raise ValueError(f"supported_tickers.csv: unexpected header {header!r}")
    records: list[tuple[object, ...]] = []
    for row in reader:
        if not row:
            continue
        if len(row) != len(TIINGO_FIELDS):
            raise ValueError(f"supported_tickers.csv: {len(row)} fields in row {row!r}")
        ticker, exchange, asset_type, currency, start, end = (f.strip() for f in row)
        records.append(
            (
                ticker.upper(),
                exchange,
                asset_type,
                currency,
                _iso_date(start, "supported_tickers.csv"),
                _iso_date(end, "supported_tickers.csv"),
            )
        )
    return pd.DataFrame.from_records(records, columns=list(TIINGO_COLUMNS))
