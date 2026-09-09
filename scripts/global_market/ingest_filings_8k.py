#!/usr/bin/env python3
"""SEC submissions → ``atlas_global.filings_8k`` — the catalyst lens's feed.

    python scripts/global_market/ingest_filings_8k.py                    # nightly increment
    python scripts/global_market/ingest_filings_8k.py --symbols AAPL,VZ --dry-run
    python scripts/global_market/ingest_filings_8k.py --full --report /tmp/8k.csv

WHAT A ROW IS. One 8-K, per instrument: ``(accession_no, instrument_id)``. ``items`` is the SEC
item codes the registrant itself put on the form — ``{2.02, 9.01}`` on a results filing — and
that is the entire signal. The scorer
(``atlas.global_market.scoring.stock_catalyst``) reads those codes and never a headline,
because a keyword rule over press-release prose produces confident nonsense at a rate nobody
measures.

ONE FETCH PER CIK, NOT PER SYMBOL. A dual-class issuer files once and the filing belongs to both
listings (Alphabet's GOOGL and GOOG share CIK 1652044). Fetching by CIK halves the requests for
those names, and the write fans the same accession out to every instrument that CIK maps to —
which is exactly what the table's two-part key is for.

``filed`` IS THE POINT-IN-TIME KEY, not ``period_of_report``. An event on the 1st disclosed on
the 5th was not knowable on the 2nd; the scorer filters on ``filed`` and so does every backtest.
Both are stored, because the gap between them is itself informative, but only one is the clock.

THE HORIZON IS NOT THE SAME FOR EVERY FILER, and this is the finding that shaped the script.
``filings.recent`` is capped at about a thousand rows BY COUNT. Apple files little besides its
own reports, so its window reaches 2015. JPMorgan files prospectuses continuously — 25,985 rows
— and its window is exactly ONE YEAR. The catalyst lookback is ``catalyst_recency_t3`` days
(seeded at 365), so a filer like JPMorgan is only just covered and a heavier one is not. Every
run therefore compares what each feed actually covers against the lookback and REPORTS the
filers that fall short, instead of scoring them on a window that quietly got smaller. The older
batches in ``filings.files`` are not fetched: deeper history is a deliberate request, not a
silent one.

IDENTITY AND RATE. SEC fair access wants a contact ``User-Agent`` and at most ten requests a
second. The identity comes from ``EDGAR_IDENTITY`` (never a literal — this repo is public) and
is read BEFORE the first request, so a missing export costs nobody any budget. Request starts
are spaced by the same ``SEC_MIN_INTERVAL_S`` every other EDGAR reader here uses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
import psycopg2
import requests
from _report import Report
from psycopg2.extras import execute_values

from atlas.db import load_thresholds
from atlas.global_market.config import edgar_identity
from atlas.global_market.providers.directories import SEC_MIN_INTERVAL_S
from atlas.global_market.providers.submissions import parse_submissions, submissions_url

M = _gdb.M
SOURCE = "edgar"  # provider_calls key
SOURCE_LABEL = "edgar"  # filings_8k.source, the DDL's own default
ENDPOINT = "submissions"
TABLE = f"{M}.filings_8k"
CONFLICT_COLUMNS = ["accession_no", "instrument_id"]
COLUMNS = (
    "accession_no",
    "instrument_id",
    "cik",
    "filed",
    "period_of_report",
    "items",
    "description",
    "url",
    "source",
)

#: The forms whose item codes this feed carries. An amendment is a filing that happened and
#: carries its own items, so it is admitted.
FORMS = {"8-K", "8-K/A"}

#: How far back the catalyst lens looks — a table row, never a literal (rule #1). The ingest
#: reads it only to decide which filers' feeds are too shallow to score honestly.
LOOKBACK_KEY = "catalyst_recency_t3"

TIMEOUT = 60

REPORT_COLUMNS = ("cik", "symbols", "filings", "written", "covers_from", "covers_to", "outcome")

STATUS_OK = "ok"
STATUS_SHALLOW = "feed_shallower_than_the_lookback"
STATUS_NO_FILINGS = "no_8k_in_the_feed"
STATUS_FETCH_FAILED = "fetch_failed"

_last_call = [0.0]


# ── targets ───────────────────────────────────────────────────────────────────────────────

# One row per CIK, with every in-universe instrument that CIK maps to. A stock with no CIK
# cannot be asked about at all — build_identity records that, and it is reported, not guessed.
TARGETS_SQL = f"""
SELECT im.cik,
       array_agg(im.instrument_id::text ORDER BY im.symbol) AS instrument_ids,
       string_agg(im.symbol, ',' ORDER BY im.symbol)        AS symbols
