#!/usr/bin/env python3
"""S&P 500 membership → ``atlas_global.index_membership`` (+ ``instrument_master.sector_gics``).

    python scripts/global_market/ingest_index_membership.py --eod 2026-09-03 --report idx.csv   # fetch, write
    python scripts/global_market/ingest_index_membership.py --eod 2026-09-03 --history          # + fja05680 spells first
    python scripts/global_market/ingest_index_membership.py --eod 2026-09-03 --dry-run \\
        --offline-dir <dir> --report idx.csv                                                     # saved files, no write

Flow
----
0. **Fetch, then bank the budget.** SPY's workbook, the eleven Select Sector SPDR workbooks
   and (``--history``) the fja05680 ``start_end`` file — live through the providers, or from
   ``--offline-dir`` by their canonical names (``holdings-daily-us-en-<spy|xlk|…>.xlsx``,
   ``sp500_ticker_start_end.csv``) for reruns and rehearsals. The adapters' ``calls`` land in
   ``provider_calls`` in their OWN short transaction before anything else is decided: spent
   budget survives an exit 2 and a rolled-back write.
1. **Gates before any write** (exit 2, nothing written): the file's as-of is not after the
   EOD (the anchor rule) and not OLDER than the as-of last recorded in
   ``ingest_state(source='ssga', key='spy_holdings')`` — a same-day rerun confirms; an older
   file is a stale download unless ``--allow-older-as-of`` says it is a documented rollback;
   the equity rows (ticker AND SEDOL — the cash and contra lines have none) number
   ``MEMBERS_MIN``–``MEMBERS_MAX`` and Σ ``weight_frac`` over the whole file lies in
   ``[WEIGHT_SUM_MIN, WEIGHT_SUM_MAX]`` (docs/global/phase1.md P1-C); at most
   ``MAX_UNRESOLVED_FRAC`` of the ticker rows unresolved; at least ``MIN_SECTOR_MAPPED_FRAC``
   of them in exactly one sector file.
2. **Current constituents** = every row with a ticker; each resolves to the ACTIVE
   ``instrument_master`` row by symbol (SSGA spells class shares as the Nasdaq directory
   does: ``BRK.B``, ``BF.B``), else through ``symbol_alias`` (any source, ``valid_to IS
   NULL``), else it is UNRESOLVED: written to the report with its reason, never dropped
   silently (this script never mints instruments — build_identity.py does).
3. ``--history``: the fja05680 spells windowed to ``[HISTORY_START, as_of)``. A spell
   resolves among ALL ``instrument_master`` rows whose listing window overlaps it (the active
   holder first; a delisted holder for a spell that ended before the live one listed —
   tickers are recycled); none or several → unresolved / ambiguous, reported. Rows carry
   ``source='fja05680'`` and NEVER touch an ``ssga`` interval: a spell that runs into one is
   clipped to end where it starts, one that starts inside it is dropped, and the upsert
   updates only rows whose source is not ``ssga``. The non-``ssga`` rows are RE-DERIVED from
   the file on every history run — an existing row whose ``(instrument_id, effective_from)``
   is not in the new spell set is deleted first: the history is reproducible from the file,
   nothing is lost, and a spell whose start moved upstream cannot leave a second open row.
4. **Then the current pass** (always, so history and today can never disagree): an open
   interval whose instrument is absent from today's file closes at ``as_of`` — the weekly
   OBSERVATION date, up to seven sessions after the true change; a current instrument
   without an open interval opens one at ``as_of``; a current instrument with an open
   interval keeps its ``effective_from`` and takes today's ``weight_frac`` with
   ``source='ssga'`` (SSGA is the authority for the current state; an ``ssga`` row is frozen
   from then on).
5. **Sectors.** ``instrument_master.sector_gics`` for current members — the ONE column of
   instrument_master written outside build_identity.py, and written WITHOUT touching
   ``updated_at`` (build_identity's freshness signal) — comes from MEMBERSHIP of the eleven
   Select Sector SPDR files (``providers/ssga.sector_by_membership``), not from the workbook's
   Sector column, which SSGA leaves ``-``. A member in exactly one sector file gets that
   sector; in none or several it gets NOTHING, a report row with the reason, and a place in
   the printed count of members without a sector.
6. **One transaction** for the rows, then two invariants asserted inside it — no instrument
   has two open intervals; no two intervals of an instrument overlap — and a violation rolls
   everything back. ``ingest_state`` (``ssga/spy_holdings``, ``fja05680/sp500_history``)
   commits with the rows.

The pure pieces (resolution, windowing, planning) live in ``atlas.global_market.index_membership``.
Semantics: ``effective_from`` inclusive, ``effective_to`` EXCLUSIVE (NULL = current) — the
first date the instrument was observed NOT a member. Weekly step in ``atlas_global_weekly.sh``
(with ``--report``); reruns are idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import _gdb
import pandas as pd
import psycopg2
from _report import Report
from psycopg2.extras import execute_values

from atlas.global_market import index_membership as imx
from atlas.global_market.providers import sp500_history as hist
from atlas.global_market.providers.ssga import (
    SECTOR_ETFS,
    SPY,
    SsgaProvider,
    holdings_endpoint,
    parse_holdings,
    parse_sector_holdings,
    sector_by_membership,
)

STATE_KEY = "spy_holdings"
REPORT_COLUMNS = ("pass", "ticker", "instrument_id", "status", "detail")
# Data-quality guards from docs/global/phase1.md P1-C, not methodology: the file must look
# like the S&P 500 (500–505 equity rows, weights summing to ~1) and identity must cover it
# before a single row is written.
MEMBERS_MIN = 500  # allow-threshold: data-quality gate, not methodology
MEMBERS_MAX = 505  # allow-threshold: data-quality gate, not methodology
WEIGHT_SUM_MIN = Decimal("0.99")  # allow-threshold: data-quality gate, not methodology
WEIGHT_SUM_MAX = Decimal("1.01")  # allow-threshold: data-quality gate, not methodology
MAX_UNRESOLVED_FRAC = 0.02  # allow-threshold: ticker rows without an identity row
MIN_SECTOR_MAPPED_FRAC = 0.98  # allow-threshold: ticker rows in exactly one sector file


# ── DB: reads through _gdb, writes on a caller-owned cursor (one transaction in main) ──


def load_identity() -> imx.Identity:
    master = _gdb.read_df(
        f"select instrument_id::text as instrument_id, symbol, is_active, listing_date, delisted_at "
        f"from {_gdb.M}.instrument_master"
    )
    alias = _gdb.read_df(
        f"select source_symbol, instrument_id::text as instrument_id "
        f"from {_gdb.M}.symbol_alias where valid_to is null"
    )
    instruments = [
        imx.Instrument(
            str(i), str(s), bool(a), None if pd.isna(ld) else ld, None if pd.isna(dd) else dd
        )
        for i, s, a, ld, dd in master.itertuples(index=False)
    ]
    aliases = {str(s): str(i) for s, i in alias.itertuples(index=False)}
    return imx.build_identity(instruments, aliases)


def load_existing() -> list[imx.Interval]:
    """EVERY interval of the index, both sources — the planners need the whole picture."""
    df = _gdb.read_df(
        f"select instrument_id::text as instrument_id, effective_from, effective_to, weight_frac, "
        f"source from {_gdb.M}.index_membership where index_code = :c",
        {"c": imx.INDEX_CODE},
    )
    return [
        imx.Interval(
            str(i),
            f,
            None if pd.isna(t) else t,
            None if pd.isna(w) else Decimal(str(w)),
            str(src),
        )
        for i, f, t, w, src in df.itertuples(index=False)
    ]


def stored_as_of() -> date | None:
    """The as-of of the last holdings file written, from ``ingest_state`` — read BEFORE planning."""
    value = _gdb.scalar(
        f"select value->>'as_of' from {_gdb.M}.ingest_state where source = :s and key = :k",
        {"s": imx.SOURCE_CURRENT, "k": STATE_KEY},
    )
    return None if value is None else date.fromisoformat(str(value))


HISTORY_DELETE = (
    f"delete from {_gdb.M}.index_membership where index_code = %s and instrument_id = %s "
    f"and effective_from = %s and source <> '{imx.SOURCE_CURRENT}'"
)
HISTORY_UPSERT = f"""
insert into {_gdb.M}.index_membership
    (index_code, instrument_id, effective_from, effective_to, weight_frac, source, updated_at)
