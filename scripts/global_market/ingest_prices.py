#!/usr/bin/env python3
"""Daily bars and corporate actions from the price spine → ``atlas_global.ohlcv_daily`` /
``corporate_actions``.

    python scripts/global_market/ingest_prices.py --backfill            # 2016-01-04 → EOD
    python scripts/global_market/ingest_prices.py                       # nightly increment
    python scripts/global_market/ingest_prices.py --symbols SPY,AAPL --dry-run

WHY THREE PULLS PER WINDOW. The vendor serves the same bars on three adjustment bases, and
each answers a different question, so we take all three rather than deriving two from one:

* ``raw``   → ``open/high/low/close/volume`` — what actually traded. The only basis whose
  volume is comparable with any other source, so it is what the liquidity floor and the
  cross-source checks read.
* ``split`` → ``open_adj/high_adj/low_adj/close_adj`` — split-only, the CHART and technicals
  basis (an EMA over a series with dividend steps in it is not an EMA of anything).
* ``all``   → ``close_tr`` — splits AND dividends, the basis every return, relative-strength
  and risk metric is computed on.

The 2026-09-04 plan had us compute the adjusted bases ourselves from raw bars plus events —
"the ONE bespoke formula of the platform", a CRSP-style back-adjustment with a parity test
against the vendor's own adjusted close. The SIP gate (2026-09-07) measured that the vendor
already serves both, so that formula is not written: three pulls delete it, its parity test,
and its whole class of bug. These are the vendor's prints, not our arithmetic — rule #0 is
satisfied more cleanly, not less.

THE RE-BASING RULE, which is the one thing here that can be silently wrong. A back-adjusted
series is anchored to the present: ``close_tr[d]`` is the raw close times every adjustment
factor between ``d`` and today. So the day a dividend goes ex, EVERY historical value moves.
Measured on this vendor, the anchor is the present and NOT the request window — SPY's
2016-01-04 ``all`` close is 171.10 whether ``end`` is 2016-01-07 or 2026-09-05 — which is
better than the Stooq archive, whose base walks with its download date. It does not make the
problem go away. A history written half on an old base and half on a new one yields a WRONG
return across the seam, and nothing about the row says so.

So: an instrument with a corporate action newer than the last date already stored FOR IT
has its adjusted columns rewritten over the full history, never appended
(:func:`rebasing_targets`). Actions are fetched first, precisely so this is known before
any bar is written. Returns are invariant to the base; absolute levels are not, and a
return that spans the seam is not.

Note the per-instrument comparison. Testing every action against the HISTORY FLOOR instead
is the same rule read one word too broadly, and it costs a factor of three hundred: every
dividend payer re-bases on every run, so each nightly quietly becomes a full ten-year
backfill of the universe. Measured on three real instruments, that is 8,052 bars a night
against the 27 actually missing.

Sources and provenance: every row carries ``source='alpaca'`` and
``adjustment_source='alpaca:split+all'`` — the label says which pulls produced the adjusted
columns, so a later reader never has to guess (the Stooq archive's rows say
``stooq:unknown`` until ``label_stooq`` measures them, and are never overwritten by a
vendor row for an instrument-day the vendor also has).

Writes nothing without a SPY bar at the EOD: no anchor session means no calendar, and every
downstream gate counts its lag in SPY sessions.
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import _gdb
import pandas as pd
import psycopg2
from _report import Report
from psycopg2.extras import execute_values

from atlas.global_market.providers.alpaca import AlpacaProvider
from atlas.global_market.providers.base import ACTION_COLUMNS

M = _gdb.M
SOURCE = "alpaca"
ADJUSTMENT_SOURCE = "alpaca:split+all"

# The vendor's history floor, measured 2026-09-07: a request from 1990 returns bars starting
# here for SPY and, with the identical count, for AAPL — which listed in 1980. So this is a
# floor on the PLAN, not a listing date, and anything older comes from the Stooq archive.
HISTORY_START = dt.date(2016, 1, 4)

# Re-pull this many sessions behind each instrument's watermark on an incremental run. The
# vendor revises late prints; India's ingesters use the same buffer for the same reason.
REPULL_SESSIONS = 5

BASES = ("raw", "split", "all")

# Columns written per instrument-day, in the order the upsert takes them.
COLUMNS = (
    "instrument_id",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_adj",
    "high_adj",
    "low_adj",
    "close_adj",
    "close_tr",
    "trade_count",
    "vwap",
)

UPSERT_SQL = f"""
insert into {M}.ohlcv_daily (
    {", ".join(COLUMNS)}, source, adjustment_source, ingested_at
) values %s
on conflict (instrument_id, date) do update set
    open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
    volume = excluded.volume, open_adj = excluded.open_adj, high_adj = excluded.high_adj,
    low_adj = excluded.low_adj, close_adj = excluded.close_adj, close_tr = excluded.close_tr,
    trade_count = excluded.trade_count, vwap = excluded.vwap,
    source = excluded.source, adjustment_source = excluded.adjustment_source,
    ingested_at = now()