FROM {M}.instrument_master im
JOIN {M}.universe_snapshot u
  ON u.instrument_id = im.instrument_id
 AND u.date = (SELECT max(date) FROM {M}.universe_snapshot)
 AND u.in_universe
WHERE im.is_active AND im.asset_class = 'stock' AND im.cik IS NOT NULL
GROUP BY im.cik
ORDER BY im.cik
"""

# The newest filing already stored per CIK — the watermark. Filings at or before it are already
# written and the run skips them; --full ignores this.
WATERMARK_SQL = f"SELECT cik, max(filed) AS filed FROM {TABLE} WHERE cik IS NOT NULL GROUP BY cik"


def targets(symbols: str | None, limit: int | None) -> pd.DataFrame:
    frame = _gdb.read_df(TARGETS_SQL, {})
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        frame = frame.loc[frame["symbols"].apply(lambda s: bool(wanted & set(str(s).split(","))))]
    return frame.head(limit) if limit else frame


def watermarks() -> dict[str, dt.date]:
    frame = _gdb.read_df(WATERMARK_SQL, {})
    return {str(r["cik"]): r["filed"] for r in frame.to_dict("records") if r["filed"] is not None}


def lookback_days() -> int:
    th = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine())
    if LOOKBACK_KEY not in th:
        raise SystemExit(
            f"REFUSED: {M}.atlas_thresholds has no {LOOKBACK_KEY!r}. Run seed_thresholds.py — "
            "the ingest must not invent the window the lens scores over"
        )
    return int(th[LOOKBACK_KEY])


# ── the fetch ─────────────────────────────────────────────────────────────────────────────


def _rate_limit(
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
) -> None:
    """Spaces request STARTS to the SEC's ceiling, so parsing time between calls is not paid
    for twice (a fixed post-call sleep stacks on latency and wastes half the budget)."""
    gap = clock() - _last_call[0]
    if gap < SEC_MIN_INTERVAL_S:
        sleep(SEC_MIN_INTERVAL_S - gap)
    _last_call[0] = clock()


def fetch_submissions(cik: str, identity: str, session: requests.Session) -> Mapping[str, Any]:
    """One filer's submissions document, raw as the SEC serves it."""
    _rate_limit()
    response = session.get(submissions_url(cik), headers={"User-Agent": identity}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


# ── the rows ──────────────────────────────────────────────────────────────────────────────


def filing_rows(
    payload: Mapping[str, Any],
    cik: str,
    instrument_ids: Sequence[str],
    since: dt.date | None,
) -> tuple[list[dict[str, Any]], tuple[dt.date, dt.date] | None]:
    """Every 8-K in the payload filed after ``since``, once per instrument sharing the CIK.

    Returns the rows and the window the FEED covers — which is what the caller compares against
    the lookback, and is a property of the payload rather than of the rows kept.
    """
    subs = parse_submissions(dict(payload), forms=FORMS)
    rows: list[dict[str, Any]] = []
    for f in subs.filings:
        if since is not None and f.filed <= since:
            continue
        for iid in instrument_ids:
            rows.append(
                {
                    "accession_no": f.accession_no,
                    "instrument_id": iid,
                    "cik": cik,
                    "filed": f.filed,
                    "period_of_report": f.period_of_report,
                    # A text[] column: psycopg2 adapts a Python list to a Postgres array.
                    "items": list(f.items),
                    "description": f.description or None,
                    "url": None,
                    "source": SOURCE_LABEL,
                }
            )
    return rows, subs.covers


def write(rows: Sequence[Mapping[str, Any]], dsn: str) -> int:
    """Upsert on ``(accession_no, instrument_id)``. Re-running a day writes the same rows over
    themselves; an amended filing arrives under its OWN accession, so nothing is overwritten by
    a correction that should have been a new row."""
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
            execute_values(cur, sql, [tuple(r[c] for c in COLUMNS) for r in rows], page_size=1000)
    finally:
        conn.close()
    return len(rows)


# ── run ───────────────────────────────────────────────────────────────────────────────────


def run(
    *,
    symbols: str | None,
    limit: int | None,
    full: bool,
    dry_run: bool,
    report: Report | None,
) -> dict[str, int]:
    identity = edgar_identity()  # BEFORE the first request: a missing export costs no budget
    picked = targets(symbols, limit)
    if picked.empty:
        raise SystemExit(
            "REFUSED: no in-universe stock carries a CIK — build_identity.py and "
            "build_universe_snapshot.py must run first"
        )
    lookback = lookback_days()
    today = _gdb.eod_cutoff()
    horizon = today - dt.timedelta(days=lookback)
    marks = {} if full else watermarks()
    print(
        f"[filings_8k] filers={len(picked):,d} watermarks={len(marks):,d} "
        f"{LOOKBACK_KEY}={lookback}d (feeds must reach back to {horizon})"
    )

    calls: Counter[str] = Counter()
    counts: Counter[str] = Counter({"filers": len(picked)})
    batch: list[dict[str, Any]] = []
    session = requests.Session()
    try:
        for r in picked.to_dict("records"):
            cik = str(r["cik"])
            ids = list(r["instrument_ids"])
            calls[ENDPOINT] += 1
            try:
                payload = fetch_submissions(cik, identity, session)
            except (requests.RequestException, ValueError) as exc:
                counts[STATUS_FETCH_FAILED] += 1
                print(f"  {r['symbols']}: {type(exc).__name__}", file=sys.stderr)
                if report:
                    report.add(cik, r["symbols"], 0, 0, None, None, STATUS_FETCH_FAILED)
                continue
            rows, covers = filing_rows(payload, cik, ids, marks.get(cik) if not full else None)
            batch.extend(rows)
            # The horizon check is about the FEED, not about the rows this run kept: a filer
            # already at its watermark writes nothing and its feed may still be too shallow.
            if covers is None:
                outcome = STATUS_NO_FILINGS
            elif covers[0] > horizon:
                outcome = STATUS_SHALLOW
            else:
                outcome = STATUS_OK
            counts[outcome] += 1
            counts["rows"] += len(rows)
            if report:
                report.add(
                    cik,
                    r["symbols"],
                    len(rows) // max(1, len(ids)),
                    len(rows),
                    covers[0] if covers else None,
                    covers[1] if covers else None,
                    outcome,
                )
    finally:
        session.close()
        if calls and not dry_run:
            _gdb.commit_provider_calls(today, {SOURCE: calls})

    shallow = counts[STATUS_SHALLOW]
    if shallow:
        # NOT a failure: the lens still scores those names, on less history than it asked for.
        # It is said out loud because the alternative is a window that silently got smaller.
        print(
            f"[filings_8k] {shallow:,d} filer(s) have a feed shallower than {lookback} days — "
            "filings.recent is capped by COUNT, so a heavy filer's 8-K history is short. Those "
            "names are scored on what the feed reaches, and the report names them."
        )
    if dry_run:
        print(f"[filings_8k] --dry-run: {counts['rows']:,d} row(s) not written")
        return dict(counts)

    written = write(batch, _gdb.psycopg2_url())
    counts["written"] = written
    print(f"[filings_8k] wrote {written:,d} row(s) into {TABLE}")
    return dict(counts)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--symbols", default=None, help="comma-separated symbols; default the universe")
    ap.add_argument("--limit", type=int, default=None, help="stop after N filers (CIKs)")
    ap.add_argument("--full", action="store_true", help="ignore the watermarks and rewrite")
    ap.add_argument("--dry-run", action="store_true", help="fetch and count; write nothing")
    ap.add_argument("--report", type=Path, default=None, help="per-filer CSV: rows and horizon")
    return ap


def main() -> None:
    args = parser().parse_args()
    report = Report(args.report, REPORT_COLUMNS, count_by=("outcome",))
    try:
        run(
            symbols=args.symbols,
            limit=args.limit,
            full=args.full,
            dry_run=args.dry_run,
            report=report,
        )
    finally:
        report.close()


if __name__ == "__main__":
    main()