values %s
on conflict (index_code, instrument_id, effective_from) do update set
    effective_to = excluded.effective_to, updated_at = now()
where index_membership.source <> '{imx.SOURCE_CURRENT}'
"""
OPEN_UPSERT = f"""
insert into {_gdb.M}.index_membership
    (index_code, instrument_id, effective_from, effective_to, weight_frac, source, updated_at)
values %s
on conflict (index_code, instrument_id, effective_from) do update set
    effective_to = null, weight_frac = excluded.weight_frac, source = excluded.source,
    updated_at = now()
"""
CLOSE_SQL = (
    f"update {_gdb.M}.index_membership set effective_to = %s, updated_at = now() "
    f"where index_code = %s and instrument_id = %s and effective_from = %s"
)
CONFIRM_SQL = (
    f"update {_gdb.M}.index_membership set weight_frac = %s, source = '{imx.SOURCE_CURRENT}', "
    f"updated_at = now() where index_code = %s and instrument_id = %s and effective_from = %s"
)
# sector_gics only: updated_at stays build_identity's freshness signal.
SECTOR_SQL = f"update {_gdb.M}.instrument_master set sector_gics = %s where instrument_id = %s"
TWO_OPEN_SQL = (
    f"select instrument_id::text, count(*) from {_gdb.M}.index_membership "
    f"where index_code = %s and effective_to is null group by 1 having count(*) > 1"
)
OVERLAP_SQL = f"""
select a.instrument_id::text, a.effective_from, a.effective_to, b.effective_from
from {_gdb.M}.index_membership a
join {_gdb.M}.index_membership b
  on b.index_code = a.index_code and b.instrument_id = a.instrument_id
 and b.effective_from > a.effective_from
