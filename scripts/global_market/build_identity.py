#!/usr/bin/env python3
"""Build ``atlas_global.instrument_master`` + ``symbol_alias`` from the REAL directories.

    python scripts/global_market/build_identity.py --snapshot-dir /tmp/identity/2026-09-04
    python scripts/global_market/build_identity.py --from-snapshot tests/fixtures/global/symbology \\
        --stooq-zip ~/Downloads/d_us_txt.zip --dry-run --report /tmp/identity.csv

The weekly identity step and ``instrument_master``'s ONLY writer. Flow:

1. Fetch (``providers/directories.py`` — the only network here) or read a saved snapshot
   (``--from-snapshot``): Nasdaq Trader ``nasdaqlisted.txt`` + ``otherlisted.txt``, SEC
   ``company_tickers.json`` / ``company_tickers_mf.json`` (+ the optional
   ``company_tickers_exchange.json``), Tiingo ``supported_tickers.zip``. A fetch saves every
   file with its sha256 into ``--snapshot-dir`` (keeping the newest ``--keep`` dated
   snapshots beside it) and records the requests in ``provider_calls`` at once, in their own
   transaction — spent budget is a fact whether or not the build below is written.
2. Assemble the desired frame (``atlas.global_market.identity_frame``): ETF flag, exchange
   per the file's legend, CIK / series / class from the SEC files (cross-file conflicts and
   name disagreements recorded), listing date from Tiingo (else the run date) — and MEASURE
   the coverage (printed every run).
3. Diff against the table (``atlas.global_market.identity_plan``): match active rows by
   symbol, update identity columns in place, pair renames (same registrant, unambiguous),
   deactivate what left the directory (never ``source='manual'`` rows), mint a NEW
   instrument for a recycled ticker, reactivate a same-key or flickered row; Stooq archive
   members absent from the directory (``--stooq-zip``) become inactive rows under the
   fallback key with ``delisted_at`` = their last bar. A plan that would deactivate more
   than the planner's cap (2 percent of the active rows or 200, whichever is smaller) is
   REFUSED — exit 2, nothing written — unless ``--allow-mass-deactivation`` is passed.
4. Write everything in ONE transaction: deactivations first (they free the active-symbol
   slot), then renames, reactivations, inserts, in-place updates, ``updated_at`` touches,
   alias closes and inserts, and ``ingest_state(source='identity', key='last_run')``.
   ``--dry-run`` plans, reports and prints, and writes nothing.

The report CSV (``--report``) has one row per directory listing, deactivated row and archive
member (``identity_plan.REPORT_COLUMNS``): symbol, asset_class, exchange, cik, series_id,
key_kind (cik | fallback), action (insert | rename | reactivate | update | deactivate |
unchanged), aliases, note, sec_conflict, name_agrees.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from contextlib import closing
from dataclasses import astuple
from datetime import UTC, date, datetime
from itertools import batched
from pathlib import Path
from typing import Any

import _gdb
import _report
import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlas.global_market import identity as ident
from atlas.global_market import identity_frame as frame_mod
from atlas.global_market import identity_plan as plan_mod
from atlas.global_market.providers import directories as dirs
from atlas.global_market.providers.stooq_bulk import (
    ADJUSTMENT_UNKNOWN,
    ArchiveMember,
    StooqBulkProvider,
)
from atlas.global_market.providers.symbology import (
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers,
    parse_sec_company_tickers_exchange,
    parse_sec_company_tickers_mf,
    parse_tiingo_supported_tickers,
)

M = _gdb.M
STATE_SOURCE = "identity"
STATE_KEY = "last_run"
MEMBER_CHUNK = 500  # archive members read per provider call when spanning their bars
EXIT_REFUSED = 2

DEACTIVATE_SQL = f"""
update {M}.instrument_master m
   set is_active = false, delisted_at = v.delisted_at::date, updated_at = now()
  from (values %s) as v(instrument_id, delisted_at)
 where m.instrument_id = v.instrument_id::uuid
"""
INSERT_SQL = f"insert into {M}.instrument_master ({', '.join(plan_mod.ROW_COLUMNS)}) values %s"
# Renames and reactivations write rows whose id IS on file; a fresh uuid that conflicts is a
# planner bug and must fail on the primary key, so plain inserts never use this statement.
UPSERT_SQL = (
    INSERT_SQL
    + """
