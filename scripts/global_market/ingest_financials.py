#!/usr/bin/env python3
"""SEC EDGAR XBRL company facts → ``atlas_global.stock_financials_pit`` (point-in-time).

    python scripts/global_market/ingest_financials.py                     # nightly increment
    python scripts/global_market/ingest_financials.py --symbols AAPL,JPM --dry-run
    python scripts/global_market/ingest_financials.py --full --report /tmp/fin.csv

``filed`` IS THE KEY, and it is the reason this table exists rather than a "latest financials"
one. A row is ``(instrument_id, period_end, form, filed)``. When a company restates a quarter,
the restated figure arrives as a NEW row with a later ``filed`` and the original is never
touched, so a backtest asking "what did the market know on 2023-05-12" reads
``filed <= '2023-05-12'`` and gets the numbers that were actually on file — not today's
corrected ones. Writing this table as an upsert on ``(instrument_id, period_end)`` would
delete exactly the evidence it is for.

WHERE THE HALVES SPLIT. Turning a payload into periods is pure and lives in
``atlas.global_market.fundamentals.facts`` — including the rule that resolves the one real
ambiguity (several durations end on the same date; a row takes the filing's OWN period class,
year for a 10-K and quarter for a 10-Q, and year-to-date durations are dropped). Read that
module's docstring for what a row is and what the feed does not carry. THIS file is the off-box
half: which filers to ask about, the SEC request, the watermark, the columns and the write.

INCREMENTAL AND IDEMPOTENT. Company facts is one request per filer for the entire history, so
the fetch cost does not change with the window; what changes is the write. Each filer's stored
``max(filed)`` is the watermark and only rows filed after it are written (``--full`` rewrites
everything, e.g. after this map gains a tag). Re-running the same day writes the same rows over
themselves. The spend lands in ``provider_calls`` in its own transaction the moment the fetches
end, so an exit at a later gate never un-spends it.

IDENTITY AND RATE. SEC fair access wants a contact ``User-Agent`` and at most 10 requests a
second. The identity comes from ``EDGAR_IDENTITY`` (never a literal — this repo is public);
``atlas.global_market.config.edgar_identity`` refuses a value without an ``@`` in it, and it is
read BEFORE the first request so a missing export costs nobody any budget. Request starts are
spaced by the same ``SEC_MIN_INTERVAL_S`` the identity fetch uses, so the two EDGAR readers can
never disagree about the ceiling.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, _report (siblings)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package

import _gdb
import pandas as pd
import psycopg2
from _report import Report
from psycopg2.extras import execute_values

from atlas.db import load_thresholds
from atlas.global_market.config import edgar_identity
from atlas.global_market.fundamentals import metrics
from atlas.global_market.fundamentals.facts import (
    PeriodRow,
    extract_rows,
    quarter_count,
    tag_summary,
)
from atlas.global_market.providers.directories import SEC_MIN_INTERVAL_S

M = _gdb.M
SOURCE = "edgar"  # provider_calls / ingest_state key
SOURCE_LABEL = "edgar_xbrl"  # stock_financials_pit.source, the DDL's own default
ENDPOINT = "api/xbrl/companyfacts"
TABLE = f"{M}.stock_financials_pit"
CONFLICT_COLUMNS = ["instrument_id", "period_end", "form", "filed"]
# The FM's floor for "this name can carry a fundamental lens" — a table row, never a literal
# (seeded by seed_thresholds.py; P3-A's definition of done is >=95% of members above it).
MIN_QUARTERS_KEY = "fund_min_quarters"

GICS_FINANCIALS = "Financials"  # instrument_master.sector_gics, from Select Sector SPDR (XLF)

# concept (xbrl_map) → stock_financials_pit column. ONE definition, in the module that reads
# the table back (``fundamentals.metrics``), so a rename cannot leave the writer and the
# reader disagreeing. ``total_debt`` is this file's own: it is the SUM of the two debt
# components below, not a concept xbrl_map extracts, so it is dropped from what is written
# per-concept and written separately.
CONCEPT_COLUMNS: dict[str, str] = {
    concept: column
    for concept, column in metrics.CONCEPT_COLUMNS.items()
    if concept != "total_debt"
}
DEBT_CONCEPTS = ("debt_long", "debt_short")  # summed into the table's single total_debt column
DB_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "period_end",
    "form",
    "filed",
    "fiscal_year",
    "fiscal_period",
    "period_start",
    "accession_no",
    *CONCEPT_COLUMNS.values(),
    "total_debt",
    "is_financial_co",
)

STATUS_WRITTEN = "written"
STATUS_UNCHANGED = "unchanged"
STATUS_NO_CIK = "no_cik"
STATUS_NO_FACTS = "no_facts"
STATUS_NO_ROWS = "no_rows"
STATUS_FETCH_FAILED = "fetch_failed"
FAILURE_STATUSES = (STATUS_NO_CIK, STATUS_NO_FACTS, STATUS_NO_ROWS, STATUS_FETCH_FAILED)
REPORT_COLUMNS = (
    "symbol",
    "cik",
    "instrument_id",
    "status",
    "quarters",
    "annuals",
    "rows_written",
    "first_period",
    "last_period",
    "latest_filed",
    "tags",
    "detail",
)


# ── the table's records ───────────────────────────────────────────────────────────────────


def db_rows(
    rows: Sequence[PeriodRow], instrument_id: str, *, is_financial: bool
) -> list[dict[str, Any]]:
    """:class:`PeriodRow` objects → ``stock_financials_pit`` records.

    ``total_debt`` is the sum of the long- and short-term components the filer reported: the
    table carries one debt column, and a company with debt it filed under only one of the two
    elements has that much debt, not none. Absent both, the column stays NULL.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        debt = [row.values[c] for c in DEBT_CONCEPTS if c in row.values]
        record: dict[str, Any] = {
            "instrument_id": instrument_id,
            "period_end": row.period_end,
            "form": row.form,
            "filed": row.filed,
            "fiscal_year": row.fiscal_year,
            "fiscal_period": row.fiscal_period,
            "period_start": row.period_start,
            "accession_no": row.accession_no,
            "total_debt": sum(debt, Decimal(0)) if debt else None,
            "is_financial_co": is_financial,
        }
        for concept, column in CONCEPT_COLUMNS.items():
            record[column] = row.values.get(concept)
        out.append(record)
    return out