where a.index_code = %s and (a.effective_to is null or b.effective_from < a.effective_to)
"""
_ROW = "(%s, %s, %s, %s, %s, %s, now())"


def write_history(cur: Any, plan: imx.HistoryPlan) -> None:
    for iid, eff in plan.deletes:
        cur.execute(HISTORY_DELETE, (imx.INDEX_CODE, iid, eff))
    values = [
        (imx.INDEX_CODE, r.instrument_id, r.effective_from, r.effective_to, None, r.source)
        for r in plan.rows
    ]
    execute_values(cur, HISTORY_UPSERT, values, template=_ROW, page_size=500)


def write_current(cur: Any, plan: imx.CurrentPlan, as_of: date) -> None:
    values = [
        (imx.INDEX_CODE, r.instrument_id, r.effective_from, None, r.weight_frac, r.source)
        for r in plan.opens
    ]
    execute_values(cur, OPEN_UPSERT, values, template=_ROW, page_size=500)
    for iid, eff in plan.closes:
        cur.execute(CLOSE_SQL, (as_of, imx.INDEX_CODE, iid, eff))
    for iid, eff, w in plan.confirms:
        cur.execute(CONFIRM_SQL, (w, imx.INDEX_CODE, iid, eff))


def write_sectors(cur: Any, sectors: Mapping[str, str]) -> None:
    for iid, sector in sectors.items():
        cur.execute(SECTOR_SQL, (sector, iid))


def assert_invariants(cur: Any) -> None:
    """No instrument with two open intervals; no overlapping intervals of one instrument —
    asserted inside the writing transaction, so a violation rolls the whole run back."""
    cur.execute(TWO_OPEN_SQL, (imx.INDEX_CODE,))
    two_open = cur.fetchall()
    cur.execute(OVERLAP_SQL, (imx.INDEX_CODE,))
    overlaps = cur.fetchall()
    if two_open or overlaps:
        raise RuntimeError(
            f"index_membership invariant violated — rolling back: {len(two_open)} instrument(s) "
            f"with two open intervals {two_open[:5]}; {len(overlaps)} overlapping pair(s) "
            f"{overlaps[:5]}"
        )


# ── gates (pure) ──


def holdings_gate(holdings: pd.DataFrame) -> tuple[int, Decimal, list[str]]:
    """``(equity rows, Σ weight_frac, reasons to refuse)``. Equity = ticker AND SEDOL present
    (the cash line has no ticker, a contra/escrow line no SEDOL); the sum is the whole file's."""
    n = int((holdings["ticker"].notna() & holdings["sedol"].notna()).sum())
    total = sum(holdings["weight_frac"], Decimal(0))
    problems: list[str] = []
    if not MEMBERS_MIN <= n <= MEMBERS_MAX:
        problems.append(f"{n} equity rows, outside {MEMBERS_MIN}–{MEMBERS_MAX}")
    if not WEIGHT_SUM_MIN <= total <= WEIGHT_SUM_MAX:
        problems.append(f"Σ weight_frac {total}, outside [{WEIGHT_SUM_MIN}, {WEIGHT_SUM_MAX}]")
    return n, total, problems