"""

# The DB columns, which differ from the provider frame's ACTION_COLUMNS by their first
# entry: the adapter speaks symbols, the table speaks instrument ids.
ACTION_DB_COLUMNS = ("instrument_id", "ex_date", "action_type", "ratio", "cash_amount")

ACTIONS_UPSERT_SQL = f"""
insert into {M}.corporate_actions (
    {", ".join(ACTION_DB_COLUMNS)}, source, ingested_at
) values %s
on conflict (instrument_id, ex_date, action_type) do update set
    ratio = excluded.ratio, cash_amount = excluded.cash_amount,
    source = excluded.source, ingested_at = now()
"""

# The price scope deliberately does NOT read universe_snapshot, which compute_technicals uses:
# that table is built from ADV$, which is built from these bars, so reading it here would make
# a cold start circular. The non-circular definition is the plan's own universe — every listed
# ETF (all of them are classified, and the liquidity floor can only be set once their ADV$
# exists), every S&P 500 member current or trailing, and the benchmarks.
TARGETS_SQL = f"""
WITH picked AS (
    SELECT instrument_id FROM {M}.instrument_master
    WHERE is_active AND asset_class = 'etf'
    UNION SELECT instrument_id FROM {M}.index_membership
    UNION SELECT instrument_id FROM {M}.benchmark_master WHERE is_active
)
SELECT im.instrument_id::text AS instrument_id, im.symbol, im.asset_class
FROM {M}.instrument_master im
WHERE im.is_active AND im.asset_class IN ('stock', 'etf')
  AND (:everything OR im.instrument_id IN (SELECT instrument_id FROM picked))