# ── database ──────────────────────────────────────────────────────────────────────────────

ANCHOR_SQL = f"SELECT max(date) AS d FROM {M}.universe_snapshot WHERE date <= :cutoff"

# The current S&P 500 members: in-universe stocks on the latest snapshot at or before the EOD.
# Membership is the universe (phase2 D3) — there is no separate "is an S&P 500 member" filter.
TARGETS_SQL = f"""
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.cik, im.sector_gics
FROM {M}.universe_snapshot us
JOIN {M}.instrument_master im USING (instrument_id)
WHERE us.date = :anchor AND us.in_universe AND im.asset_class = 'stock' AND im.is_active
ORDER BY im.symbol
"""

WATERMARK_SQL = f"""
SELECT instrument_id::text AS instrument_id, max(filed) AS latest_filed
FROM {TABLE} GROUP BY instrument_id
"""

# Written by hand rather than through _gdb.upsert_df because the run's watermark
# (``ingest_state``) has to commit in the SAME transaction as the rows it describes — the
# ingest_macro / ingest_prices pattern. A watermark that survives a rolled-back write claims
# a history that is not there. ``ingested_at`` refreshes on every touch so the freshness guard
# sees a re-run; ``source`` is the DDL's own default, spelled once here.
UPSERT_SQL = f"""
insert into {TABLE} ({", ".join(DB_COLUMNS)}, source, ingested_at)
values %s
on conflict ({", ".join(CONFLICT_COLUMNS)}) do update set
    {", ".join(f"{c} = excluded.{c}" for c in DB_COLUMNS if c not in CONFLICT_COLUMNS)},
    ingested_at = now()
"""


def anchor_date(cutoff: dt.date) -> dt.date:
    frame = _gdb.read_df(ANCHOR_SQL, {"cutoff": cutoff})
    day = frame["d"].iloc[0] if not frame.empty else None
    if day is None:
        raise SystemExit(
            f"{M}.universe_snapshot holds nothing at or before {cutoff} — run "
            "build_universe_snapshot.py first; the members of the index are its output"
        )
    return day


def targets(anchor: dt.date, symbols: str | None, limit: int | None) -> pd.DataFrame:
    frame = _gdb.read_df(TARGETS_SQL, {"anchor": anchor})
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        frame = pd.DataFrame(frame[frame["symbol"].isin(sorted(wanted))])
        missing = wanted - set(frame["symbol"])
        if missing:
            raise SystemExit(
                f"REFUSED: not in the {anchor} universe as active stocks: {', '.join(sorted(missing))}"
            )
    return pd.DataFrame(frame.head(limit)) if limit else frame


def watermarks() -> dict[str, dt.date]:
    frame = _gdb.read_df(WATERMARK_SQL)
    return dict(zip(frame["instrument_id"], frame["latest_filed"], strict=True))