def as_of_gate(as_of: date, eod: date, stored: date | None, allow_older: bool) -> str | None:
    """Why the file must be refused, or ``None``: after the EOD (the anchor rule), or older
    than the as-of already recorded (a stale download) unless the rollback flag says so."""
    if as_of > eod:
        return f"holdings as of {as_of} are after the EOD {eod} (the anchor rule)"
    if stored is not None and as_of < stored and not allow_older:
        return (
            f"holdings as of {as_of} are OLDER than the {stored} already recorded in "
            "ingest_state — a stale download (--allow-older-as-of for a documented rollback)"
        )
    return None


# ── resolution over the files ──


def new_report(path: Path | None = None) -> Report:
    """The per-ticker outcome report, counted by ``pass:status`` (``current:resolved`` …)."""
    return Report(path, REPORT_COLUMNS, count_by=("pass", "status"))


def resolve_holdings(
    holdings: pd.DataFrame, ident: imx.Identity, report: Report
) -> tuple[dict[str, Decimal], dict[str, str]]:
    """``(weights by instrument, instrument by ticker)`` over the ticker rows; every row that
    does not resolve is a report row with its reason (``counts['current:unresolved']``)."""
    weights: dict[str, Decimal] = {}
    by_ticker: dict[str, str] = {}
    rows = holdings.loc[holdings["ticker"].notna()]
    for t, w in rows[["ticker", "weight_frac"]].itertuples(index=False):
        ticker = str(t)
        iid, via = imx.resolve_current(ticker, ident)
        if iid is None:
            report.add("current", ticker, None, "unresolved", via)
        elif iid in weights:
            report.add("current", ticker, iid, "unresolved", imx.REASON_DUPLICATE)
        else:
            weights[iid] = w
            by_ticker[ticker] = iid
            report.add("current", ticker, iid, "resolved", via)
    return weights, by_ticker


def resolve_history(
    spells: Sequence[tuple[str, date, date | None]], ident: imx.Identity, report: Report
) -> list[tuple[str, date, date | None]]:
    out: list[tuple[str, date, date | None]] = []
    for ticker, s, e in spells:
        iid, via = imx.resolve_spell(ticker, s, e, ident)
        ambiguous = via.startswith(imx.REASON_AMBIGUOUS)
        status = "resolved" if iid else ("ambiguous" if ambiguous else "unresolved")
        report.add("history", ticker, iid, status, f"{s}→{e or 'open'}: {via}")
        if iid:
            out.append((iid, s, e))
    return out


def sectors_for(
    mapping: pd.DataFrame, by_ticker: Mapping[str, str], report: Report
) -> dict[str, str]:
    """``instrument_id → sector`` for the current members (resolved tickers) in exactly one
    sector file; a member in none or several gets a report row with the reason
    (``counts['sector:unmapped']`` is the printed count of members without a sector)."""
    out: dict[str, str] = {}
    for ticker, sector, etf, matches in mapping[
        ["ticker", "sector_gics", "sector_etf", "matches"]
    ].itertuples(index=False):
        iid = by_ticker.get(str(ticker))
        if iid is None:
            continue  # not a member: reported by the current pass already
        if sector is None:
            reason = "in no sector file" if not matches else "in several: " + ", ".join(matches)
            report.add("sector", str(ticker), iid, "unmapped", reason)
        else:
            out[iid] = str(sector)
            report.add("sector", str(ticker), iid, "mapped", f"{etf} → {sector}")
    return out


# ── files: live through the providers, or saved copies by their canonical names ──