on conflict (instrument_id) do update set
    symbol = excluded.symbol, asset_class = excluded.asset_class, name = excluded.name,
    exchange = excluded.exchange, cik = excluded.cik, series_id = excluded.series_id,
    class_id = excluded.class_id, listing_date = excluded.listing_date,
    delisted_at = excluded.delisted_at, is_active = excluded.is_active,
    source = excluded.source, updated_at = now()
"""
)
UPDATE_SQL = f"""
update {M}.instrument_master m
   set asset_class = v.asset_class, name = v.name, exchange = v.exchange, cik = v.cik,
       series_id = v.series_id, class_id = v.class_id, listing_date = v.listing_date::date,
       updated_at = now()
  from (values %s) as v(instrument_id, {", ".join(plan_mod.IDENTITY_COLUMNS)})
 where m.instrument_id = v.instrument_id::uuid
"""
TOUCH_SQL = (
    f"update {M}.instrument_master set updated_at = now() where instrument_id = any(%s::uuid[])"
)
ALIAS_CLOSE_SQL = f"""
update {M}.symbol_alias a
   set valid_to = v.valid_to::date
  from (values %s) as v(source, source_symbol, instrument_id, valid_to)
 where a.source = v.source and a.source_symbol = v.source_symbol
   and a.instrument_id = v.instrument_id::uuid and a.valid_to is null
"""
ALIAS_INSERT_SQL = f"""
insert into {M}.symbol_alias (source, source_symbol, valid_from, instrument_id, note) values %s
on conflict (source, source_symbol, valid_from) do update set
    instrument_id = excluded.instrument_id, note = excluded.note, valid_to = null
"""
STATE_SQL = f"""
insert into {M}.ingest_state (source, key, value, updated_at) values (%s, %s, %s, now())
on conflict (source, key) do update set value = excluded.value, updated_at = now()
"""
COUNTS_SQL = f"""
select count(*) filter (where is_active) as active, count(*) as total,
       (select count(*) from {M}.symbol_alias where valid_to is null) as open_aliases
  from {M}.instrument_master
"""


# ── 1. files ──


def assemble(snap: dirs.Snapshot, run_date: date) -> tuple[pd.DataFrame, frozenset[str], dict]:
    """Parse the snapshot and build the desired frame; return it with the set of tickers
    proven present in Tiingo's list (US exchange, USD) and the measured coverage."""
    nasdaq = parse_nasdaq_symbol_directory(snap.text(dirs.NASDAQ_LISTED))
    other = parse_nasdaq_symbol_directory(snap.text(dirs.OTHER_LISTED))
    frame = frame_mod.directory_frame(nasdaq, other)
    exchange = None
    if dirs.SEC_COMPANY_TICKERS_EXCHANGE in snap.files:
        exchange = parse_sec_company_tickers_exchange(snap.text(dirs.SEC_COMPANY_TICKERS_EXCHANGE))
    else:
        print(
            f"  WARNING: {dirs.SEC_COMPANY_TICKERS_EXCHANGE} absent — CIKs from the two other SEC files"
        )
    frame = frame_mod.attach_sec(
        frame,
        parse_sec_company_tickers(snap.text(dirs.SEC_COMPANY_TICKERS)),
        parse_sec_company_tickers_mf(snap.text(dirs.SEC_COMPANY_TICKERS_MF)),
        exchange,
    )
    csv_text = snap.tiingo_csv()
    if csv_text is None:
        listings = pd.DataFrame({"ticker": [], "start_date": []})
        print(
            f"  WARNING: {dirs.TIINGO_SUPPORTED_TICKERS} absent — listing dates fall to the run date"
        )
    else:
        listings = frame_mod.tiingo_listings(parse_tiingo_supported_tickers(csv_text))
    frame = frame_mod.attach_listing_dates(frame, listings, run_date)
    return frame, frozenset(listings["ticker"]), frame_mod.coverage(frame)


# ── 2. archive members ──


