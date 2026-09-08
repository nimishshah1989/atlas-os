#!/usr/bin/env python3
"""Import the FM's Stooq bulk archive (``d_us_txt.zip``) into ``atlas_global.ohlcv_daily``.

    python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip --dry-run
    python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip --symbols SPY,AAPL,BRK.B
    python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip --since 2016-01-01

Flow
----
1. List the archive — ``StooqBulkProvider.members()``: symbol, kind, exchange, size and zip
   CRC per price file (the folder names carry kind and exchange).
2. Identity bridge — each member maps to ONE ``instrument_master`` row: by
   ``symbol_alias(source='stooq', source_symbol=<TICKER>.US, valid_to IS NULL)`` first, else
   by ``instrument_master.symbol = symbology.stooq_symbol(<ticker>)`` (``SPY.US → SPY``,
   ``BRK-B.US → BRK.B``). The importer never mints an instrument — ``build_identity.py`` is
   ``instrument_master``'s only writer. Unmapped members are COUNTED and written to the
   report file with a reason; nothing is dropped silently.
3. Bars — ``open/high/low/close/volume`` from the file; ``source='stooq_csv'``;
   ``close_adj`` NULL; ``close_tr`` and ``adjustment_source`` from the MEASURED basis
   (see "Labelling the adjustment", below). A row that is not a valid bar
   (a price ≤ 0, high < low, open/close outside [low, high]) is refused and listed in the
   report by symbol and date; the FM's archive has about a hundred such rows in 28 million.
4. Upsert — ``ON CONFLICT (instrument_id, date) DO UPDATE … WHERE ohlcv_daily.source <> 'alpaca'``:
   a row Alpaca wrote is never overwritten (protected rows are counted and printed).
5. Resume — ``ingest_state(source='stooq_csv', key=<symbol>)`` records the member's CRC/size
   and the ``--since`` it was imported with. A rerun skips members whose fingerprint matches
   and whose stored window covers the requested one, so an interrupted import continues where
   it stopped and a newer archive re-imports only the files that changed.

``--dry-run`` parses the whole archive through the same code path and prints the report
without writing to the database; when ``ATLAS_DB_URL`` is configured it also runs the
identity bridge (read-only) and prints how many members map, by alias and by symbol, so
``build_identity.py``'s coverage can be checked before any bar is written.

Labelling the adjustment (replaces the Alpaca-labelling TODO this file used to carry)
------------------------------------------------------------------------------------
The old plan was a ``stooq_adjustment_check`` labelling each file against Alpaca
``adjustment=split`` / ``=all``. It never ran, and cheaper evidence now exists:
``validate_global.py --check BASIS`` MEASURES the basis from the stored bars against FRED's
SP500 price index — an unrelated publisher, no key, dividends absent by construction.

So this importer decides nothing about the archive; it ASKS, via
:func:`measured_total_return`, and labels from the answer. Gate passes → ``close_tr`` = the
file's close under ``stooq:total_return``. Gate does not pass, or cannot run → ``close_tr``
NULL under ``stooq:unknown``, said loudly; ``price_basis.basis_of`` resolves nothing for that
label, so ``compute_technicals.py`` skips and lists those instruments rather than score bars
whose meaning nobody established.

That is what stops a STALE label. Were Stooq to switch to a split-only series, no run could
go on stamping ``total_return``: the measurement is redone whenever bars are written or
relabelled, and the nightly BASIS gate re-measures and withholds the publish. A constant in
the code would have kept looking right and being wrong. ``close_adj`` stays NULL on Stooq
rows either way — split-only prices cannot be recovered from a total-return series without
the dividend events, and inventing them is the derived number rule #0 forbids.

A per-instrument Alpaca cross-check is still worth having (the FRED measurement is SPY-wide;
one mislabelled file would not show in it) and is left to ``ingest_prices.py`` — as a
confirmation now, not the labelling itself.
"""

