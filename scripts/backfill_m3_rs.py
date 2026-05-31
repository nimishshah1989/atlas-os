"""M3 RS standardization backfill — coordinated, vectorized, UPDATE-only.

Recomputes ONLY the columns the M3 RS standardization changed (ADR-0001 /
ADR-0002), across the v6 ~2-year window, and writes them onto EXISTING rows via
temp-table ``UPDATE … FROM`` (never ``INSERT … ON CONFLICT`` — see the
v6-mv-and-backfill-gotchas note: NOT NULL columns like ``regime_state`` /
state columns would raise on the candidate insert row before the conflict
arbiter redirects to DO UPDATE).

Stages (run in dependency order — each commits before the next reads):

  A. stocks   — ret_24m, rs_{1d,1w,1m,3m,6m,12m,24m}_tier (relative form +
                Nifty50 Large anchor), rs_{…}_tier_gold (direct stock-vs-gold).
  B. indices  — ret_24m (Nifty500 24m denominator for sector 24m RS).
  C. sectors  — bottomup_rs_{1d,1w,1m,6m,12m,24m}_nifty500 (reads corrected
                stock ret_* + index ret_24m; 3m unchanged, left as-is).

No regime stage: ``pct_stocks_rs_positive`` is computed-and-discarded (not in
regime METRICS_COLUMNS; absent from every prod table/view/matview), and
``regime_state`` classifies off price breadth, not RS. ``participation_rs`` is
rs_state-derived and invariant. So no persisted breadth/regime column changes.

Every computation reuses the vectorised compute primitives (groupby pct_change /
column arithmetic) — no row loops, no iterrows/apply.

Usage (run detached on EC2):
    setsid nohup python -m scripts.backfill_m3_rs --start 2024-05-01 \
        --end 2026-05-31 --stage all > /tmp/m3_backfill.log 2>&1 &

``--dry-run`` computes + logs before/after row counts but writes nothing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import pandas as pd
import structlog
from psycopg2.extras import execute_values

from atlas.compute._session import df_to_pg_rows
from atlas.compute.benchmarks import (
    add_relative_strength,
    materialize_benchmark_cache,
    merge_tier_benchmark,
)
from atlas.compute.indices import load_index_prices
from atlas.compute.primitives import RS_WINDOWS, WINDOWS, add_returns
from atlas.compute.sectors import (
    compute_bottom_up_sector_metrics,
    load_nifty500_returns,
    load_sector_master,
    load_sector_stock_data,
)
from atlas.compute.stocks import (
    _gold_relative_strength,
    _load_ohlcv,
    _load_universe,
)
from atlas.db import get_engine

log = structlog.get_logger()

PAGE_SIZE = 5_000

# Trading-day warm-up for the 504-day (24m) window needs ~2 calendar years of
# prior history; load this many extra calendar days before the target start.
_LOOKBACK_DAYS = 760

_STOCK_RS_COLS = tuple(f"rs_{w}_tier" for w in RS_WINDOWS)
_STOCK_GOLD_COLS = tuple(f"rs_{w}_tier_gold" for w in RS_WINDOWS)
# 3m is unchanged (already relative form + persisted pre-M3) — exclude it.
_SECTOR_RS_COLS = tuple(f"bottomup_rs_{w}_nifty500" for w in RS_WINDOWS if w != "3m")


def _temp_update(
    raw_conn,
    *,
    table: str,
    pk_cols: tuple[str, ...],
    value_cols: tuple[str, ...],
    rows: list[tuple],
) -> int:
    """Load ``rows`` into a temp table and ``UPDATE … FROM`` ``table`` on ``pk_cols``.

    Writes only ``value_cols`` onto rows that already exist — never inserts, so
    NOT NULL columns the backfill doesn't touch are never violated. Caller owns
    the transaction. ``rows`` tuples are ordered ``(*pk_cols, *value_cols)``.
    """
    if not rows:
        return 0
    all_cols = (*pk_cols, *value_cols)
    pk_defs = ", ".join(f"{c} {'date' if c == 'date' else 'text'}" for c in pk_cols)
    val_defs = ", ".join(f"{c} numeric" for c in value_cols)
    pk_clause = ", ".join(pk_cols)
    set_clause = ", ".join(f"{c} = s.{c}" for c in value_cols)
    join_clause = " AND ".join(f"t.{c} = s.{c}" for c in pk_cols)

    cur = raw_conn.cursor()
    cur.execute("SET statement_timeout = 0")
    cur.execute("DROP TABLE IF EXISTS _bf_m3")
    cur.execute(
        f"CREATE TEMP TABLE _bf_m3 ({pk_defs}, {val_defs}, PRIMARY KEY ({pk_clause})) ON COMMIT DROP"
    )
    execute_values(
        cur,
        f"INSERT INTO _bf_m3 ({', '.join(all_cols)}) VALUES %s",
        rows,
        page_size=PAGE_SIZE,
    )
    cur.execute(f"UPDATE atlas.{table} t SET {set_clause} FROM _bf_m3 s WHERE {join_clause}")
    return cur.rowcount


def _commit_update(eng, *, table, pk_cols, value_cols, frame, dry_run):
    """Reindex ``frame`` to (pk + value) cols, drop all-NA value rows, write."""
    keep = [*pk_cols, *value_cols]
    out = frame.reindex(columns=keep).dropna(subset=list(value_cols), how="all")
    log.info(
        "m3_backfill_stage_rowcounts",
        table=table,
        computed_rows=len(frame),
        writable_rows=len(out),
        **{f"{c}_nonnull": int(out[c].notna().sum()) for c in value_cols if c in out},
    )
    if dry_run or out.empty:
        return 0
    raw = eng.raw_connection()
    try:
        n = _temp_update(
            raw, table=table, pk_cols=pk_cols, value_cols=value_cols, rows=df_to_pg_rows(out)
        )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    log.info("m3_backfill_stage_written", table=table, rows_written=n)
    return n


# --------------------------------------------------------------------------- #
# Stage A — stocks                                                            #
# --------------------------------------------------------------------------- #


def backfill_stocks(eng, *, start: date, end: date, dry_run: bool) -> int:
    load_start = start - timedelta(days=_LOOKBACK_DAYS)
    universe = _load_universe(eng)
    cache = materialize_benchmark_cache(eng, start=load_start, end=end)
    ohlcv = _load_ohlcv(
        eng, instrument_ids=universe["instrument_id"].tolist(), start=load_start, end=end
    )
    if ohlcv.empty:
        log.warning("m3_stocks_no_ohlcv")
        return 0

    df = ohlcv.merge(universe[["instrument_id", "tier"]], on="instrument_id", how="left")
    df = add_returns(df, group_col="instrument_id", price_col="close")
    df = merge_tier_benchmark(df, cache, tier_col="tier")
    df = add_relative_strength(df, windows={w: WINDOWS[w] for w in RS_WINDOWS})
    df = _gold_relative_strength(df, cache)

    # Write only the target window onto existing rows.
    df = df.loc[(df["date"] >= start) & (df["date"] <= end)]
    value_cols = ("ret_24m", *_STOCK_RS_COLS, *_STOCK_GOLD_COLS)
    return _commit_update(
        eng,
        table="atlas_stock_metrics_daily",
        pk_cols=("instrument_id", "date"),
        value_cols=value_cols,
        frame=df,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- #
# Stage B — indices (ret_24m only)                                            #
# --------------------------------------------------------------------------- #


def backfill_indices(eng, *, start: date, end: date, dry_run: bool) -> int:
    # load_index_prices applies its own ~900-day (~620 trading-day) lookback,
    # enough to warm the 504-day (24m) window at the target start.
    prices = load_index_prices(eng, start, end)
    if prices.empty:
        log.warning("m3_indices_no_prices")
        return 0
    df = add_returns(prices, group_col="index_code", price_col="close", windows={"24m": 504})
    df = df.loc[(df["date"] >= start) & (df["date"] <= end)]
    return _commit_update(
        eng,
        table="atlas_index_metrics_daily",
        pk_cols=("index_code", "date"),
        value_cols=("ret_24m",),
        frame=df,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- #
# Stage C — sectors (depends on corrected stock + index ret_*)                #
# --------------------------------------------------------------------------- #


def backfill_sectors(eng, *, start: date, end: date, dry_run: bool) -> int:
    stock_data = load_sector_stock_data(eng, start, end)
    if stock_data.empty:
        log.warning("m3_sectors_no_stock_data")
        return 0
    master = load_sector_master(eng)
    n500 = load_nifty500_returns(eng, start, end)
    bu = compute_bottom_up_sector_metrics(stock_data, master, df_nifty500_returns=n500)
    bu = bu.loc[(bu["date"] >= start) & (bu["date"] <= end)]
    return _commit_update(
        eng,
        table="atlas_sector_metrics_daily",
        pk_cols=("sector_name", "date"),
        value_cols=_SECTOR_RS_COLS,
        frame=bu,
        dry_run=dry_run,
    )


# NOTE: there is deliberately no regime stage. The brief listed
# ``pct_stocks_rs_positive`` for backfill, but prod introspection confirmed it is
# NOT persisted anywhere (absent from regime ``METRICS_COLUMNS`` and from every
# table/view/matview), and ``regime_state`` classifies off price breadth
# (``pct_above_ema_50``), not RS — so the anchor/form change touches no persisted
# regime/breadth column. ``participation_rs`` (sectors) is likewise rs_state-derived
# and invariant. Only display RS columns change. See ADR-0001/0002.


_STAGES = {
    "stocks": backfill_stocks,
    "indices": backfill_indices,
    "sectors": backfill_sectors,
}
# Dependency order: stocks + indices must commit before sectors reads them back.
_ALL_ORDER = ("stocks", "indices", "sectors")


def main() -> int:
    parser = argparse.ArgumentParser(description="M3 RS standardization backfill (UPDATE-only)")
    parser.add_argument(
        "--start", type=str, default=None, help="YYYY-MM-DD (default: 2yr before end)"
    )
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--stage",
        choices=[*_ALL_ORDER, "all"],
        default="all",
        help="Which stage to run (default: all, in dependency order)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute + log counts, write nothing"
    )
    args = parser.parse_args()

    end = pd.to_datetime(args.end).date() if args.end else date.today()
    start = pd.to_datetime(args.start).date() if args.start else end - timedelta(days=730)
    eng = get_engine()

    stages = _ALL_ORDER if args.stage == "all" else (args.stage,)
    log.info(
        "m3_backfill_start", start=str(start), end=str(end), stages=stages, dry_run=args.dry_run
    )
    total = 0
    for name in stages:
        log.info("m3_backfill_stage_begin", stage=name)
        total += _STAGES[name](eng, start=start, end=end, dry_run=args.dry_run)
    log.info("m3_backfill_done", total_rows_written=total, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