def archive_members(
    provider: StooqBulkProvider, directory_symbols: set[str]
) -> tuple[list[dict[str, Any]], list[ArchiveMember], list[ArchiveMember]]:
    """Split the archive into members whose canonical symbol the directory lists and the
    rest; span the rest's bars (first / last date). Returns (absent members as planner
    rows, present members, members the Stooq grammar cannot canonicalise)."""
    present: list[ArchiveMember] = []
    absent: list[ArchiveMember] = []
    unspellable: list[ArchiveMember] = []
    canonical: dict[str, str] = {}
    for m in provider.members():
        symbol = ident.canonical_from_stooq(m.stooq_ticker)
        if symbol is None:
            unspellable.append(m)
            continue
        canonical[m.symbol] = symbol
        (present if symbol in directory_symbols else absent).append(m)
    spans: dict[str, tuple[date, date]] = {}
    for chunk in batched(absent, MEMBER_CHUNK):
        bars = provider.bars([m.symbol for m in chunk], date.min, date.max, ADJUSTMENT_UNKNOWN)
        if not bars.empty:
            agg = bars.groupby("symbol")["date"].agg(["min", "max"])
            spans.update(
                zip(agg.index.astype(str), zip(agg["min"], agg["max"], strict=True), strict=True)
            )
    rows = []
    for m in absent:
        first, last = spans.get(m.symbol, (None, None))
        rows.append(
            {
                "symbol": canonical[m.symbol],
                "stooq_ticker": m.stooq_ticker,
                "asset_class": m.kind,
                "exchange": m.exchange,
                "first_bar": first,
                "last_bar": last,
            }
        )
    return rows, present, unspellable


# ── 3. the table as it is ──


def load_existing() -> list[dict[str, Any]]:
    df = _gdb.read_df(
        f"select instrument_id::text as instrument_id, {', '.join(plan_mod.ROW_COLUMNS[1:])} "
        f"from {M}.instrument_master"
    )
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


def load_open_aliases() -> dict[tuple[str, str], str]:
    df = _gdb.read_df(
        f"select source, source_symbol, instrument_id::text as instrument_id "
        f"from {M}.symbol_alias where valid_to is null"
    )
    return df.set_index(["source", "source_symbol"])["instrument_id"].to_dict()


# ── 4. write ──


def record_calls(run_date: date, provider: dirs.DirectoryProvider) -> None:
    """``provider_calls`` for this fetch, per provider, in its OWN short transaction — the
    budget is spent whether or not the build below commits."""
    by_provider: dict[str, Counter[str]] = {}
    for name, (prov, _url) in dirs.FILES.items():
        if provider.calls[dirs.endpoint(name)]:
            by_provider.setdefault(prov, Counter())[dirs.endpoint(name)] += provider.calls[
                dirs.endpoint(name)
            ]
    with closing(psycopg2.connect(_gdb.psycopg2_url())) as conn, conn, conn.cursor() as cur:
        for prov, calls in by_provider.items():
            _gdb.record_provider_calls(cur, run_date, prov, calls)