from __future__ import annotations

# allow-large: one archive, one importer — parse, identity-bridge, validate, label, upsert and
# resume are the SAME transaction's concerns, and the docstring above carries the provenance
# rules the FM audits. This file was 533 lines before the basis work; the +121 are the
# measured-label path (measured_total_return, --relabel) and the reasoning for it. Splitting
# the labelling into a sibling module would put the label in a different file from the write
# it justifies, which is the coupling this script exists to keep visible.
import argparse
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import _gdb
import pandas as pd
import psycopg2
from _report import Report
from psycopg2.extras import Json, execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlas.global_market.price_basis import STOOQ_TOTAL_RETURN, STOOQ_UNKNOWN
from atlas.global_market.providers.stooq_bulk import (
    ADJUSTMENT_UNKNOWN,
    ArchiveMember,
    StooqBulkProvider,
)
from atlas.global_market.providers.symbology import stooq_symbol

SOURCE = "stooq_csv"
LABELLED = STOOQ_TOTAL_RETURN  # minted only behind the BASIS gate — see measured_total_return
UNLABELLED = STOOQ_UNKNOWN  # the honest label when nothing has measured these bars
PROTECTED_SOURCE = "alpaca"
REASON_NO_IDENTITY = "no identity row (instrument_master.symbol or symbol_alias source='stooq')"
CHUNK_BYTES = 20_000_000  # uncompressed text per provider call ≈ 400k bars; one transaction each
REPORT_COLUMNS = ("stooq_ticker", "symbol", "kind", "exchange", "status", "rows", "detail")

# Bar validity (a DATA-QUALITY rule, not methodology): each predicate names the rows it refuses.
_REFUSALS: tuple[tuple[str, Callable[[pd.DataFrame], pd.Series]], ...] = (
    (
        "a price <= 0",
        lambda f: (f["open"] <= 0) | (f["high"] <= 0) | (f["low"] <= 0) | (f["close"] <= 0),
    ),
    ("high < low", lambda f: f["high"] < f["low"]),
    (
        "open/close outside [low, high]",
        lambda f: (
            (f["open"] < f["low"])
            | (f["open"] > f["high"])
            | (f["close"] < f["low"])
            | (f["close"] > f["high"])
        ),
    ),
)

UPSERT_SQL = f"""
insert into {_gdb.M}.ohlcv_daily
    (instrument_id, date, open, high, low, close, volume,
     close_adj, close_tr, trade_count, vwap, source, adjustment_source)
values %s
on conflict (instrument_id, date) do update set
    open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
    volume = excluded.volume, close_adj = excluded.close_adj, close_tr = excluded.close_tr,
    trade_count = excluded.trade_count, vwap = excluded.vwap, source = excluded.source,
    adjustment_source = excluded.adjustment_source, ingested_at = now()
where ohlcv_daily.source <> '{PROTECTED_SOURCE}'
returning instrument_id
"""
STATE_SQL = f"""
insert into {_gdb.M}.ingest_state (source, key, value, updated_at) values %s
on conflict (source, key) do update set value = excluded.value, updated_at = excluded.updated_at
"""


# ── identity bridge (pure) ──


@dataclass(frozen=True, slots=True)
class Mapped:
    member: ArchiveMember
    instrument_id: str
    asset_class: str
    via: str  # alias | symbol
    note: str = ""  # e.g. the archive folder and instrument_master disagree on the kind


@dataclass(frozen=True, slots=True)
class Unmapped:
    member: ArchiveMember
    reason: str


Identity = Mapping[str, tuple[str, str]]  # key → (instrument_id, asset_class)


