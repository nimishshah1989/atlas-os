#!/usr/bin/env python3
"""FRED macro series → ``atlas_global.macro_daily`` (wide: one row per date, one column per series).

    python scripts/global_market/ingest_macro.py --since 2016-01-04        # the backfill
    python scripts/global_market/ingest_macro.py --eod 2026-09-03           # the nightly (incremental)

Series (plan, "macro_daily"): ``SP500`` (price index — the SPY cross-check, never a displayed
price), ``VIXCLS``, ``DGS10``, ``DTB3`` (the risk-free rate), ``DTWEXBGS``. Column = series id
lower-cased; ``source='fred'``. Values come through ``providers/fred.py:fred_series`` — Decimal,
FRED's missing marker dropped — never India's float ``_fred``.

Key: OPTIONAL. ``config.fred_key()`` returns ``None`` when ``FRED_API_KEY`` is unset, and
``fred_series`` then reads FRED's keyless CSV export instead of the JSON API — the same
observations from the same publisher, so the run is not blocked on a credential. The
transport is printed, recorded in ``ingest_state`` and counted under its OWN
``provider_calls`` endpoint (``graph/fredgraph.csv`` vs ``series/observations``), so the
ledger never claims a call was spent on an API that was never reached.

Calendar: the SPY sessions (``gcal.sessions`` over ``ohlcv_daily`` where the SPY instrument has
bars) in the window. Each session takes the latest observation on or before it — India's
``_ffill_onto`` idea — so a bond-market holiday on a stock-market session (Columbus Day:
DGS10/DTB3 missing, SPY open) carries the prior print, and an observation on a non-session
(Good Friday, when the bond market publishes) is not a row. Two deliberate limits (rule #0):
a session AFTER a series' last observation gets NULL, never yesterday's value stamped as
today's (the SPY-vs-SP500 return correlation in gate A would otherwise see a fake zero return
on the trailing day); and WITHOUT a SPY session calendar for the window the run exits 2
before spending a FRED call — writing FRED's raw dates would be a one-way door (non-session
rows persist forever, beside every later forward-fill). ``--allow-raw-dates`` overrides for
development only, and the log says so.

Window: ``--since`` explicit, else ``max(date)`` in the table minus ``REPULL_DAYS`` (FRED
revises recent prints), else ``HISTORY_START`` (the platform's first session,
``atlas.config.MARKETS["us"]``); capped at ``--eod`` (the anchor). Upsert on ``date``; a NULL
never erases a value already stored (``coalesce``). ``provider_calls`` lands in its own short
transaction right after the fetches (spent budget survives a failed write); ``ingest_state``
commits with the rows. Daily step in ``atlas_global_daily.sh``; the freshness guard allows
three sessions of lag (FRED posts DGS10/DTB3 the next business day).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import _gdb
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from atlas.global_market import calendar as gcal
from atlas.global_market.config import CONFIG, fred_key
from atlas.global_market.providers.fred import CSV_ENDPOINT, JSON_ENDPOINT, fred_series

SOURCE = "fred"
# column → FRED series id
SERIES: dict[str, str] = {s.lower(): s for s in ("SP500", "VIXCLS", "DGS10", "DTB3", "DTWEXBGS")}
COLUMNS: tuple[str, ...] = ("date", *SERIES)
HISTORY_START = date.fromisoformat(CONFIG.history_start)
REPULL_DAYS = (
    14  # allow-threshold: data-quality: refetch window below max(date), FRED revises recent prints
)
# Which FRED door this run used — printed, and the key the spend is recorded under.
TRANSPORT = {JSON_ENDPOINT: "JSON API (FRED_API_KEY set)", CSV_ENDPOINT: "keyless CSV export"}

UPSERT_SQL = f"""
insert into {_gdb.M}.macro_daily (date, {", ".join(SERIES)}, source, ingested_at)
values %s
on conflict (date) do update set
    {", ".join(f"{c} = coalesce(excluded.{c}, macro_daily.{c})" for c in SERIES)},
    source = excluded.source, ingested_at = now()
