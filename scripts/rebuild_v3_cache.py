"""Rebuild the v6 deep-search OHLCV cache from the full EC2 universe.

Run on EC2 (Supabase / atlas-os DB). Produces a pickle compatible with
:func:`atlas.discovery.engine._load_cache_files` (same shape as the v2
cache at ``/tmp/sde_ohlcv_cache.pkl``), but spanning ALL ~2,294 iids in
``public.de_equity_ohlcv`` instead of the curated 727-name v2 subset.

Output shape (per :mod:`atlas.discovery.engine` contract):

    pd.DataFrame columns = ['date', 'iid', 'close', 'volume']
    dtypes               = [datetime64[ns], object/str, float64, int64]

The companion ``nifty500_cache.pkl`` and ``iid_blacklist.json`` are
emitted alongside so the engine's ``_load_cache_files`` is fully
satisfied:

* ``--output``                  → primary OHLCV pickle (default
  ``/tmp/sde_ohlcv_cache_v3.pkl``).
* ``--nifty500-output``         → Nifty 500 benchmark series pickle
  (defaults to ``<output_dir>/nifty500_cache.pkl``).
* ``--blacklist-output``        → blacklist JSON (defaults to
  ``<output_dir>/iid_blacklist.json``). Empty list by default — caller
  may pass ``--inherit-blacklist /tmp/iid_blacklist.json`` to keep v2's
  blacklist intact.

Chunked-fetch strategy
----------------------
The OHLCV table is ~4M rows. We pull in 200k-row chunks via SQLAlchemy
``execute(...).fetchmany(chunk_size)`` against a streaming connection
(``stream_results=True``) — never ``pd.read_sql`` an unbounded query.
Chunks are appended to a list of small DataFrames, then concat'd at the
end (one allocation, no quadratic copying).

CLI
---
    python scripts/rebuild_v3_cache.py \\
        --output /tmp/sde_ohlcv_cache_v3.pkl \\
        --since 2014-01-01
"""

# allow-large: single-purpose EC2 utility — connects to DB, streams
# OHLCV, builds Nifty benchmark, emits cache pickles. Splitting into
# multiple files would force shared CLI plumbing for no testability win.

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Defaults — keep aligned with atlas.discovery.engine.{OHLCV_,NIFTY500_,...}
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = Path("/tmp/sde_ohlcv_cache_v3.pkl")  # noqa: S108
DEFAULT_SINCE = date(2014, 1, 1)
CHUNK_SIZE = 200_000  # rows per fetchmany
NIFTY500_INDEX_SYMBOL = "NIFTY 500"

# Date sanity: warn if the database max(date) is older than this many days.
STALENESS_WARN_DAYS = 5

logger = logging.getLogger("rebuild_v3_cache")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RebuildStats:
    """Summary stats for a single rebuild run — printed at the end."""

    total_rows: int
    unique_instruments: int
    date_min: pd.Timestamp | None
    date_max: pd.Timestamp | None
    duration_s: float
    delisted_iids_in_data: int
    output_path: Path
    nifty500_path: Path
    blacklist_path: Path
    pickle_size_bytes: int


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def _get_engine() -> Engine:
    """Lazy import of atlas.db so this script works without the full package.

    Falls back to building an engine directly from ``ATLAS_DB_URL`` if
    ``atlas.db`` can't be imported (e.g. on a stripped EC2 venv).
    """
    try:
        from atlas.db import get_engine

        return get_engine()
    except Exception as exc:  # pragma: no cover — EC2-only fallback
        logger.info(
            "atlas_db_import_failed_falling_back_to_direct_engine",
            extra={"error": str(exc)},
        )
        from sqlalchemy import create_engine

        url = os.environ.get("ATLAS_DB_URL")
        if not url:
            raise RuntimeError("ATLAS_DB_URL not set; cannot build SQLAlchemy engine") from exc
        return create_engine(url, pool_pre_ping=True, pool_size=2)