ORDER BY im.asset_class, im.symbol
"""

# Each instrument's own watermark, so an incremental run pulls only what it lacks. Vendor rows
# only: a Stooq row is not evidence that the vendor's bar for that day was ever fetched.
WATERMARK_SQL = f"""
SELECT instrument_id::text AS instrument_id, max(date) AS last_date
FROM {M}.ohlcv_daily WHERE source = '{SOURCE}' GROUP BY 1
"""

SPY_BAR_SQL = f"""
SELECT max(o.date) FROM {M}.ohlcv_daily o
JOIN {M}.instrument_master im USING (instrument_id)
WHERE im.symbol = 'SPY' AND o.date <= %(eod)s
"""


def scalar_or_none(cur: Any) -> Any:
    """The first column of ``cur``'s next row, or ``None`` when there is no row.

    ``fetchone()`` returns ``None`` for an empty result, so subscripting it directly
    turns "the aggregate found nothing" into a TypeError several lines from the cause.
    Every query this is used on is a ``max()``, which returns one row holding NULL, so
    the None branch means the query itself changed — worth an honest failure either way.
    """
    row = cur.fetchone()
    return None if row is None else row[0]


def merge_bases(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The three per-basis frames → one row per (symbol, date) with all three bases on it.

    RAW is the spine: a date the vendor prints raw but not adjusted (or the reverse) is a
    vendor inconsistency, not something to paper over, so the adjusted columns come from a
    LEFT join and stay NULL rather than being back-filled from a neighbouring basis. The
    caller reports the count; nothing invents a price.
    """
    raw: pd.DataFrame = frames["raw"]
    out = raw[
        ["symbol", "date", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
    ].copy()

    split = pd.DataFrame(
        frames["split"], columns=pd.Index(["symbol", "date", "open", "high", "low", "close"])
    )
    split = split.rename(
        columns={"open": "open_adj", "high": "high_adj", "low": "low_adj", "close": "close_adj"}
    )
    total = pd.DataFrame(frames["all"], columns=pd.Index(["symbol", "date", "close"]))
    total = total.rename(columns={"close": "close_tr"})

    out = out.merge(split, on=["symbol", "date"], how="left")
    return out.merge(total, on=["symbol", "date"], how="left")


def rebasing_targets(
    actions: pd.DataFrame, watermarks: dict[str, dt.date], floor: dt.date
) -> set[str]:
    """Symbols whose adjusted history must be rewritten in full, not appended.

    The question is per instrument and it is NOT "did anything happen since 2016". It is:
    **has an action gone ex since the last date we already wrote for THIS instrument?** If
    so, every row we hold for it sits on a base the vendor has since moved, and appending
    today's bar would put a seam in the middle of the series. If not, the rows we hold are
    still on the current base and the incremental window is safe.

    Getting this wrong is expensive rather than incorrect, which is why it is easy to miss:
    comparing every action against the history floor marks EVERY dividend payer as re-basing
    on EVERY run, so each nightly silently becomes a full ten-year backfill of the whole
    universe — measured at three requests per 200 symbols per basis, roughly 5,300 rather
    than 100. It was found by running the incremental path against real rows and noticing it
    re-pulled 8,052 bars it already had.

    An instrument with no watermark has nothing to invalidate: it is pulled from the floor
    anyway, by :func:`window_for`.
    """
    if actions.empty:
        return set()
    out: set[str] = set()
    for r in actions.to_dict("records"):
        symbol = str(r["symbol"])
        mark = watermarks.get(symbol)
        if mark is not None and r["ex_date"] > mark - dt.timedelta(days=REPULL_SESSIONS * 2):
            out.add(symbol)
        elif mark is None and r["ex_date"] >= floor:
            out.add(symbol)
    return out


def action_rows(
    actions: pd.DataFrame, ids: dict[str, str]
) -> tuple[list[tuple[Any, ...]], list[tuple[tuple[str, Any, str], list[Any]]]]:
    """Vendor action records → ``(rows_to_write, conflicts)``, dropping symbols we do not hold.

    ``ratio`` is new-shares-per-old (a 4:1 forward split is 4.0, a 1-for-8 reverse is 0.125)
    so one column reads the same way in both directions; ``cash_amount`` is USD per share and
    is NULL for anything that is not cash. Each conflict is returned as its key plus EVERY
    competing value, because a report naming one of two numbers cannot be acted on.

    TWO RECORDS, ONE KEY. ``corporate_actions`` is keyed ``(instrument_id, ex_date,
    action_type)`` and the feed does not respect that. Postgres refuses two such rows inside
    one statement ("ON CONFLICT DO UPDATE command cannot affect row a second time"), which is
    the right failure and an unusable one — the whole run dies. Two distinct things turned up
    on real data, and they are handled differently:

    * **The same record twice** (GE's 2021-06-25 $0.01 dividend, identical in every stored
      column, differing only in the vendor's record id). Collapsed to ONE. Provably lossless:
      there is no number to choose between.
    * **Two records that DISAGREE on the amount.** Written NOWHERE, and reported. Measured on
      a 200-ETF backfill: 11 of 973 events, ~1.1 %, and EVERY ONE of them in December —
      the month ETFs pay a year-end capital-gains distribution alongside the regular income
      one. AAA on 2021-12-29 is the shape of all of them: 0.0161075 and 0.00161, identical
      CUSIP, identical ex/record/payable/process dates, both ``special=False``, both
      ``foreign=False``. Nothing the feed publishes says which is right, or whether they are
      two components that ought to be added.

    So neither is written. Adding them up would be arithmetic the feed never stated; keeping
    the larger, or the last one seen, would be arbitrary — and this is a dividend, so a wrong
    choice is a wrong yield and a wrong distribution history. Note that no PRICE depends on
    this: ``close_tr`` is the vendor's own total-return series, not something reconstructed
    from these rows, so a withheld action costs the events table a row and costs the board
    nothing. That is what makes withholding affordable rather than merely principled.

    OPEN, for the FM: ask the vendor whether a same-key pair is two components of one
    distribution (in which case they sum) or a data error. Until then the report is the record.
    """
    keep: dict[tuple[str, Any, str], tuple[Any, ...]] = {}
    seen: dict[tuple[str, Any, str], list[Any]] = {}
    disagreed: set[tuple[str, Any, str]] = set()
    for r in actions.to_dict("records"):
        iid = ids.get(str(r["symbol"]))
        if iid is None:
            continue
        key = (iid, r["ex_date"], str(r["action_type"]))
        row = (iid, r["ex_date"], r["action_type"], r["ratio"], r["cash_amount"])
        value = r["cash_amount"] if r["ratio"] is None else r["ratio"]
        prior = keep.get(key)
        if prior is not None and prior != row:
            disagreed.add(key)
        seen.setdefault(key, []).append(value)
        keep[key] = row
    conflicts = [(k, seen[k]) for k in sorted(disagreed, key=lambda k: (k[1], k[0]))]
    return [row for k, row in keep.items() if k not in disagreed], conflicts


def price_rows(frame: pd.DataFrame, ids: dict[str, str]) -> list[tuple[Any, ...]]:
    """Merged bars → upsert tuples. A bar for a symbol we do not hold is skipped by the
    caller's report, never minted into ``instrument_master`` (``build_identity.py`` is that
    table's only writer)."""
    rows: list[tuple[Any, ...]] = []
    for r in frame.to_dict("records"):
        iid = ids.get(str(r["symbol"]))
        if iid is None:
            continue
        rows.append(
            (
                iid,
                r["date"],
                r["open"],
                r["high"],
                r["low"],
                r["close"],
                None if pd.isna(r["volume"]) else int(r["volume"]),
                r["open_adj"],
                r["high_adj"],
                r["low_adj"],
                r["close_adj"],
                r["close_tr"],
                None if pd.isna(r["trade_count"]) else int(r["trade_count"]),
                r["vwap"],
            )
        )
    return rows


def invalid_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Bars that cannot be true, whatever the vendor says: a non-positive price, a high below
    a low, or an open/close outside [low, high]. Refused into the report by symbol and date —
    the same rule ``import_stooq`` applies to the archive, applied to the spine too."""
    px = ["open", "high", "low", "close"]
    bad = (frame[px] <= 0).any(axis=1)
    bad |= frame["high"] < frame["low"]
    bad |= (frame["open"] > frame["high"]) | (frame["open"] < frame["low"])
    bad |= (frame["close"] > frame["high"]) | (frame["close"] < frame["low"])
    return frame.loc[bad]


def by_start(
    symbols: Sequence[str], watermarks: dict[str, dt.date], since: dt.date, rebase: set[str]
) -> dict[dt.date, list[str]]:
    """Symbols grouped by the date their pull starts.

    The adapter already chunks at its own 200-symbol request limit, so grouping here is about
    the WINDOW, not the request size: everything sharing a start date goes in one call, and
    nothing is pulled over a longer window than it needs. On a backfill that is one group; on
    a nightly it is usually two (the instruments with a fresh watermark, and whatever is new
    or re-basing).
    """
    groups: dict[dt.date, list[str]] = {}
    for s in symbols:
        groups.setdefault(window_for(s, watermarks, since, rebase), []).append(s)
    return dict(sorted(groups.items()))


def targets(scope: str, symbols: str | None) -> pd.DataFrame:
    frame = _gdb.read_df(TARGETS_SQL, {"everything": scope == "all"})
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        frame = pd.DataFrame(frame[frame["symbol"].isin(sorted(wanted))])
        missing = wanted - set(frame["symbol"])
        if missing:
            raise SystemExit(
                f"REFUSED: not in instrument_master (or inactive): {', '.join(sorted(missing))}"
            )
    return frame


def window_for(
    symbol: str, watermarks: dict[str, dt.date], since: dt.date, rebase: set[str]
) -> dt.date:
    """Where this instrument's pull starts: the history floor when backfilling or re-basing,
    else its own watermark minus the re-pull buffer."""
    if symbol in rebase:
        return since
    last = watermarks.get(symbol)
    if last is None:
        return since
    return max(since, last - dt.timedelta(days=REPULL_SESSIONS * 2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None, help="default: eod_cutoff()")
    ap.add_argument(
        "--backfill", action="store_true", help=f"pull from {HISTORY_START}, ignoring watermarks"
    )
    ap.add_argument("--since", type=dt.date.fromisoformat, default=None, help="override the floor")
    ap.add_argument("--scope", choices=["universe", "all"], default="universe")
    ap.add_argument("--symbols", default=None, help="comma-separated subset, e.g. SPY,AAPL")
    ap.add_argument("--limit", type=int, default=None, help="first N targets (smoke test)")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    ap.add_argument("--report", default=None, help="CSV of per-instrument outcomes")
    args = ap.parse_args(argv)

    eod = args.eod or _gdb.eod_cutoff()
    since = args.since or HISTORY_START
    picked = targets(args.scope, args.symbols)
    if args.limit:
        picked = picked.head(args.limit)
    if picked.empty:
        print("REFUSED: no targets — build_identity.py must land its rows first")
        return 2

    ids = dict(zip(picked["symbol"], picked["instrument_id"], strict=True))
    symbols = sorted(ids)
    watermarks: dict[str, dt.date] = {}
    if not args.backfill:
        wm = _gdb.read_df(WATERMARK_SQL)
        by_id = dict(zip(wm["instrument_id"], wm["last_date"], strict=True))
        watermarks = {s: by_id[i] for s, i in ids.items() if i in by_id}

    print(f"[prices] targets={len(symbols):,d} scope={args.scope} eod={eod} since={since}")
    print(f"  watermarks: {len(watermarks):,d} instrument(s) already have vendor bars")

    provider = AlpacaProvider()
    report = Report(
        Path(args.report) if args.report else None,
        ("symbol", "status", "bars", "first_date", "last_date", "detail"),
    )

    # Actions FIRST: they decide which instruments need a full-history rewrite, and that has
    # to be known before a single bar is written (module docstring, "the re-basing rule").
    # Only events we might not already know about matter. On a backfill that is everything
    # since the floor; on a nightly it is everything since the OLDEST watermark, because an
    # action older than every row we hold cannot have invalidated any of them.
    actions_from = since
    if watermarks and not args.backfill:
        actions_from = max(since, min(watermarks.values()) - dt.timedelta(days=REPULL_SESSIONS * 2))
    actions = pd.DataFrame(columns=pd.Index(ACTION_COLUMNS))
    actions_ok = True
    try:
        actions = provider.actions(symbols, actions_from, eod)
    except ImportError:
        # A missing package is a BROKEN INSTALL, not a feed outage, and the two deserve
        # opposite responses. Seen on a real first run: the `global` extra was not installed,
        # `import alpaca` raised, and this block cheerfully announced the vendor unavailable
        # and elected to rewrite all 5,656 instruments from scratch. It crashed two lines
        # later on the same missing module so nothing was lost, but a variant where only the
        # actions path failed to import would have run a full re-backfill nightly and looked
        # like a vendor problem while being an `uv sync` away from correct.
        raise
    except Exception as exc:
        actions_ok = False
        print(f"  WARNING: corporate actions unavailable ({exc})")
    if actions_ok:
        rebase = rebasing_targets(actions, watermarks, since)
    else:
        # Not knowing which instruments re-based is not the same as none having: without the
        # event list every adjusted column could be on a stale base, so every target is
        # rewritten in full. Expensive and correct, rather than cheap and silently wrong.
        rebase = set(symbols)
        print("  → treating every target as re-based (a stale base is invisible in the row)")
    print(
        f"  actions: {len(actions):,d} event(s); {len(rebase):,d} instrument(s) need a full rewrite"
    )
    if provider.unmapped_actions:
        print(f"  action types dropped as unreadable: {dict(provider.unmapped_actions)}")

    written = 0
    action_written = 0
    skipped_dates = 0
    frames: list[pd.DataFrame] = []
    try:
        for start, batch in by_start(symbols, watermarks, since, rebase).items():
            if start > eod:
                for s in batch:
                    report.add(s, "up_to_date", 0, None, None, f"watermark {watermarks.get(s)}")
                continue
            per_basis = {b: provider.bars(batch, start, eod, adjustment=b) for b in BASES}
            merged = merge_bases(per_basis)
            if merged.empty:
                for s in batch:
                    report.add(s, "no_bars", 0, None, None, f"{start} → {eod}")
                continue
            bad = invalid_bars(merged)
            if len(bad):
                for r in bad.to_dict("records"):
                    report.add(
                        r["symbol"], "refused_bar", 1, r["date"], r["date"], "impossible OHLC"
                    )
                merged = pd.DataFrame(merged[~merged.index.isin(bad.index)])
            skipped_dates += int(merged["close_tr"].isna().sum())
            frames.append(merged)
            print(
                f"  {batch[0]}…{batch[-1]} ({len(batch)}): {len(merged):,d} bars "
                f"{start} → {eod}, {provider.calls['stocks/bars']} request(s) so far"
            )
    finally:  # the budget was spent whatever the run decides next
        _gdb.commit_provider_calls(eod, {SOURCE: provider.calls})

    frame = (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=pd.Index(COLUMNS))
    )
    for sym, g in frame.groupby("symbol"):
        report.add(sym, "ok", len(g), g["date"].min(), g["date"].max(), None)
    print(
        f"  merged {len(frame):,d} bars over {frame['symbol'].nunique() if len(frame) else 0} symbol(s)"
    )
    if skipped_dates:
        print(
            f"  NOTE: {skipped_dates:,d} bar(s) have raw prices but no total-return close {report.where()}"
        )

    if args.dry_run:
        print("  --dry-run: nothing written")
        report.close()
        return 0

    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            cur.execute(SPY_BAR_SQL, {"eod": eod})
            spy_before = scalar_or_none(cur)

            rows = price_rows(frame, ids)
            if rows:
                execute_values(
                    cur,
                    UPSERT_SQL,
                    rows,
                    template="("
                    + ", ".join(["%s"] * len(COLUMNS))
                    + f", '{SOURCE}', '{ADJUSTMENT_SOURCE}', now())",
                    page_size=1000,
                )
                written = len(rows)

            arows, aconflicts = action_rows(actions, ids)
            for (iid, ex_date, kind), values in aconflicts:
                report.add(
                    iid,
                    "action_conflict",
                    len(values),
                    ex_date,
                    ex_date,
                    f"{kind}: {len(values)} records disagree "
                    f"({', '.join(str(v) for v in values)}) — none written",
                )
            if arows:
                execute_values(
                    cur,
                    ACTIONS_UPSERT_SQL,
                    arows,
                    template="("
                    + ", ".join(["%s"] * len(ACTION_DB_COLUMNS))
                    + f", '{SOURCE}', now())",
                    page_size=1000,
                )
                action_written = len(arows)

            # The anchor check runs AFTER the write and inside the same transaction, so the
            # bars this run just fetched count — a cold start would otherwise refuse itself.
            cur.execute(SPY_BAR_SQL, {"eod": eod})
            spy_after = scalar_or_none(cur)
            if spy_after is None:
                conn.rollback()
                print(
                    f"  REFUSED: no SPY bar on or before {eod} even after this run "
                    f"(was {spy_before}) — no anchor session, so nothing is written"
                )
                report.close()
                return 2

            _gdb.record_state(
                cur,
                SOURCE,
                "ohlcv_daily",
                {
                    "since": since.isoformat(),
                    "eod": eod.isoformat(),
                    "scope": args.scope,
                    "targets": len(symbols),
                    "rows": written,
                    "actions": action_written,
                    "rebased": sorted(rebase)[:50],
                    "rebased_count": len(rebase),
                    "spy_last_bar": spy_after.isoformat(),
                    "run_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            )
    finally:
        conn.close()

    print(
        f"  upserted {written:,d} bars and {action_written:,d} action(s); "
        f"SPY anchor {spy_after}; {sum(report.counts.values()):,d} outcome(s) {report.where()}"
    )
    for status, n in sorted(report.counts.items()):
        print(f"    {status}: {n:,d}")
    report.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