def map_members(
    members: Sequence[ArchiveMember], by_alias: Identity, by_symbol: Identity
) -> tuple[list[Mapped], list[Unmapped]]:
    """Alias (Stooq's own spelling) wins over the normalised symbol; neither → unmapped."""
    mapped: list[Mapped] = []
    unmapped: list[Unmapped] = []
    for m in members:
        via = "alias"
        hit = by_alias.get(m.stooq_ticker)
        if hit is None:
            via = "symbol"
            hit = by_symbol.get(m.symbol)
        if hit is None:
            unmapped.append(Unmapped(m, REASON_NO_IDENTITY))
            continue
        instrument_id, asset_class = hit
        note = (
            ""
            if asset_class == m.kind
            else f"archive folder says {m.kind}, instrument_master says {asset_class}"
        )
        mapped.append(Mapped(m, instrument_id, asset_class, via, note))
    return mapped, unmapped


def load_identity() -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    # Active rows only: a symbol is unique among ACTIVE instruments (a recycled ticker's
    # delisted holder keeps its row and history), and a ticker-keyed archive can only mean
    # the listing that carries the ticker today.
    master = _gdb.read_df(
        f"select instrument_id::text as instrument_id, symbol, asset_class "
        f"from {_gdb.M}.instrument_master where is_active"
    )
    alias = _gdb.read_df(
        f"select a.source_symbol, a.instrument_id::text as instrument_id, m.asset_class "
        f"from {_gdb.M}.symbol_alias a "
        f"join {_gdb.M}.instrument_master m using (instrument_id) "
        f"where a.source = 'stooq' and a.valid_to is null"
    )
    by_symbol = {
        str(s): (str(i), str(c))
        for s, i, c in zip(
            master["symbol"], master["instrument_id"], master["asset_class"], strict=True
        )
    }
    by_alias = {
        str(s).upper(): (str(i), str(c))
        for s, i, c in zip(
            alias["source_symbol"], alias["instrument_id"], alias["asset_class"], strict=True
        )
    }
    return by_alias, by_symbol


# ── resume state (pure) ──


def state_value(
    member: ArchiveMember,
    *,
    since: date | None,
    rows_sent: int,
    rows_written: int,
    first_date: date | None,
    last_date: date | None,
) -> dict[str, Any]:
    return {
        "zip_member": member.name,
        "crc": member.crc,
        "size": member.size,
        "since": since.isoformat() if since else None,
        "rows_sent": rows_sent,
        "rows_written": rows_written,
        "first_date": first_date.isoformat() if first_date else None,
        "last_date": last_date.isoformat() if last_date else None,
        "imported_at": datetime.now(UTC).isoformat(),
    }


def should_skip(member: ArchiveMember, state: Mapping[str, Any] | None, since: date | None) -> bool:
    """Same file (CRC + size) and a stored window that covers the requested one."""
    if not state or state.get("crc") != member.crc or state.get("size") != member.size:
        return False
    stored = state.get("since")
    if stored is None:
        return True  # a full import covers any --since
    return since is not None and date.fromisoformat(str(stored)) <= since


def load_state() -> dict[str, dict[str, Any]]:
    df = _gdb.read_df(
        f"select key, value from {_gdb.M}.ingest_state where source = :s", {"s": SOURCE}
    )
    return {str(k): dict(v) for k, v in zip(df["key"], df["value"], strict=True)}


# ── bars → rows ──


def split_valid_bars(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, date, str]]]:
    """Keep the valid bars; list ``(symbol, date, reason)`` for every refused row."""
    if frame.empty:
        return frame, []
    refused: list[tuple[str, date, str]] = []
    bad = pd.Series(False, index=frame.index)
    for reason, predicate in _REFUSALS:
        hit = predicate(frame).astype(bool) & ~bad
        symbols = frame.loc[hit, "symbol"].tolist()
        dates = frame.loc[hit, "date"].tolist()
        refused.extend((s, d, reason) for s, d in zip(symbols, dates, strict=True))
        bad |= hit
    return frame.loc[~bad], refused