def _fetch_ohlcv_chunked(engine: Engine, since: date) -> pd.DataFrame:
    """Stream OHLCV from the DB in CHUNK_SIZE row batches.

    Returns the assembled long DataFrame with columns
    ``(date, iid, close, volume)`` — the contract
    :func:`atlas.discovery.engine._load_cache_files` consumes.
    """
    sql = text(
        """
        SELECT date,
               instrument_id::text AS iid,
               close_adj           AS close,
               volume
        FROM public.de_equity_ohlcv
        WHERE date >= :since
          AND close_adj IS NOT NULL
          AND volume    IS NOT NULL
        ORDER BY instrument_id, date
        """
    )

    chunks: list[pd.DataFrame] = []
    rows_so_far = 0
    t0 = time.monotonic()
    # stream_results=True: server-side cursor; fetch in chunks instead of
    # buffering the entire result set client-side.
    conn = engine.connect().execution_options(stream_results=True, max_row_buffer=CHUNK_SIZE)
    try:
        result = conn.execute(sql, {"since": since})
        cols: list[Any] = list(result.keys())
        while True:
            batch = result.fetchmany(CHUNK_SIZE)
            if not batch:
                break
            # Each row is a SQLAlchemy Row; tuple() makes it pandas-friendly.
            df = pd.DataFrame(batch, columns=cast(Any, cols))
            chunks.append(df)
            rows_so_far += len(df)
            logger.info(
                "v3_cache_fetch_progress",
                extra={
                    "rows_fetched": rows_so_far,
                    "elapsed_s": round(time.monotonic() - t0, 1),
                    "chunks": len(chunks),
                },
            )
    finally:
        conn.close()

    if not chunks:
        raise RuntimeError(
            f"v3 cache rebuild: zero rows returned for date >= {since}. "
            "Check ATLAS_DB_URL + de_equity_ohlcv coverage."
        )

    df_combined = cast(pd.DataFrame, pd.concat(chunks, ignore_index=True, copy=False))

    # Normalise dtypes to match the v2 cache shape.
    # date: pandas datetime (the v2 cache uses datetime64[ns])
    df_combined["date"] = pd.to_datetime(df_combined["date"])
    df_combined["iid"] = df_combined["iid"].astype(str)
    df_combined["close"] = df_combined["close"].astype(float)
    df_combined["volume"] = df_combined["volume"].astype("int64")
    return cast(pd.DataFrame, df_combined[["date", "iid", "close", "volume"]])


