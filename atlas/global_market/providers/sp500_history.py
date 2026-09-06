"""fja05680/sp500 — S&P 500 membership history as effective-dated ticker intervals.

Production reads ONE public file from https://github.com/fja05680/sp500
(raw.githubusercontent.com), fetched 2026-09-04 and kept verbatim under
``tests/fixtures/global/index/``:

* ``sp500_ticker_start_end.csv`` — header ``ticker,start_date,end_date``; one row per
  membership SPELL, so a ticker that left and came back has two rows (AAL 1996-01-02 →
  1997-01-15 and 2015-03-23 → 2024-09-23; 52 such tickers); an empty ``end_date`` marks a
  current member. 1,259 rows, 503 current, on the 2026-09-04 fetch.

The repository's second file, ``S&P 500 Historical Components & Changes (Updated).csv``
(``date,tickers``; one row per change date carrying the FULL membership list; 2,718 rows,
1996-01-02 → 2026-06-30), is the cross-check the tests fetch
(``tests/unit/global_market/test_sp500_history.py``): its last row is how far the history is
KNOWN, and :func:`known_through` reads the same date off the start_end file — the latest
start or end date, since the last change is somebody's spell boundary (verified equal on the
2026-09-04 files: 2026-06-30, CAG's departure). The SSGA holdings file carries the state
after that date.

Date semantics, verified row by row on the real files (SIVB, TWTR, ATVI, FRC, WBA, AABA,
AAL): ``start_date`` is INCLUSIVE — the ticker is in the components row dated start_date
and absent from the row before — and ``end_date`` is EXCLUSIVE — absent from the row dated
end_date, present in the row before — i.e. end_date is the first date the ticker was no
longer a member. ``index_membership.effective_from`` / ``effective_to`` carry the same
semantics, so the source maps without date arithmetic.

Caveats the author states: hand-maintained from Wikipedia since 2019; 1996–2001 rows are
incomplete (irrelevant from 2016). Tickers are the spellings of their day (``BRK.B``,
``BF.B``, ``AABA`` for Altaba) and are recycled — DELL 1996 → 2013 is a different company
from DELL 2024 →. Resolving a spell to an instrument is the ingest script's job, with the
spell's dates as evidence; this module parses and derives, and invents nothing.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date

import pandas as pd
import requests

START_END_ENDPOINT = "sp500_ticker_start_end.csv"
START_END_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/" + START_END_ENDPOINT
INTERVAL_COLUMNS: tuple[str, ...] = ("ticker", "start_date", "end_date")
TIMEOUT = 60


class Sp500HistoryProvider:
    """The fetch half: one GET, counted in ``calls`` (a failed request still counts)."""

    name = "fja05680"

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()

    def fetch_start_end(self) -> str:
        self.calls[START_END_ENDPOINT] += 1
        r = requests.get(START_END_URL, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text


def parse_start_end(text: str) -> pd.DataFrame:
    """``DataFrame[ticker, start_date, end_date]`` — one row per spell, file order kept.

    ``end_date`` is ``None`` for a current member. A blank ticker or start, an unparseable
    date, or a spell that ends before it starts is refused (the file is hand-maintained).
    """
    rd = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip() for h in next(rd, [])]
    if header != list(INTERVAL_COLUMNS):
        raise ValueError(f"start_end: header {header} != {list(INTERVAL_COLUMNS)}")
    rows: list[tuple[str, date, date | None]] = []
    for n, r in enumerate(rd, start=2):
        if not r or not any(c.strip() for c in r):
            continue
        if len(r) != 3:
            raise ValueError(f"start_end line {n}: expected 3 fields, got {r}")
        ticker, start, end = (c.strip() for c in r)
        if not ticker or not start:
            raise ValueError(f"start_end line {n}: blank ticker or start_date: {r}")
        s = date.fromisoformat(start)
        e = date.fromisoformat(end) if end else None
        if e is not None and e < s:
            raise ValueError(f"start_end line {n}: {ticker} ends {e} before it starts {s}")
        rows.append((ticker, s, e))
    if not rows:
        raise ValueError("start_end: no rows")
    return pd.DataFrame.from_records(rows, columns=list(INTERVAL_COLUMNS))


def known_through(start_end: pd.DataFrame) -> date:
    """How far the history is known: the latest start or end date in the file (the last
    change date of the components file — the tests assert the two agree)."""
    return max(d for d in [*start_end["start_date"], *start_end["end_date"]] if d is not None)