def min_quarters() -> int:
    """The coverage floor from ``atlas_thresholds`` — absent means the seed has not run, and
    that is a refusal, not a default (rule #1: no methodology number lives in this file)."""
    value = load_thresholds(_gdb.SCHEMA, engine=_gdb.engine()).get(MIN_QUARTERS_KEY)
    if value is None:
        raise SystemExit(
            f"REFUSED: {M}.atlas_thresholds has no active {MIN_QUARTERS_KEY} — run "
            "`python scripts/global_market/seed_thresholds.py` (FM approval first)"
        )
    return int(value)


# ── fetching ──────────────────────────────────────────────────────────────────────────────

_last_call = [0.0]


def _rate_limit(
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
) -> None:
    """Min-interval limiter: spaces request STARTS to the SEC's ceiling regardless of how long
    the parsing between calls took (a fixed post-call sleep stacks on top of latency and
    wastes half the budget — ``scripts/foundation/ingest_kite.py``). The interval is
    ``providers/directories``' own, so the two EDGAR readers share ONE number."""
    gap = clock() - _last_call[0]
    if gap < SEC_MIN_INTERVAL_S:
        sleep(SEC_MIN_INTERVAL_S - gap)
    _last_call[0] = clock()


def fetch_facts(cik: str) -> Mapping[str, Any]:
    """One filer's whole company-facts payload, raw as SEC serves it.

    ``edgartools`` owns the transport (contact header, retry, its own throttle and disk
    cache); this takes the raw dict rather than its parsed objects so the extraction above
    runs identically on the payloads committed under ``tests/fixtures/global/edgar/``.
    """
    from edgar.entity.entity_facts import download_company_facts_from_sec

    _rate_limit()
    return download_company_facts_from_sec(int(cik))


# ── run ───────────────────────────────────────────────────────────────────────────────────


def run(
    *,
    eod: dt.date,
    symbols: str | None,
    limit: int | None,
    full: bool,
    dry_run: bool,
    report: Report | None,
) -> dict[str, int]:
    from edgar import set_identity
    from edgar.entity import CompanyFactsNotFoundError

    set_identity(edgar_identity())  # BEFORE the first request: a missing export costs no budget
    anchor = anchor_date(eod)
    picked = targets(anchor, symbols, limit)
    if picked.empty:
        raise SystemExit(
            f"REFUSED: no in-universe stock on {anchor} — build_universe_snapshot.py must run first"
        )
    floor = min_quarters()
    marks = {} if full else watermarks()
    print(
        f"[financials] anchor={anchor} filers={len(picked):,d} "
        f"watermarks={len(marks):,d} {MIN_QUARTERS_KEY}={floor}"
    )

    calls: Counter[str] = Counter()
    frames: list[dict[str, Any]] = []
    counts = Counter({"attempted": len(picked)})
    try:
        for row in picked.to_dict("records"):
            counts.update(
                _one_filer(row, marks, floor, frames, calls, report, CompanyFactsNotFoundError)
            )
    finally:  # the budget was spent whatever the run decides next
        _gdb.commit_provider_calls(eod, {SOURCE: calls})

    print(f"  {len(frames):,d} row(s) to write over {counts['filers_written']:,d} filer(s)")
    if dry_run:
        print("  --dry-run: nothing written")
    else:
        write(frames, eod, anchor, counts)
        print(f"  upserted {len(frames):,d} row(s) into {TABLE}")
    _summarise(counts, report, calls, floor)
    return dict(counts)