def measured_total_return() -> bool:
    """Ask the BASIS gate what the bars already in ohlcv_daily actually carry.

    ``validate_global.py --check BASIS`` is the ONE place the basis is measured, and it
    passes only when the evidence says total return. Anything that stops it — no bars yet on
    a first import, FRED unreachable, a split-only or indeterminate verdict — returns False,
    and the caller labels ``stooq:unknown`` rather than guess. The gate prints its reasoning.
    """
    from validate_global import Gate, check_BASIS

    gate = Gate()
    try:
        check_BASIS(gate)
    except Exception as error:  # an unreachable FRED is "not measured", never "total return"
        print(f"  BASIS gate could not run: {error!r}")
        return False
    return gate.fails == 0


def bar_rows(
    frame: pd.DataFrame, instrument_id: str, *, total_return: bool
) -> list[tuple[object, ...]]:
    """Column order is UPSERT_SQL's.

    ``total_return`` is the BASIS gate's verdict, not an assumption: when it holds the file's
    close IS the total-return close and lands in ``close_tr`` under ``stooq:total_return``.
    When it does not, the bar is still stored — the prices are real — but ``close_tr`` stays
    NULL under ``stooq:unknown``, so nothing scores it. ``close_adj`` is NULL either way.
    """
    label = LABELLED if total_return else UNLABELLED
    return [
        (
            instrument_id,
            d,
            o,
            h,
            lo,
            c,
            v,
            None,
            c if total_return else None,
            None,
            None,
            SOURCE,
            label,
        )
        for d, o, h, lo, c, v in zip(
            frame["date"].tolist(),
            frame["open"].tolist(),
            frame["high"].tolist(),
            frame["low"].tolist(),
            frame["close"].tolist(),
            frame["volume"].tolist(),
            strict=True,
        )
    ]


def chunks_by_size[T](
    items: Sequence[T], size: Callable[[T], int], limit: int
) -> Iterator[list[T]]:
    """Consecutive slices whose ``size`` sums stay under ``limit`` (one item at least)."""
    batch: list[T] = []
    total = 0
    for it in items:
        if batch and total + size(it) > limit:
            yield batch
            batch, total = [], 0
        batch.append(it)
        total += size(it)
    if batch:
        yield batch


# ── report ──


def note(report: Report, m: ArchiveMember, status: str, rows: int = 0, detail: str = "") -> None:
    """One member outcome in the shared report (``REPORT_COLUMNS`` order)."""
    report.add(m.stooq_ticker, m.symbol, m.kind, m.exchange, status, rows, detail)


def note_refused(
    report: Report, by_symbol: Mapping[str, ArchiveMember], rows: list[tuple[str, date, str]]
) -> None:
    for s, d, reason in rows:
        note(report, by_symbol[s], "refused_bar", 1, f"{d}: {reason}")


# ── the two modes ──


def select_members(provider: StooqBulkProvider, symbols: str | None) -> list[ArchiveMember]:
    """All members, or the ``--symbols`` subset (instrument spelling or Stooq spelling)."""
    members = provider.members()
    if not symbols:
        return members
    index = {m.symbol: m for m in members}
    picked: list[ArchiveMember] = []
    for raw in symbols.split(","):
        key = raw.strip().upper()
        if not key:
            continue
        m = index.get(key)
        if m is None:
            try:
                m = index.get(stooq_symbol(key))
            except ValueError:
                m = None
        if m is None:
            print(f"  --symbols {key}: not in the archive")
            continue
        picked.append(m)
    return picked


def bridge(members: list[ArchiveMember], report: Report) -> tuple[list[Mapped], list[Unmapped]]:
    """The identity bridge against the live table (read-only); every unmapped member is
    written to the report with its reason before anything else happens."""
    by_alias, by_symbol = load_identity()
    mapped, unmapped = map_members(members, by_alias, by_symbol)
    for u in unmapped:
        note(report, u.member, "unmapped", 0, u.reason)
    return mapped, unmapped