"""


# ── pure ──


def ffill_onto(sessions: Sequence[date], obs: pd.DataFrame) -> dict[date, Decimal | None]:
    """Each session → the latest observation on or before it; ``None`` before the first
    observation and — deliberately — after the last one (no trailing extrapolation)."""
    obs = obs.sort_values("date", ignore_index=True)
    dates = list(obs["date"])
    values = list(obs["value"])
    out: dict[date, Decimal | None] = {}
    j, last = 0, None
    last_obs = dates[-1] if dates else None
    for d in sessions:
        while j < len(dates) and dates[j] <= d:
            last = values[j]
            j += 1
        out[d] = last if (last_obs is not None and d <= last_obs) else None
    return out


def wide_frame(sessions: Sequence[date], series: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """``DataFrame[COLUMNS]`` over ``sessions`` (or, with none, over the raw observation dates
    of every series — no forward-fill then); rows with no value at all are not rows."""
    if sessions:
        cal = list(sessions)
        cols = {c: ffill_onto(cal, df) for c, df in series.items()}
    else:
        cal = sorted({d for df in series.values() for d in df["date"]})
        cols = {
            c: {d: v for d, v in zip(df["date"], df["value"], strict=True)}
            for c, df in series.items()
        }
    rows = [
        [d, *(cols.get(c, {}).get(d) for c in SERIES)]
        for d in cal
        if any(cols.get(c, {}).get(d) is not None for c in SERIES)
    ]
    return pd.DataFrame.from_records(rows, columns=list(COLUMNS)).astype(object)


# ── DB ──


def spy_sessions(start: date, end: date) -> list[date]:
    df = _gdb.read_df(
        f"select distinct date from {_gdb.M}.ohlcv_daily "
        f"where instrument_id = (select instrument_id from {_gdb.M}.instrument_master "
        "where symbol = 'SPY' and is_active) and date >= :s and date <= :e",
        {"s": start, "e": end},
    )
    return gcal.sessions(df["date"])


def default_since() -> date:
    mx = _gdb.scalar(f"select max(date) from {_gdb.M}.macro_daily")
    return HISTORY_START if mx is None else max(HISTORY_START, mx - timedelta(days=REPULL_DAYS))


def write_rows(cur: Any, frame: pd.DataFrame) -> None:
    execute_values(
        cur,
        UPSERT_SQL,
        [tuple(r) for r in frame.itertuples(index=False, name=None)],
        template="(" + ", ".join(["%s"] * len(COLUMNS)) + f", '{SOURCE}', now())",
        page_size=1000,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--eod", type=date.fromisoformat, default=None, help="default: _gdb.eod_cutoff()"
    )
    ap.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        help="observation_start; default: incremental",
    )
    ap.add_argument(
        "--allow-raw-dates",
        action="store_true",
        help="without SPY sessions, write FRED's raw dates (development only — a one-way door)",
    )
    args = ap.parse_args(argv)
    eod = args.eod or _gdb.eod_cutoff()
    since = args.since or default_since()

    cal = spy_sessions(since, eod)
    if cal:
        print(
            f"  calendar: {len(cal):,d} SPY sessions {cal[0]} → {cal[-1]}; forward-filling onto them"
        )
    elif args.allow_raw_dates:
        print(
            f"  calendar: NO SPY bars in ohlcv_daily for {since} → {eod}; --allow-raw-dates: "
            "writing FRED's raw dates, no forward-fill (development only)"
        )
    else:
        print(
            f"  REFUSED: no SPY session calendar yet for {since} → {eod} — ingest_prices (P1-B) "
            "must land first (raw FRED dates would persist beside every later forward-fill; "
            "--allow-raw-dates overrides, development only); nothing fetched, nothing written"
        )
        return 2

    key = fred_key()
    endpoint = JSON_ENDPOINT if key else CSV_ENDPOINT
    print(f"  transport: {TRANSPORT[endpoint]} → {endpoint}")
    calls: Counter[str] = Counter()
    series: dict[str, pd.DataFrame] = {}
    try:
        for col, sid in SERIES.items():
            calls[endpoint] += 1
            df = fred_series(sid, since, key, end=eod)
            series[col] = df
            span = f"{df['date'].iloc[0]} → {df['date'].iloc[-1]}" if len(df) else "no observations"
            print(f"  {sid:9} {len(df):6,d} obs  {span}")
    finally:  # the budget was spent whatever happens next
        _gdb.commit_provider_calls(eod, {SOURCE: calls})

    frame = wide_frame(cal, series)
    print(f"  {len(frame):,d} rows {since} → {eod}")

    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            write_rows(cur, frame)
            _gdb.record_state(
                cur,
                SOURCE,
                "macro_daily",
                {
                    "since": since.isoformat(),
                    "eod": eod.isoformat(),
                    "rows": len(frame),
                    "sessions": len(cal),
                    "raw_dates": not cal,
                    "endpoint": endpoint,
                    "last_obs": {
                        c: (df["date"].iloc[-1].isoformat() if len(df) else None)
                        for c, df in series.items()
                    },
                    "run_at": datetime.now(UTC).isoformat(),
                },
            )
    finally:
        conn.close()
    print(
        f"  upserted {len(frame):,d} rows into {_gdb.M}.macro_daily "
        f"({sum(calls.values())} FRED calls to {endpoint})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
