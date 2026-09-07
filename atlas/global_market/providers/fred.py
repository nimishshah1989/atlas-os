"""FRED observations → ``DataFrame[date, value]`` — keyed or KEYLESS, one contract.

:func:`fred_series` returns columns ``date`` (:class:`datetime.date`) and ``value``
(:class:`Decimal` — FRED serialises numbers as strings, and a float round-trip is exactly
what ``numeric`` columns are there to avoid), ascending by date, with FRED's
missing-observation marker DROPPED — never zero-filled, never carried forward here (rule #0:
a value we did not receive is not a value) — and raises on any HTTP error.

Two transports behind that one contract:

* ``api_key`` given → the JSON API (``api.stlouisfed.org/fred/series/observations``). It
  stays the PREFERRED path: it carries revision vintages (``realtime_start``/``_end``) and
  series metadata the CSV export has no room for.
* ``api_key`` ``None`` → the KEYLESS CSV export (``fred.stlouisfed.org/graph/fredgraph.csv``),
  the file behind FRED's own "Download → CSV" button. No registration, no key, no quota.

ONE public function with a branch, not a second public name, because which transport runs is
a TRANSPORT detail: a caller asks for a series and gets the contract above either way, and
the invariants (Decimal, missing dropped, ascending, window honoured) are asserted in ONE
place instead of drifting between two copies. The choice is made ONCE, at the edge, by
``config.fred_key()`` returning ``str | None`` — so no call site ever picks a transport, and
handing the FM's key to ``.env`` later moves every caller onto the JSON API with no code
change.

Window. The JSON API takes ``observation_start`` / ``observation_end``. The CSV export takes
``cosd`` / ``coed``, VERIFIED live against the endpoint on 2026-09-07: ``cosd=2026-08-01&
coed=2026-08-15`` returned 2026-08-03 → 2026-08-14 (inclusive bounds, applied server-side,
weekends simply absent), and a ``cosd`` before the series begins returns the series from its
own start rather than an error. The client-side re-filter after parsing is therefore a GUARD,
not a workaround — it makes the window part of THIS function's contract instead of a property
of a URL parameter FRED is free to change.

Missing marker. The JSON API writes ``"."``. The CSV export writes an EMPTY field — verified
on the live endpoint (``DGS10`` on 2026-06-19, Juneteenth: ``2026-06-19,``) and on the
committed export ``tests/fixtures/global/macro/DTB3.csv`` (115 empty values). ``_MISSING``
holds both spellings, so neither transport can turn a day FRED did not publish into a number.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

import pandas as pd
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
JSON_ENDPOINT = "series/observations"  # the labels provider_calls records the spend under
CSV_ENDPOINT = "graph/fredgraph.csv"
_MISSING = frozenset({".", ""})


def _rows(pairs: list[tuple[str, str]]) -> list[tuple[date, Decimal]]:
    """``(date, value)`` strings → typed rows, with FRED's missing observations dropped."""
    out: list[tuple[date, Decimal]] = []
    for raw_date, raw_value in pairs:
        value = (raw_value or "").strip()
        if value in _MISSING:
            continue
        out.append((date.fromisoformat(raw_date.strip()), Decimal(value)))
    return out


def _frame(rows: list[tuple[date, Decimal]]) -> pd.DataFrame:
    return pd.DataFrame.from_records(rows, columns=["date", "value"]).sort_values(
        by="date", ignore_index=True
    )


def parse_fred_csv(text: str, series_id: str) -> pd.DataFrame:
    """FRED's CSV export body → the ``fred_series`` contract. Pure — no I/O.

    The header is checked because an error page served as HTTP 200 must not read as "the
    series has no observations": the export's second column is NAMED for the series, so this
    also proves the response is the series that was asked for.
    """
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None or len(header) != 2 or header[1].strip().upper() != series_id.upper():
        raise ValueError(
            f"fredgraph.csv for {series_id}: expected a 2-column export headed "
            f"'<date>,{series_id}', got {header!r}"
        )
    pairs: list[tuple[str, str]] = []
    for record in reader:
        if not record or not any(field.strip() for field in record):
            continue  # a trailing newline is not a row
        if len(record) != 2:
            raise ValueError(f"fredgraph.csv for {series_id}: row is not date,value: {record!r}")
        pairs.append((record[0], record[1]))
    return _frame(_rows(pairs))


def _window(df: pd.DataFrame, start: date, end: date | None) -> pd.DataFrame:
    """The requested window, enforced client-side on BOTH transports (a guard, not a
    workaround — see the module docstring): the window is this function's contract, not a
    property of whichever URL parameter the endpoint happens to honour."""
    if df.empty:
        return df
    keep = df["date"] >= start
    if end is not None:
        keep &= df["date"] <= end
    return df.loc[keep].reset_index(drop=True)


def fred_series(
    series_id: str,
    start: date,
    api_key: str | None,
    *,
    end: date | None = None,
    timeout: int = 30,
) -> pd.DataFrame:
    """Observations of ``series_id`` from ``start`` (to ``end``, inclusive, if given).

    ``api_key`` selects the transport: a key uses the JSON API, ``None`` the keyless CSV
    export. Returns columns ``date`` (:class:`datetime.date`) and ``value``
    (:class:`Decimal`), ascending by date, missing observations omitted. Raises on any HTTP
    error and on a CSV body that is not the requested series' export.
    """
    if api_key is None:
        params = {"id": series_id, "cosd": start.isoformat()}
        if end is not None:
            params["coed"] = end.isoformat()
        r = requests.get(FRED_CSV_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        return _window(parse_fred_csv(r.text, series_id), start, end)

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
    }
    if end is not None:
        params["observation_end"] = end.isoformat()
    r = requests.get(FRED_BASE, params=params, timeout=timeout)
    r.raise_for_status()
    observations = r.json().get("observations", [])
    frame = _frame(_rows([(o["date"], o.get("value") or "") for o in observations]))
    return _window(frame, start, end)