def dry_run_identity(members: list[ArchiveMember], report: Report) -> None:
    """How many members map, and through what. Skipped — and said so — when no database
    is configured; a configured but unreachable one raises."""
    try:
        _gdb.db_url()
    except RuntimeError as e:
        print(f"  identity bridge skipped: {e}")
        return
    mapped, unmapped = bridge(members, report)
    via = Counter(x.via for x in mapped)
    kind_notes = sum(1 for x in mapped if x.note)
    print(
        f"  identity: {len(mapped):,d} of {len(members):,d} members map to instrument_master "
        f"({len(mapped) / max(len(members), 1):.1%}) — via alias {via['alias']:,d}, "
        f"via symbol {via['symbol']:,d}; {len(unmapped):,d} unmapped; "
        f"{kind_notes:,d} archive-folder/asset_class disagreements (noted, not resolved)"
    )
    if unmapped:
        sample = ", ".join(u.member.stooq_ticker for u in unmapped[:10])
        print(f"  unmapped {report.where()}: {sample}{', …' if len(unmapped) > 10 else ''}")


def dry_run(
    provider: StooqBulkProvider, members: list[ArchiveMember], since: date | None, report: Report
) -> None:
    t0 = time.monotonic()
    start = since or date.min
    end = _gdb.eod_cutoff()
    mb = provider.path.stat().st_size / 1e6
    print(f"== Stooq archive {provider.path.name} ({mb:,.0f} MB), dry run — no writes ==")
    by_bucket = Counter((m.kind, m.exchange) for m in members)
    for (kind, exchange), n in sorted(by_bucket.items()):
        print(f"  {kind:5s} {exchange:8s} {n:6,d} members")
    empty = sum(1 for m in members if m.size == 0)
    print(f"  total {len(members):,d} members ({empty} empty files); window {start} → {end}")
    dry_run_identity(members, report)

    per_symbol: dict[str, tuple[int, date, date]] = {}
    refused_rows = 0
    for chunk in chunks_by_size(members, lambda m: m.size, CHUNK_BYTES):
        frame = provider.bars([m.symbol for m in chunk], start, end, ADJUSTMENT_UNKNOWN)
        good, refused = split_valid_bars(frame)
        refused_rows += len(refused)
        note_refused(report, {m.symbol: m for m in chunk}, refused)
        if not good.empty:
            agg = good.groupby("symbol")["date"].agg(["size", "min", "max"])
            for s, n, lo, hi in zip(agg.index, agg["size"], agg["min"], agg["max"], strict=True):
                per_symbol[str(s)] = (int(n), lo, hi)
        for m in chunk:
            n = per_symbol.get(m.symbol, (0, date.min, date.min))[0]
            note(report, m, "parsed" if n else "empty", n)

    if not per_symbol:
        print("\n  no bars in the window")
        return
    rows = sum(n for n, _, _ in per_symbol.values())
    lo = min(lo for _, lo, _ in per_symbol.values())
    hi = max(hi for _, _, hi in per_symbol.values())
    frac = provider.fractional_volume_rows
    print(f"\n  symbols with bars: {len(per_symbol):,d} of {len(members):,d}")
    print(f"  rows parsed: {rows:,d}   min date {lo}   max date {hi}")
    print(
        f"  fractional volumes (Stooq split adjustment; stored rounded to whole shares): "
        f"{frac:,d} ({frac / max(rows + refused_rows, 1):.1%})"
    )
    print(f"  refused bars (not a valid bar): {refused_rows:,d} {report.where()}")
    print("\n  10 largest members:")
    for m in sorted(members, key=lambda m: m.size, reverse=True)[:10]:
        n, lo, hi = per_symbol.get(m.symbol, (0, date.min, date.min))
        print(
            f"  {m.size:>10,d} B  {m.symbol:8s} {m.kind:5s} {m.exchange:8s} "
            f"{n:7,d} rows  {lo} → {hi}  {m.name}"
        )
    print(f"\n  parsed in {time.monotonic() - t0:,.0f}s")