def apply(plan: plan_mod.Plan, run_date: date, state: dict[str, Any]) -> None:
    """One transaction, in dependency order; nothing is written when any step fails."""

    def rows(full: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [tuple(r[c] for c in plan_mod.ROW_COLUMNS) for r in full]

    with closing(psycopg2.connect(_gdb.psycopg2_url())) as conn, conn, conn.cursor() as cur:
        if plan.deactivations:
            execute_values(
                cur,
                DEACTIVATE_SQL,
                [(r["instrument_id"], r["delisted_at"]) for r in plan.deactivations],
            )
        if plan.renames:
            execute_values(cur, UPSERT_SQL, rows(plan.renames))
        if plan.reactivations:
            execute_values(cur, UPSERT_SQL, rows(plan.reactivations))
        if plan.inserts:
            execute_values(cur, INSERT_SQL, rows(plan.inserts), page_size=1000)
        if plan.updates:
            execute_values(
                cur,
                UPDATE_SQL,
                [
                    (r["instrument_id"], *(r[c] for c in plan_mod.IDENTITY_COLUMNS))
                    for r in plan.updates
                ],
            )
        if plan.touches:
            cur.execute(TOUCH_SQL, (plan.touches,))
        if plan.alias_closes:
            execute_values(
                cur, ALIAS_CLOSE_SQL, [(s, v, i, run_date) for s, v, i in plan.alias_closes]
            )
        if plan.alias_inserts:
            execute_values(
                cur,
                ALIAS_INSERT_SQL,
                [(s, v, run_date, i, n or None) for s, v, i, n in plan.alias_inserts],
                page_size=1000,
            )
        cur.execute(STATE_SQL, (STATE_SOURCE, STATE_KEY, Json(state)))


def default_report_dir() -> Path:
    """``$ATLAS_LOG_DIR`` — the orchestrators' log directory (scripts/ops/atlas_global_*.sh
    read the same variable) — else ``<repo>/logs/global``."""
    env = os.environ.get("ATLAS_LOG_DIR", "").strip()
    return Path(env) if env else Path(__file__).resolve().parents[2] / "logs" / "global"


def write_report(path: Path | None, plan: plan_mod.Plan) -> _report.Report:
    """The per-row report through the shared writer (``_report.Report``): one CSV row per
    ``ReportRow``, counted by action. With no path nothing is written, only counted."""
    report = _report.Report(path, plan_mod.REPORT_COLUMNS, count_by=("action",))
    for row in plan.report:
        report.add(*astuple(row))
    report.close()
    return report


# ── 5. the run ──


def _pct(n: int, d: int) -> str:
    return f"{n:,d}/{d:,d} ({100.0 * n / d:.1f}%)" if d else f"{n:,d}/0"


def print_coverage(c: dict[str, int]) -> None:
    print(
        f"  directory: {c['rows']:,d} listings — {c['etf_rows']:,d} ETFs, "
        f"{c['stock_rows']:,d} stock-flagged; exchange on {_pct(c['rows_with_exchange'], c['rows'])}"
    )
    print(
        f"  SEC identity: stocks {_pct(c['stock_cik'], c['stock_rows'])}; "
        f"ETFs {_pct(c['etf_cik'], c['etf_rows'])} — mf {c['etf_cik_via_mf']:,d}, "
        f"company_tickers {c['etf_cik_via_company_tickers']:,d}, exchange file "
        f"{c['cik_via_exchange_file']:,d}; series/class {_pct(c['etf_series'], c['etf_rows'])}"
    )
    print(
        f"  SEC cross-file CIK conflicts: {c['sec_conflicts']:,d}; directory name vs SEC title: "
        f"{c['name_disagreements']:,d} of {c['names_checked']:,d} disagree (see the report)"
    )
    print(
        f"  listing dates: tiingo {_pct(c['listing_date_tiingo'], c['rows'])}, "
        f"run date {c['rows'] - c['listing_date_tiingo']:,d}"
    )


def print_plan(plan: plan_mod.Plan) -> None:
    counts = plan.counts()
    print(
        "  plan: "
        + ", ".join(f"{k} {v:,d}" for k, v in counts.items() if not k.startswith("alias"))
        + f"; aliases: insert {counts['alias_insert']:,d}, close {counts['alias_close']:,d}"
    )
    by_source = Counter(s for s, _v, _i, _n in plan.alias_inserts)
    if by_source:
        print(
            "  alias inserts by source: "
            + ", ".join(f"{s} {n:,d}" for s, n in sorted(by_source.items()))
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build atlas_global.instrument_master + symbol_alias")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--snapshot-dir", type=Path, help="fetch, then save every file + sha256 here")
    src.add_argument("--from-snapshot", type=Path, help="offline: read a saved snapshot directory")
    ap.add_argument(
        "--keep",
        type=int,
        default=8,
        help="fetch mode: keep the newest N dated snapshot directories beside --snapshot-dir",
    )
    ap.add_argument(
        "--stooq-zip", type=Path, default=None, help="Stooq d_us_txt.zip (survivorship rows)"
    )
    ap.add_argument(
        "--run-date", type=date.fromisoformat, default=None, help="default: _gdb.eod_cutoff()"
    )
    ap.add_argument(
        "--allow-mass-deactivation",
        action="store_true",
        help="override the planner's cap on deactivations (only after checking the files)",
    )
    ap.add_argument("--dry-run", action="store_true", help="plan + report + print; write nothing")
    ap.add_argument(
        "--report",
        type=Path,
        default=None,
        help="CSV of per-row outcomes (default: build_identity_<run date>.csv next to the "
        "snapshot, or in the working directory; --dry-run writes one only when asked)",
    )
    args = ap.parse_args()

    t0 = time.monotonic()
    run_date = args.run_date or _gdb.eod_cutoff()
    pruned: list[str] = []
    if args.from_snapshot:
        snap = dirs.read_snapshot(args.from_snapshot)
        mode = f"snapshot {args.from_snapshot} ({snap.provenance})"
    else:
        provider = dirs.DirectoryProvider()
        snap = provider.fetch_all()
        mode = "fetched"
        if args.snapshot_dir:
            dirs.write_snapshot(args.snapshot_dir, snap)
            pruned = [p.name for p in dirs.prune_snapshots(args.snapshot_dir.parent, args.keep)]
            mode += f", saved to {args.snapshot_dir}"
        if not args.dry_run:
            record_calls(run_date, provider)
    print(f"== build_identity run_date={run_date} ({mode}){' DRY RUN' if args.dry_run else ''} ==")
    for name in snap.files:
        print(f"  {name:32s} sha256={snap.sha256s[name][:16]}… fetched {snap.fetched_at[name]}")
    if pruned:
        print(f"  pruned {len(pruned)} older snapshot(s): {', '.join(pruned)}")

    desired, tiingo_tickers, coverage = assemble(snap, run_date)
    print_coverage(coverage)

    members: list[dict[str, Any]] = []
    present: list[ArchiveMember] = []
    archive: dict[str, Any] = {}
    if args.stooq_zip:
        stooq = StooqBulkProvider(args.stooq_zip)
        members, present, unspellable = archive_members(stooq, set(desired["symbol"]))
        empty = sum(1 for m in members if m["first_bar"] is None)
        archive = {
            "members": len(present) + len(members) + len(unspellable),
            "in_directory": len(present),
            "archive_only": len(members),
            "archive_only_empty": empty,
            "unspellable": [m.stooq_ticker for m in unspellable],
        }
        print(
            f"  archive {args.stooq_zip.name}: {archive['members']:,d} members — "
            f"{len(present):,d} in the directory, {len(members):,d} archive-only "
            f"({empty} empty files), {len(unspellable)} without a canonical spelling"
        )

    existing = load_existing()
    open_aliases = load_open_aliases()
    print(
        f"  table before: {len(existing):,d} rows ({sum(1 for r in existing if r['is_active']):,d} active)"
    )
    try:
        plan = plan_mod.plan(
            desired.to_dict("records"),
            members,
            existing,
            open_aliases,
            tiingo_tickers,
            run_date,
            allow_mass_deactivation=args.allow_mass_deactivation,
        )
    except plan_mod.MassDeactivationError as e:
        print(f"== REFUSED: {e} — nothing written ==")
        return EXIT_REFUSED
    if args.stooq_zip:
        wanted = {v for s, v, _i, _n in plan.alias_inserts if s == ident.SOURCE_STOOQ} | {
            v for (s, v), _i in open_aliases.items() if s == ident.SOURCE_STOOQ
        }
        matched = sum(1 for m in present if m.stooq_ticker in wanted)
        archive["alias_matches_member"] = matched
        print(
            f"  stooq alias = archive member for {_pct(matched, len(present))} of the listed members"
        )
    print_plan(plan)

    # A live run always leaves its report: next to the snapshot when one is saved, else in
    # the log directory (never the working directory — a cron has none and a laptop checkout
    # is a public repository); a dry run only when asked.
    report = args.report
    if report is None and not args.dry_run:
        report = (args.snapshot_dir or default_report_dir()) / f"build_identity_{run_date}.csv"
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
    print(f"  report: {len(plan.report):,d} row outcomes {write_report(report, plan).where()}")

    if args.dry_run:
        print(f"== dry run complete in {time.monotonic() - t0:,.0f}s — nothing written ==")
        return 0

    state = {
        "run_date": run_date.isoformat(),
        "mode": mode,
        "provenance": snap.provenance,
        "files": {
            n: {"sha256": snap.sha256s[n], "fetched_at": snap.fetched_at[n]} for n in snap.files
        },
        "snapshots_pruned": pruned,
        "coverage": coverage,
        "archive": archive,
        "counts": plan.counts(),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    apply(plan, run_date, state)
    after = _gdb.read_df(COUNTS_SQL).iloc[0]
    print(
        f"== done in {time.monotonic() - t0:,.0f}s: instrument_master {int(after['total']):,d} rows "
        f"({int(after['active']):,d} active); symbol_alias {int(after['open_aliases']):,d} open =="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