def read_workbook(etf: str, offline_dir: Path | None, ssga: SsgaProvider) -> bytes:
    if offline_dir is not None:
        return (offline_dir / holdings_endpoint(etf)).read_bytes()
    return ssga.fetch_holdings(etf)


def read_start_end(offline_dir: Path | None, fja: hist.Sp500HistoryProvider) -> str:
    if offline_dir is not None:
        return (offline_dir / hist.START_END_ENDPOINT).read_text()
    return fja.fetch_start_end()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--eod", type=date.fromisoformat, default=None, help="default: eod_cutoff()")
    ap.add_argument("--history", action="store_true", help="re-derive the fja05680 spells first")
    ap.add_argument(
        "--offline-dir", type=Path, default=None, help="saved files by their canonical names"
    )
    ap.add_argument("--dry-run", action="store_true", help="resolve + plan; write nothing")
    ap.add_argument("--report", type=Path, default=None, help="CSV of per-ticker outcomes")
    ap.add_argument(
        "--allow-older-as-of",
        action="store_true",
        help="accept a file older than the recorded as-of (a documented rollback only)",
    )
    args = ap.parse_args(argv)
    eod = args.eod or _gdb.eod_cutoff()

    ssga, fja = SsgaProvider(), hist.Sp500HistoryProvider()
    try:
        xlsx = read_workbook(SPY, args.offline_dir, ssga)
        sectors = {
            etf: parse_sector_holdings(read_workbook(etf, args.offline_dir, ssga), etf)
            for etf in SECTOR_ETFS
        }
        start_end = (
            hist.parse_start_end(read_start_end(args.offline_dir, fja)) if args.history else None
        )
    finally:  # the budget was spent whatever happens next
        _gdb.commit_provider_calls(eod, {ssga.name: ssga.calls, fja.name: fja.calls})

    as_of, holdings = parse_holdings(xlsx, SPY)
    n_tickers = int(holdings["ticker"].notna().sum())
    n_equity, total_w, problems = holdings_gate(holdings)
    origin = f"from {args.offline_dir}" if args.offline_dir else "fetched"
    print(
        f"== SSGA SPY holdings as of {as_of} ({origin}): {len(holdings)} rows, {n_tickers} with "
        f"a ticker, {n_equity} equity rows, Σ weight_frac {total_w}; EOD {eod} =="
    )
    stored = stored_as_of()
    refusal = as_of_gate(as_of, eod, stored, args.allow_older_as_of)
    if refusal:
        print(f"  REFUSED: {refusal}; nothing written")
        return 2
    if stored is not None:
        how = "confirms" if as_of == stored else ("advances" if as_of > stored else "ROLLS BACK")
        print(f"  as-of {how} the recorded {stored}")
    if problems:
        print(
            f"  REFUSED: {'; '.join(problems)} — not the S&P 500 as the plan expects it; nothing written"
        )
        return 2
    print(
        f"  gates: {n_equity} equity rows in {MEMBERS_MIN}–{MEMBERS_MAX}, Σ weight_frac {total_w} "
        f"in [{WEIGHT_SUM_MIN}, {WEIGHT_SUM_MAX}]"
    )

    off_date = sorted(e for e, (a, _) in sectors.items() if a != as_of)
    mapping = sector_by_membership(holdings, {e: df for e, (_, df) in sectors.items()})
    n_mapped = int(mapping["sector_gics"].notna().sum())
    print(
        f"  sectors: {n_mapped} of {len(mapping)} ticker rows in exactly one of the "
        f"{len(sectors)} sector files"
        + (f"; as-of differs from SPY in {off_date}" if off_date else "; all as of " + str(as_of))
    )

    report = new_report(args.report)
    try:
        ident = load_identity()
        existing = load_existing()
        print(
            f"  identity: {len(ident.rows):,d} instrument rows, {len(ident.by_alias):,d} aliases; "
            f"{len(existing):,d} existing {imx.INDEX_CODE} intervals"
        )
        history = imx.HistoryPlan([], [], [])
        history_meta: dict[str, Any] = {}
        if start_end is not None:
            known = hist.known_through(start_end)
            if known > as_of:
                print(f"  REFUSED: fja05680 known through {known}, after the holdings {as_of}")
                return 2
            spells = imx.window_spells(start_end, imx.HISTORY_START, as_of)
            resolved = resolve_history(spells, ident, report)
            history = imx.plan_history(resolved, existing)
            for iid, note in history.notes:
                report.add("history", "", iid, "clipped", note)
            print(
                f"  history: {len(start_end):,d} spells in the file, {len(spells):,d} touch "
                f"{imx.HISTORY_START}→{as_of}, {len(resolved):,d} resolved, "
                f"{len(spells) - len(resolved):,d} unresolved/ambiguous, {len(history.notes)} "
                f"clipped/dropped; {len(history.rows)} rows to upsert, {len(history.deletes)} stale "
                f"rows to delete; known through {known}"
            )
            history_meta = {
                "known_through": known.isoformat(),
                "spells": len(spells),
                "resolved": len(resolved),
                "rows": len(history.rows),
                "deleted": len(history.deletes),
            }
            # The current pass plans against what history will have written.
            existing = [iv for iv in existing if iv.source == imx.SOURCE_CURRENT] + history.rows

        weights, by_ticker = resolve_holdings(holdings, ident, report)
        unresolved = n_tickers - len(weights)
        sector_rows = sectors_for(mapping, by_ticker, report)
        n_no_sector = report.counts["sector:unmapped"]
        frac = unresolved / n_tickers if n_tickers else 1.0
        mapped_frac = n_mapped / len(mapping) if len(mapping) else 0.0
        plan = imx.plan_current(weights, existing, as_of)
        where = report.where()
        print(
            f"  current: {len(weights)} resolved, {unresolved} unresolved ({frac:.1%} of "
            f"{n_tickers}); plan: open {len(plan.opens)}, close {len(plan.closes)}, confirm "
            f"{len(plan.confirms)}; sector_gics to write {len(sector_rows)}, members without a "
            f"sector {n_no_sector} {where}"
        )
        if frac > MAX_UNRESOLVED_FRAC:
            print(
                f"  FAIL: {frac:.1%} unresolved > {MAX_UNRESOLVED_FRAC:.0%} {where}; nothing "
                "written (run build_identity.py first — this script never mints instruments)"
            )
            return 2
        if mapped_frac < MIN_SECTOR_MAPPED_FRAC:
            print(
                f"  FAIL: {mapped_frac:.1%} of ticker rows mapped to one sector file "
                f"< {MIN_SECTOR_MAPPED_FRAC:.0%} {where}; nothing written"
            )
            return 2
        if args.dry_run:
            print(f"  dry run — nothing written {where}")
            return 0

        conn = psycopg2.connect(_gdb.psycopg2_url())
        try:
            with conn, conn.cursor() as cur:
                write_history(cur, history)
                write_current(cur, plan, as_of)
                write_sectors(cur, sector_rows)
                assert_invariants(cur)
                _gdb.record_state(
                    cur,
                    imx.SOURCE_CURRENT,
                    STATE_KEY,
                    {
                        "as_of": as_of.isoformat(),
                        "eod": eod.isoformat(),
                        "sha256": hashlib.sha256(xlsx).hexdigest(),
                        "rows": len(holdings),
                        "equity_rows": n_equity,
                        "weight_sum": str(total_w),
                        "resolved": len(weights),
                        "unresolved": unresolved,
                        "opened": len(plan.opens),
                        "closed": len(plan.closes),
                        "confirmed": len(plan.confirms),
                        "sectors_mapped": n_mapped,
                        "sectors_written": len(sector_rows),
                        "members_without_sector": n_no_sector,
                        "sector_as_of_mismatch": off_date,
                        "run_at": datetime.now(UTC).isoformat(),
                    },
                )
                if start_end is not None:
                    _gdb.record_state(cur, imx.SOURCE_HISTORY, "sp500_history", history_meta)
        finally:
            conn.close()
        print(
            f"  written: {len(history.deletes)} stale history rows deleted, {len(history.rows)} "
            f"history rows upserted, {len(plan.opens)} opened, {len(plan.closes)} closed, "
            f"{len(plan.confirms)} confirmed, {len(sector_rows)} sector_gics updates; invariants "
            f"hold {where}"
        )
        return 0
    finally:
        report.close()


if __name__ == "__main__":
    sys.exit(main())