def run_import(
    provider: StooqBulkProvider, members: list[ArchiveMember], since: date | None, report: Report
) -> int:
    t0 = time.monotonic()
    mapped, unmapped = bridge(members, report)
    print(
        f"== identity: {len(mapped):,d} of {len(members):,d} members map to instrument_master "
        f"({len(unmapped):,d} unmapped → {report.path}) =="
    )
    if not mapped:
        print("  nothing maps — run build_identity.py first (the importer never mints instruments)")
        return 2
    state = load_state()
    todo = [x for x in mapped if not should_skip(x.member, state.get(x.member.symbol), since)]
    todo_symbols = {x.member.symbol for x in todo}
    for x in mapped:
        if x.member.symbol not in todo_symbols:
            note(report, x.member, "skipped_resumed", 0, "same CRC/size already imported")
    print(f"  resume: {len(mapped) - len(todo):,d} already imported, {len(todo):,d} to do")

    # ONE measurement for the run: the archive is one download, so its basis is one answer.
    # On a COLD database this necessarily fails — the gate measures rows that are not in the
    # table yet, SPY's own included — so the rows land unlabelled and the second pass below
    # picks them up once they exist. Cold start therefore stays ONE command, and the label is
    # still measured from stored bars rather than assumed.
    total_return = measured_total_return()
    print(
        f"  basis: rows will be labelled {LABELLED} with close_tr set"
        if total_return
        else f"  basis: not measurable yet (a cold database has no bars to measure) — "
        f"rows land as {UNLABELLED}; the basis is re-measured after the import"
    )

    start = since or date.min
    end = _gdb.eod_cutoff()
    sent = written = refused_rows = done = 0
    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        for chunk in chunks_by_size(todo, lambda x: x.member.size, CHUNK_BYTES):
            frame = provider.bars([x.member.symbol for x in chunk], start, end, ADJUSTMENT_UNKNOWN)
            good, refused = split_valid_bars(frame)
            refused_rows += len(refused)
            note_refused(report, {x.member.symbol: x.member for x in chunk}, refused)
            rows: list[tuple[object, ...]] = []
            spans: dict[str, tuple[int, date | None, date | None]] = {}
            for x in chunk:
                g = good.loc[good["symbol"] == x.member.symbol]
                rows.extend(bar_rows(g, x.instrument_id, total_return=total_return))
                dates = g["date"].tolist()
                spans[x.member.symbol] = (
                    len(dates),
                    dates[0] if dates else None,
                    dates[-1] if dates else None,
                )
            with conn, conn.cursor() as cur:  # one transaction: bars + state, or neither
                returned = (
                    execute_values(cur, UPSERT_SQL, rows, page_size=1000, fetch=True)
                    if rows
                    else []
                )
                per_instrument = Counter(str(r[0]) for r in returned)
                state_rows: list[tuple[object, ...]] = []
                for x in chunk:
                    n, lo, hi = spans[x.member.symbol]
                    w = per_instrument.get(x.instrument_id, 0)
                    value = state_value(
                        x.member,
                        since=since,
                        rows_sent=n,
                        rows_written=w,
                        first_date=lo,
                        last_date=hi,
                    )
                    state_rows.append((SOURCE, x.member.symbol, Json(value), datetime.now(UTC)))
                    protected = (
                        f"{n - w} rows protected (source='{PROTECTED_SOURCE}')" if n != w else ""
                    )
                    note(report, x.member, "imported" if n else "empty", n, x.note or protected)
                execute_values(cur, STATE_SQL, state_rows, page_size=1000)
            sent += len(rows)
            written += len(returned)
            done += len(chunk)
            print(
                f"  [{done:,d}/{len(todo):,d}] {chunk[0].member.symbol}…{chunk[-1].member.symbol}: "
                f"{len(rows):,d} rows sent, {len(returned):,d} written; {time.monotonic() - t0:,.0f}s"
            )
    finally:
        conn.close()
    print(
        f"\n== done: {sent:,d} rows sent, {written:,d} written, {sent - written:,d} protected "
        f"({PROTECTED_SOURCE}), {refused_rows:,d} refused bars; {len(unmapped):,d} unmapped; "
        f"report {report.path} =="
    )
    if not total_return and written:
        # The bars the gate needed now EXIST. Re-measure and label them, so a first import
        # into an empty database is one command and not a footgun. Advisory: the import
        # itself succeeded either way, and rows that still cannot be measured keep
        # `stooq:unknown` — which compute_technicals skips and lists, never scores.
        print("\n== the bars are in; re-measuring the basis to label them ==")
        relabel()
    return 0


