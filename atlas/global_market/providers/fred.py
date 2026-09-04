"""FRED observations → ``DataFrame[date, value]``.

Mirrors ``_fred()`` in ``scripts/foundation/ingest_macro.py`` (same endpoint, same params)
with two differences that matter for a numeric column: values stay ``Decimal`` (FRED
serialises them as strings; a float round-trip is exactly what ``numeric`` columns are
there to avoid), and FRED's ``"."`` missing marker is DROPPED — never zero-filled, never
carried forward here (rule #0: a value we did not receive is not a value).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_MISSING = frozenset({".", "", None})


def fred_series(
    series_id: str,
    start: date,
    api_key: str,
    *,
    end: date | None = None,
    timeout: int = 30,
) -> pd.DataFrame:
    """Observations of ``series_id`` from ``start`` (to ``end``, inclusive, if given).

    Returns columns ``date`` (:class:`datetime.date`) and ``value`` (:class:`Decimal`),
    ascending by date, missing observations omitted. Raises on any HTTP error.
    """
    params: dict[str, str] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
    }
    if end is not None:
        params["observation_end"] = end.isoformat()
    r = requests.get(FRED_BASE, params=params, timeout=timeout)
    r.raise_for_status()
    rows = [
        (date.fromisoformat(o["date"]), Decimal(o["value"]))
        for o in r.json().get("observations", [])
        if o.get("value") not in _MISSING
    ]
    return pd.DataFrame.from_records(rows, columns=["date", "value"]).sort_values(
        by="date", ignore_index=True
    )
