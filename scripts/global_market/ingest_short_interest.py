#!/usr/bin/env python3
"""FINRA consolidated short interest → ``atlas_global.short_interest`` — the flow lens's feed.

    python scripts/global_market/ingest_short_interest.py                 # new settlements only
    python scripts/global_market/ingest_short_interest.py --dates 2026-08-14 --dry-run
    python scripts/global_market/ingest_short_interest.py --backfill 2017-01-01 --report /tmp/si.csv

ONE REQUEST PER PAGE, FIVE PAGES PER SETTLEMENT. The dataset is PARTITIONED BY ``settlementDate``
— FINRA rejects a sorted query unless every partition key is pinned with an EQUAL filter — so a
run asks for one settlement at a time and pages through it. A settlement is about 22,500 rows at
5,000 a page, and the response headers carry ``record-total`` and ``record-max-limit``, so the
page count is read rather than guessed. Twice-monthly settlements make the nightly cost ten
requests a month; a nine-year backfill is roughly a thousand.

THE FILTER MUST GO IN A POST BODY. The same JSON in the query string is rejected: it has to be
URL-encoded there, and getting that wrong fails as a 400 that names neither the cause nor the fix.

WHAT IS STORED IS WHAT FINRA PUBLISHED. ``days_to_cover`` and ``change_percent`` are FINRA's own
arithmetic, written as they came rather than recomputed, so the lens reads the same figures the
regulator did and the journal can be reconciled against the source. ``split_flag`` and
``revision_flag`` come along because a split between settlements makes two share counts
incomparable and a revision is a different fact from the original.

ONLY SYMBOLS THIS BOARD KNOWS ARE WRITTEN. A settlement covers every listed US equity, most of
which are not in ``instrument_master``. Unmatched symbols are COUNTED and reported, never
invented as instruments: identity is ``build_identity.py``'s job and this script must not create
a row it cannot explain.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import psycopg2
import requests
from _report import Report
from psycopg2.extras import execute_values

from atlas.global_market.providers.finra import (
    DATASET_URL,
    ShortInterest,
    parse_short_interest,
)

M = _gdb.M
SOURCE = "finra"  # provider_calls key and the table's own source label
ENDPOINT = "consolidatedShortInterest"
TABLE = f"{M}.short_interest"
CONFLICT_COLUMNS = ["instrument_id", "settlement_date"]
COLUMNS = (
    "instrument_id",
    "settlement_date",
    "short_interest",
    "avg_daily_volume",
    "days_to_cover",
    "previous_short_interest",
    "change_percent",
    "split_flag",
    "revision_flag",
    "source",
)

#: FINRA's own ceiling, echoed in the ``record-max-limit`` response header. Asking for more is
#: silently truncated to this, which would drop two thirds of a settlement without an error.
PAGE = 5000
TIMEOUT = 120
#: The SEC's ceiling does not apply here, but hammering a free public API does not become polite
#: because it is allowed. One request every fifth of a second is plenty for ~1,000 of them.
MIN_INTERVAL_S = 0.2

REPORT_COLUMNS = ("settlement_date", "rows_returned", "matched", "unmatched", "written", "outcome")

STATUS_OK = "ok"
STATUS_EMPTY = "no_rows_for_this_settlement"
STATUS_FETCH_FAILED = "fetch_failed"

_last_call = [0.0]


# ── which settlements to ask for ───────────────────────────────────────────────────────────

# Every settlement already stored. The feed is append-only in practice — FINRA republishes a
# settlement only to revise it — so a stored date is skipped unless --backfill asks for it again.
STORED_SQL = f"SELECT DISTINCT settlement_date FROM {TABLE} ORDER BY settlement_date"

# symbol → instrument_id for the stocks this board knows. instrument_master is the only authority
# on identity; a FINRA symbol that matches nothing here is counted, not created.
SYMBOLS_SQL = f"""
SELECT im.symbol, im.instrument_id::text AS instrument_id
FROM {M}.instrument_master im
WHERE im.is_active AND im.asset_class = 'stock'
"""


def stored_settlements() -> set[dt.date]:
    frame = _gdb.read_df(STORED_SQL, {})
    return {r["settlement_date"] for r in frame.to_dict("records")}


def known_symbols() -> dict[str, str]:
    frame = _gdb.read_df(SYMBOLS_SQL, {})
    return {str(r["symbol"]).upper(): str(r["instrument_id"]) for r in frame.to_dict("records")}


# ── the fetch ──────────────────────────────────────────────────────────────────────────────


def _rate_limit(
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
) -> None:
    gap = clock() - _last_call[0]
    if gap < MIN_INTERVAL_S:
        sleep(MIN_INTERVAL_S - gap)
    _last_call[0] = clock()


def fetch_settlement(
    settled: dt.date, session: requests.Session, calls: Counter[str]
) -> list[dict[str, Any]]:
    """Every row FINRA holds for one settlement date, across as many pages as it takes.

    The page count comes from the ``record-total`` header rather than from "keep going until a
    short page": a page that happens to land exactly on the boundary would end the loop early and
    the shortfall would look like a quiet settlement.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while total is None or offset < total:
        _rate_limit()
        calls[ENDPOINT] += 1
        response = session.post(
            DATASET_URL,
            json={
                "limit": PAGE,
                "offset": offset,
                "compareFilters": [
                    {
                        "fieldName": "settlementDate",
                        "fieldValue": settled.isoformat(),
                        "compareType": "EQUAL",
                    }
                ],
            },
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError(f"{settled}: expected a list of rows, got {type(page).__name__}")
        rows.extend(page)
        if total is None:
            header = response.headers.get("record-total")
            total = int(header) if header and header.isdigit() else len(page)
        offset += PAGE
        if not page:
            break
    return rows


# ── the rows ───────────────────────────────────────────────────────────────────────────────


def interest_rows(
    readings: Iterable[ShortInterest], by_symbol: Mapping[str, str]
) -> tuple[list[dict[str, Any]], int]:
    """Readings for symbols this board knows, and how many were left unmatched.

    The unmatched count is the point of returning it: a settlement covers every listed US equity
    and most of them are not in this universe, so "22,000 rows in, 500 written" is the expected
    shape rather than a sign of a broken join.
    """
    out: list[dict[str, Any]] = []
    unmatched = 0
    for r in readings:
        iid = by_symbol.get(r.symbol)
        if iid is None:
            unmatched += 1
            continue
        out.append(
            {
                "instrument_id": iid,
                "settlement_date": r.settlement_date,
                "short_interest": None if r.short_shares is None else int(r.short_shares),
                "avg_daily_volume": None
                if r.average_daily_volume is None
                else int(r.average_daily_volume),
                "days_to_cover": r.days_to_cover,
                "previous_short_interest": None
                if r.previous_short_shares is None
                else int(r.previous_short_shares),
                "change_percent": r.change_percent,
                "split_flag": r.split_flag,
                "revision_flag": r.is_revision,
                "source": SOURCE,
            }
        )
    return out, unmatched


def write(rows: Sequence[Mapping[str, Any]], dsn: str) -> int:
    """Upsert on ``(instrument_id, settlement_date)``. A revision republishes the same settlement
    with different figures, and it must land on top of the original rather than beside it."""
    if not rows:
        return 0
    updates = ", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c not in CONFLICT_COLUMNS)
    sql = (
        f"INSERT INTO {TABLE} ({', '.join(COLUMNS)}) VALUES %s "
        f"ON CONFLICT ({', '.join(CONFLICT_COLUMNS)}) DO UPDATE SET {updates}"
    )
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            execute_values(cur, sql, [tuple(r[c] for c in COLUMNS) for r in rows], page_size=2000)
    finally:
        conn.close()
    return len(rows)


def settlements_to_fetch(
    known: set[dt.date], dates: str | None, backfill: dt.date | None, today: dt.date
) -> list[dt.date]:
    """Which settlement dates this run asks FINRA for.

    ``--dates`` names them outright. ``--backfill`` re-asks for every candidate since a date,
    stored or not. Otherwise: the candidates of the last ninety days that are not stored yet —
    settlements are the 15th and the last day of each month, and FINRA publishes about eight
    business days later, so a fortnight's window would miss one that arrived late.
    """
    if dates:
        return sorted({dt.date.fromisoformat(d.strip()) for d in dates.split(",") if d.strip()})
    start = backfill or (today - dt.timedelta(days=90))
    candidates = [d for d in settlement_calendar(start, today)]
    return candidates if backfill else [d for d in candidates if d not in known]


def settlement_calendar(start: dt.date, end: dt.date) -> list[dt.date]:
    """The 15th and the last day of every month in the range.

    FINRA settles on those two dates; when one falls on a weekend the published settlement date is
    the day itself, not a shifted one, so no calendar adjustment is made here. A date FINRA does
    not hold simply returns no rows, which the run records as an empty settlement rather than as
    a failure — asking is cheaper than modelling the exchange calendar for it.
    """
    out: list[dt.date] = []
    year, month = start.year, start.month
    while dt.date(year, month, 1) <= end:
        mid = dt.date(year, month, 15)
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        last = nxt - dt.timedelta(days=1)
        out.extend(d for d in (mid, last) if start <= d <= end)
        year, month = nxt.year, nxt.month
    return sorted(out)


# ── run ────────────────────────────────────────────────────────────────────────────────────


def run(
    *,
    dates: str | None,
    backfill: dt.date | None,
    dry_run: bool,
    report: Report | None,
) -> dict[str, int]:
    by_symbol = known_symbols()
    if not by_symbol:
        raise SystemExit(
            "REFUSED: instrument_master holds no active stock — build_identity.py must run first"
        )
    today = _gdb.eod_cutoff()
    wanted = settlements_to_fetch(stored_settlements(), dates, backfill, today)
    if not wanted:
        print("[short_interest] every candidate settlement is already stored — nothing to do")
        return {"settlements": 0, "written": 0}
    print(
        f"[short_interest] {len(wanted)} settlement(s) to fetch, "
        f"{wanted[0]} .. {wanted[-1]}; {len(by_symbol):,d} known stock symbol(s)"
    )

    calls: Counter[str] = Counter()
    counts: Counter[str] = Counter({"settlements": len(wanted)})
    batch: list[dict[str, Any]] = []
    session = requests.Session()
    try:
        for settled in wanted:
            try:
                raw = fetch_settlement(settled, session, calls)
            except (requests.RequestException, ValueError) as exc:
                counts[STATUS_FETCH_FAILED] += 1
                print(f"  {settled}: {type(exc).__name__}", file=sys.stderr)
                if report:
                    report.add(settled, 0, 0, 0, 0, STATUS_FETCH_FAILED)
                continue
            rows, unmatched = interest_rows(parse_short_interest(raw), by_symbol)
            batch.extend(rows)
            outcome = STATUS_OK if raw else STATUS_EMPTY
            counts[outcome] += 1
            counts["rows"] += len(rows)
            counts["unmatched"] += unmatched
            print(f"  {settled}: {len(raw):,d} row(s), {len(rows):,d} matched, {unmatched:,d} not")
            if report:
                report.add(settled, len(raw), len(rows), unmatched, len(rows), outcome)
    finally:
        session.close()
        if calls and not dry_run:
            _gdb.commit_provider_calls(today, {SOURCE: calls})

    if dry_run:
        print(f"[short_interest] --dry-run: {counts['rows']:,d} row(s) not written")
        return dict(counts)
    written = write(batch, _gdb.psycopg2_url())
    counts["written"] = written
    print(f"[short_interest] wrote {written:,d} row(s) into {TABLE}")
    return dict(counts)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--dates", default=None, help="comma-separated settlement dates to fetch")
    ap.add_argument(
        "--backfill",
        type=dt.date.fromisoformat,
        default=None,
        help="re-fetch every settlement since this date, stored or not",
    )
    ap.add_argument("--dry-run", action="store_true", help="fetch and count; write nothing")
    ap.add_argument("--report", type=Path, default=None, help="per-settlement CSV")
    return ap


def main() -> None:
    args = parser().parse_args()
    report = Report(args.report, REPORT_COLUMNS, count_by=("outcome",))
    try:
        run(dates=args.dates, backfill=args.backfill, dry_run=args.dry_run, report=report)
    finally:
        report.close()


if __name__ == "__main__":
    main()