RELABEL_SQL = f"""
update {_gdb.M}.ohlcv_daily
   set close_tr = close, adjustment_source = %s, ingested_at = now()
 where source = %s and adjustment_source = %s and close is not null
"""


def relabel() -> int:
    """Label rows imported before the basis was measured — if, and only if, it measures now.

    Runs the BASIS gate against the rows themselves, then touches only rows this importer
    wrote (``source='stooq_csv'``) still carrying ``stooq:unknown``, and only their label and
    ``close_tr``. No price changes: the close was always the total-return close, the database
    just had no evidence for saying so. Idempotent, and safe beside Alpaca rows (other
    source). A gate that does not pass exits 2 with nothing written — relabelling anyway is
    exactly the stale label this design prevents.
    """
    print("== measuring the basis before labelling anything ==")
    if not measured_total_return():
        print(
            f"\n== REFUSED: the BASIS gate did not pass, so no row is labelled {LABELLED}. "
            f"Rows keep {UNLABELLED} and compute_technicals will skip them. =="
        )
        return 2
    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            cur.execute(RELABEL_SQL, (LABELLED, SOURCE, UNLABELLED))
            rows = cur.rowcount
    finally:
        conn.close()
    print(
        f"\n== relabelled {rows:,d} rows {UNLABELLED} -> {LABELLED} "
        f"(close_tr = close); re-run compute_technicals.py to score them =="
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Import a Stooq d_us_txt.zip into atlas_global.ohlcv_daily"
    )
    ap.add_argument("--zip", help="path to Stooq's d_us_txt.zip (not needed with --relabel)")
    ap.add_argument(
        "--relabel",
        action="store_true",
        help=f"measure the basis, then set close_tr and adjustment_source={LABELLED} on "
        f"already-imported {UNLABELLED} rows; reads no archive",
    )
    ap.add_argument("--symbols", default=None, help="comma-separated subset, e.g. SPY,AAPL,BRK.B")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="parse the archive and report; reads identity from the DB when configured, writes nothing",
    )
    ap.add_argument(
        "--since", type=date.fromisoformat, default=None, help="only bars on/after YYYY-MM-DD"
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=None,
        help="CSV of per-member outcomes (default: import_stooq_<utc>.csv next to the zip; "
        "--dry-run writes one only when asked)",
    )
    args = ap.parse_args()

    if args.relabel:
        return relabel()
    if not args.zip:
        ap.error("--zip is required (or pass --relabel to label already-imported rows)")

    provider = StooqBulkProvider(args.zip)
    members = select_members(provider, args.symbols)
    if not members:
        print("no archive members selected")
        return 2
    path = args.report
    if path is None and not args.dry_run:
        stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        path = provider.path.with_name(f"import_stooq_{stamp}.csv")
    report = Report(path, REPORT_COLUMNS)
    try:
        if args.dry_run:
            dry_run(provider, members, args.since, report)
            return 0
        return run_import(provider, members, args.since, report)
    finally:
        report.close()


if __name__ == "__main__":
    sys.exit(main())
