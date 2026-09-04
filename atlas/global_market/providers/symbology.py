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
  fair-access rule wants a ``User-Agent`` carrying a contact address).
"""

from __future__ import annotations

import json
import re

import pandas as pd

STOOQ_MARKET_SUFFIX = ".US"
# base, any number of "-x" segments (class / unit / warrant), an optional "_y" (preferred).
_STOOQ_STEM = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*(_[A-Z0-9]*)?$")

_DIRECTORY_TRAILER = "File Creation Time"
_DIRECTORY_FIRST_COLUMNS = ("symbol", "act_symbol")
_DIRECTORY_FLAG_COLUMNS = ("etf", "test_issue", "nextshares")
_DIRECTORY_INT_COLUMNS = ("round_lot_size",)

SEC_COLUMNS = ("cik", "ticker", "name")


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
    become bool and ``round_lot_size`` int; the ``File Creation Time`` trailer is dropped and
    test issues (Nasdaq's tick-pilot dummies such as ``ZAZZT`` / ``ATEST``) are filtered out.
    A header this parser does not recognise, or a row whose field count differs from the
    header's, raises ``ValueError`` rather than being guessed at.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("symbol directory: empty file")
    columns = [_snake(h) for h in lines[0].split("|")]
    if columns[0] not in _DIRECTORY_FIRST_COLUMNS or not {"etf", "test_issue"} <= set(columns):
        raise ValueError(f"symbol directory: unrecognised header {lines[0]!r}")
    table: dict[str, list[str]] = {c: [] for c in columns}
    for ln in lines[1:]:
        if ln.startswith(_DIRECTORY_TRAILER):
            continue
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
                    f"{int(entry['cik_str']):010d}",
                    str(entry["ticker"]).strip().upper(),
                    str(entry["title"]).strip(),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"company_tickers.json: unexpected entry {entry!r}") from e
    return pd.DataFrame.from_records(rows, columns=list(SEC_COLUMNS))