def write(
    records: Sequence[Mapping[str, Any]], eod: dt.date, anchor: dt.date, counts: Counter[str]
) -> None:
    """The rows and the run's watermark, in ONE transaction — both or neither."""
    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            if records:
                execute_values(
                    cur,
                    UPSERT_SQL,
                    [tuple(r[c] for c in DB_COLUMNS) for r in records],
                    template="("
                    + ", ".join(["%s"] * len(DB_COLUMNS))
                    + f", '{SOURCE_LABEL}', now())",
                    page_size=1000,
                )
            _gdb.record_state(
                cur,
                SOURCE,
                "stock_financials_pit",
                {
                    "eod": eod.isoformat(),
                    "universe_anchor": anchor.isoformat(),
                    "filers_attempted": counts["attempted"],
                    "filers_written": counts["filers_written"],
                    "rows": len(records),
                    "quarter_rows": counts["quarter_rows"],
                    "annual_rows": counts["annual_rows"],
                    "short_history": counts["short_history"],
                    "failures": {s: counts[s] for s in FAILURE_STATUSES if counts[s]},
                    "run_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            )
    finally:
        conn.close()


def _one_filer(
    row: Mapping[str, Any],
    marks: Mapping[str, dt.date],
    floor: int,
    frames: list[dict[str, Any]],
    calls: Counter[str],
    report: Report | None,
    not_found: type[Exception],
) -> Counter[str]:
    """Fetch, extract and stage one filer; returns the counters its outcome moves.

    One filer's failure is a reported outcome, never the end of the run: the other 502 members
    are still worth writing, and the report names what went wrong for each name that did not.
    """
    symbol, cik, iid = row["symbol"], row.get("cik"), row["instrument_id"]

    def outcome(status: str, detail: str, **cells: Any) -> Counter[str]:
        """One report line — the empty columns spelled once, not at every exit."""
        if report is not None:
            report.add(
                symbol,
                cik,
                iid,
                status,
                cells.get("quarters", 0),
                cells.get("annuals", 0),
                cells.get("rows_written", 0),
                cells.get("first_period"),
                cells.get("last_period"),
                cells.get("latest_filed"),
                cells.get("tags", ""),
                detail,
            )
        return Counter({status: 1})

    if not cik:
        return outcome(STATUS_NO_CIK, "no CIK on instrument_master")
    try:
        calls[ENDPOINT] += 1
        payload = fetch_facts(str(cik))
    except not_found:
        return outcome(STATUS_NO_FACTS, "SEC has no XBRL facts for this CIK")
    except Exception as exc:
        return outcome(STATUS_FETCH_FAILED, f"{type(exc).__name__}: {exc}")

    rows = extract_rows(payload)
    if not rows:
        return outcome(STATUS_NO_ROWS, "no mapped concept in any period")

    quarters = quarter_count(rows)
    since = marks.get(iid)
    fresh = [r for r in rows if since is None or r.filed > since]
    records = db_rows(fresh, iid, is_financial=row.get("sector_gics") == GICS_FINANCIALS)
    frames.extend(records)
    status = STATUS_WRITTEN if records else STATUS_UNCHANGED
    counts = outcome(
        status,
        "" if records else f"nothing filed after {since}",
        quarters=quarters,
        annuals=sum(r.is_annual for r in rows),
        rows_written=len(records),
        first_period=rows[0].period_end,
        last_period=rows[-1].period_end,
        latest_filed=max(r.filed for r in rows),
        tags=tag_summary(rows),
    )
    counts["history_quarters"] += quarters
    counts["short_history"] += int(quarters < floor)
    counts["filers_written"] += int(bool(records))
    counts["rows"] += len(records)
    counts["quarter_rows"] += sum(1 for r in fresh if not r.is_annual)
    counts["annual_rows"] += sum(1 for r in fresh if r.is_annual)
    return counts


def _summarise(
    counts: Counter[str], report: Report | None, calls: Counter[str], floor: int
) -> None:
    """The one line that says what the run did, and the one that says what it could not.

    ``short_history`` counts each filer's WHOLE filed history, not the rows this run happened
    to write, so an incremental night reports the same coverage as a backfill would.
    """
    failures = " ".join(f"{s}={counts[s]:,d}" for s in FAILURE_STATUSES if counts[s])
    print(
        f"[financials] filers attempted={counts['attempted']:,d} "
        f"written={counts['filers_written']:,d} unchanged={counts[STATUS_UNCHANGED]:,d} | "
        f"rows={counts['rows']:,d} (quarters {counts['quarter_rows']:,d} / "
        f"annuals {counts['annual_rows']:,d}) | "
        f"filers with < {floor} quarters on file={counts['short_history']:,d} | "
        f"{sum(calls.values()):,d} EDGAR call(s)"
    )
    print(f"  failures: {failures or 'none'}")
    if report is not None:
        print(f"  {sum(report.counts.values()):,d} outcome(s) {report.where()}")


def parser() -> argparse.ArgumentParser:
    """The CLI, reachable from a test without a database or a network."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--eod", type=dt.date.fromisoformat, default=None, help="default: _gdb.eod_cutoff()"
    )
    ap.add_argument("--limit", type=int, default=None, help="first N filers (smoke test)")
    ap.add_argument("--symbols", default=None, help="comma-separated subset, e.g. AAPL,MSFT")
    ap.add_argument("--report", type=Path, default=None, help="per-filer CSV: what was picked")
    ap.add_argument(
        "--full", action="store_true", help="ignore the stored watermarks and rewrite every row"
    )
    ap.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = Report(args.report, REPORT_COLUMNS) if args.report else None
    try:
        run(
            eod=args.eod or _gdb.eod_cutoff(),
            symbols=args.symbols,
            limit=args.limit,
            full=args.full,
            dry_run=args.dry_run,
            report=report,
        )
    finally:
        if report is not None:
            report.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