def _fetch_nifty500(engine: Engine, since: date) -> pd.Series:
    """Fetch Nifty 500 benchmark closes from ``de_index_prices``.

    Returns a date-indexed Series. Empty Series if the index isn't found
    — the engine still works (panels that reference Nifty just get NaN).
    """
    sql = text(
        """
        SELECT date, close
        FROM public.de_index_prices
        WHERE UPPER(symbol) = :sym
          AND date >= :since
        ORDER BY date
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"sym": NIFTY500_INDEX_SYMBOL, "since": since}).fetchall()
    if not rows:
        logger.warning(
            "nifty500_index_not_found",
            extra={"symbol": NIFTY500_INDEX_SYMBOL, "since": str(since)},
        )
        return pd.Series([], name="nifty500", dtype="float64")
    df = pd.DataFrame(rows, columns=cast(Any, ["date", "close"]))
    df["date"] = pd.to_datetime(df["date"])
    series = df.set_index("date")["close"].astype(float)
    series.name = "nifty500"
    return cast(pd.Series, series)


def _identify_delisted_iids(df: pd.DataFrame, stale_threshold_days: int = 90) -> list[str]:
    """Return iids whose last trade is > stale_threshold_days ago.

    Audit aid only — used for the diagnostic printout. Does NOT filter
    the cache (delisted iids stay in v3; the engine's evaluator handles
    them).
    """
    if df.empty:
        return []
    today = pd.Timestamp(date.today())
    threshold = today - pd.Timedelta(days=stale_threshold_days)
    last_date = cast(pd.Series, df.groupby("iid")["date"].max())
    filtered = cast(pd.Series, last_date[last_date < threshold])
    return [str(x) for x in filtered.index.tolist()]


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rebuild_v3_cache",
        description=__doc__,
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output pickle path (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--since",
        type=lambda s: date.fromisoformat(s),
        default=DEFAULT_SINCE,
        help=f"Pull OHLCV from this date onward (default: {DEFAULT_SINCE.isoformat()})",
    )
    p.add_argument(
        "--nifty500-output",
        type=Path,
        default=None,
        help=("Path for Nifty 500 benchmark pickle. Defaults to <output-dir>/nifty500_cache.pkl."),
    )
    p.add_argument(
        "--blacklist-output",
        type=Path,
        default=None,
        help=(
            "Path for the iid blacklist JSON. "
            "Defaults to <output-dir>/iid_blacklist.json (empty list)."
        ),
    )
    p.add_argument(
        "--inherit-blacklist",
        type=Path,
        default=None,
        help=(
            "Optional: read an existing blacklist JSON and copy its contents "
            "to --blacklist-output. Use to preserve the v2 blacklist when "
            "rebuilding alongside."
        ),
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return p


def rebuild_v3_cache(
    *,
    output: Path,
    since: date,
    nifty500_output: Path | None,
    blacklist_output: Path | None,
    inherit_blacklist: Path | None,
    engine: Engine | None = None,
) -> RebuildStats:
    """Pull OHLCV from DB, build v3 cache pickle + companion files.

    Args:
        output: destination of the main OHLCV pickle.
        since: earliest date to pull.
        nifty500_output: optional override for the nifty500 pickle path.
        blacklist_output: optional override for the blacklist JSON path.
        inherit_blacklist: optional path to a v2 blacklist to copy.
        engine: optionally inject a SQLAlchemy engine (test seam).

    Returns:
        :class:`RebuildStats` with row count + unique iids + date range.
    """
    t0 = time.monotonic()
    engine = engine if engine is not None else _get_engine()

    output = output.resolve()
    out_dir = output.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    nifty500_path = nifty500_output.resolve() if nifty500_output else out_dir / "nifty500_cache.pkl"
    blacklist_path = (
        blacklist_output.resolve() if blacklist_output else out_dir / "iid_blacklist.json"
    )

    # --- 1. OHLCV ---
    logger.info("v3_cache_fetch_start", extra={"since": str(since)})
    df = _fetch_ohlcv_chunked(engine, since)
    logger.info(
        "v3_cache_fetch_done",
        extra={
            "rows": len(df),
            "iids": int(df["iid"].nunique()),
            "elapsed_s": round(time.monotonic() - t0, 1),
        },
    )

    # --- 2. Nifty 500 benchmark ---
    nifty = _fetch_nifty500(engine, since)
    logger.info(
        "nifty500_fetched",
        extra={"rows": len(nifty), "date_min": str(nifty.index.min() if len(nifty) else None)},
    )

    # --- 3. Blacklist (inherit or empty) ---
    if inherit_blacklist is not None:
        if not inherit_blacklist.exists():
            raise FileNotFoundError(f"--inherit-blacklist not found: {inherit_blacklist}")
        with inherit_blacklist.open() as fh:
            blacklist_payload = json.load(fh)
    else:
        blacklist_payload = []

    # --- 4. Persist ---
    df.to_pickle(output)
    nifty.to_pickle(nifty500_path)
    with blacklist_path.open("w") as fh:
        json.dump(blacklist_payload, fh, indent=2)

    # --- 5. Diagnostics ---
    delisted = _identify_delisted_iids(df, stale_threshold_days=90)
    duration = time.monotonic() - t0

    date_min_val = df["date"].min()
    date_max_val = df["date"].max()
    stats = RebuildStats(
        total_rows=len(df),
        unique_instruments=int(df["iid"].nunique()),
        date_min=cast("pd.Timestamp | None", date_min_val),
        date_max=cast("pd.Timestamp | None", date_max_val),
        duration_s=duration,
        delisted_iids_in_data=len(delisted),
        output_path=output,
        nifty500_path=nifty500_path,
        blacklist_path=blacklist_path,
        pickle_size_bytes=output.stat().st_size,
    )

    # Staleness warning (don't fail — just shout).
    if stats.date_max is not None:
        days_stale = (pd.Timestamp(date.today()) - stats.date_max).days
        if days_stale > STALENESS_WARN_DAYS:
            logger.warning(
                "v3_cache_data_stale",
                extra={
                    "max_date": str(stats.date_max.date()),
                    "days_stale": days_stale,
                    "warn_threshold": STALENESS_WARN_DAYS,
                },
            )

    return stats


def _print_stats(stats: RebuildStats) -> None:
    print()
    print("=" * 72)
    print("v3 cache rebuild — summary")
    print("=" * 72)
    print(f"  output:              {stats.output_path}")
    print(f"  pickle size:         {stats.pickle_size_bytes / 1e6:,.1f} MB")
    print(f"  nifty500:            {stats.nifty500_path}")
    print(f"  blacklist:           {stats.blacklist_path}")
    print(f"  total rows:          {stats.total_rows:,}")
    print(f"  unique instruments:  {stats.unique_instruments:,}")
    print(f"  date range:          {stats.date_min} → {stats.date_max}")
    print(f"  delisted iids (>90d stale): {stats.delisted_iids_in_data}")
    print(f"  duration:            {stats.duration_s:,.1f} s")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    args = _build_cli_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        stats = rebuild_v3_cache(
            output=args.output,
            since=args.since,
            nifty500_output=args.nifty500_output,
            blacklist_output=args.blacklist_output,
            inherit_blacklist=args.inherit_blacklist,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _print_stats(stats)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
