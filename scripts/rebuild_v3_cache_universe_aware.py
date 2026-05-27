"""Rebuild v3 OHLCV cache — survivorship-corrected via universe membership.

Variant of :mod:`scripts.rebuild_v3_cache` that respects the historical
universe track in ``atlas.atlas_universe_stocks``. The cache contains
OHLCV for every instrument-date pair where the instrument was an active
member of the curated 750-name universe AT THAT TIME (per
``effective_from`` / ``effective_to`` semantics).

Why this exists
---------------
The plain v3 cache pulled the entire ``de_equity_ohlcv`` table (~2,294
iids). That broke the methodology lock: deep-search candidates fired
against names that were never in the universe (illiquid bucket-shop
tickers, ETF wrappers, etc).

v2 took the opposite extreme: scoped to a static present-day universe,
killing the cache for any name that left the universe (Yes Bank circa
2018, DHFL circa 2019, Vodafone-Idea pattern).

This script splits the difference:

* INNER JOIN against ``atlas.atlas_universe_stocks`` — gates to the 750
  curated names + any historical members.
* Respect ``effective_from`` / ``effective_to`` — pull OHLCV only for
  dates the instrument was an active universe member.

Output schema matches :mod:`scripts.rebuild_v3_cache` exactly so
:func:`atlas.discovery.engine._load_cache_files` consumes it without
modification (``date``, ``iid``, ``close``, ``volume``).

CLI
---
    python scripts/rebuild_v3_cache_universe_aware.py \\
        --output /tmp/sde_ohlcv_cache_v3_uniaware.pkl \\
        --since 2014-01-01
"""

# allow-large: single-purpose EC2 utility — connects to DB, streams
# OHLCV through universe-aware JOIN, builds Nifty benchmark, emits
# cache pickles. Splitting would force shared CLI plumbing for no
# testability win.

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = Path("/tmp/sde_ohlcv_cache_v3_uniaware.pkl")  # noqa: S108
DEFAULT_SINCE = date(2014, 1, 1)
CHUNK_SIZE = 200_000
NIFTY500_INDEX_SYMBOL = "NIFTY 500"
STALENESS_WARN_DAYS = 5

logger = logging.getLogger("rebuild_v3_cache_universe_aware")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UniAwareRebuildStats:
    """Summary stats for one universe-aware rebuild run."""

    total_rows: int
    unique_instruments: int
    universe_iids: int
    historical_only_iids: int
    currently_active_iids: int
    cap_tier_counts: dict[str, int]
    date_min: pd.Timestamp | None
    date_max: pd.Timestamp | None
    duration_s: float
    output_path: Path
    nifty500_path: Path
    blacklist_path: Path
    pickle_size_bytes: int


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def _get_engine() -> Engine:
    """Lazy import of atlas.db so this script works without the full package."""
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


# ---------------------------------------------------------------------------
# Universe-aware OHLCV fetch
# ---------------------------------------------------------------------------


def _fetch_ohlcv_universe_aware(engine: Engine, since: date) -> pd.DataFrame:
    """Stream OHLCV filtered by universe membership at each date.

    JOIN semantics:
      INNER JOIN atlas.atlas_universe_stocks u ON u.instrument_id = o.instrument_id
      WHERE (u.effective_to IS NULL OR o.date <= u.effective_to)

    The ``effective_from`` lower-bound is intentionally NOT applied as a
    date filter. Today the universe table is a present-day snapshot
    (every row has ``effective_from = UNIVERSE_LOCK_DATE``), so an
    ``o.date >= u.effective_from`` filter would clip the cache to ~17
    days of data — useless for 1m/3m/6m/12m walk-forwards.

    The right intent of effective_from is "first date this row's
    metadata was authoritative", not "first date this instrument was
    universe-eligible". We treat universe membership as INNER JOIN by
    iid, with future effective_to support if/when the universe gets a
    real historical track (the Yes Bank / DHFL / Vodafone-Idea
    survivorship-correction pattern).

    A given instrument may appear multiple times in the universe table
    if it was added / removed / re-added — the JOIN + downstream dedup
    handle this correctly when that data lands.

    Returns:
        Long DataFrame (date, iid, close, volume) — matches the contract
        :func:`atlas.discovery.engine._load_cache_files` consumes.
    """
    # Paginate by year. A single full-history scan is killed by the
    # Supabase pooler's statement_timeout (~5 min); per-year slices each
    # finish well under the cap.
    sql_year = text(
        """
        SELECT o.date,
               o.instrument_id::text AS iid,
               o.close_adj           AS close,
               o.volume
        FROM public.de_equity_ohlcv o
        INNER JOIN atlas.atlas_universe_stocks u
          ON u.instrument_id = o.instrument_id
        WHERE o.date >= CAST(:y_start AS DATE)
          AND o.date <  CAST(:y_end   AS DATE)
          AND (u.effective_to IS NULL OR o.date <= u.effective_to)
          AND o.close_adj IS NOT NULL
          AND o.volume    IS NOT NULL
        """
    )

    chunks: list[pd.DataFrame] = []
    rows_so_far = 0
    t0 = time.monotonic()
    start_year = since.year
    end_year = date.today().year + 1
    year_slices = [
        (date(y, 1, 1) if y > start_year else since, date(y + 1, 1, 1))
        for y in range(start_year, end_year)
    ]
    try:
        for y_start, y_end in year_slices:
            # Fresh connection per slice keeps the pooler happy.
            with engine.connect() as conn:
                try:
                    conn.execute(text("SET statement_timeout = 0"))
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                year_result = conn.execute(sql_year, {"y_start": y_start, "y_end": y_end})
                cols: list[Any] = list(year_result.keys())
                batch = year_result.fetchall()
            if not batch:
                logger.info(
                    "v3_uniaware_year_empty",
                    extra={"y_start": str(y_start), "y_end": str(y_end)},
                )
                continue
            df = pd.DataFrame(batch, columns=cast(Any, cols))
            chunks.append(df)
            rows_so_far += len(df)
            logger.info(
                "v3_uniaware_fetch_progress",
                extra={
                    "rows_fetched": rows_so_far,
                    "elapsed_s": round(time.monotonic() - t0, 1),
                    "chunks": len(chunks),
                },
            )
    except Exception:
        raise

    if not chunks:
        raise RuntimeError(
            f"v3 universe-aware cache rebuild: zero rows returned for date >= {since}. "
            "Check ATLAS_DB_URL, de_equity_ohlcv coverage, and atlas.atlas_universe_stocks."
        )

    df_combined = cast(pd.DataFrame, pd.concat(chunks, ignore_index=True, copy=False))
    df_combined["date"] = pd.to_datetime(df_combined["date"])
    df_combined["iid"] = df_combined["iid"].astype(str)
    df_combined["close"] = df_combined["close"].astype(float)
    df_combined["volume"] = df_combined["volume"].astype("int64")
    # OHLCV may have duplicates if an iid had multiple universe-membership
    # windows that overlap (defensive — current universe data doesn't have
    # this, but guard anyway). Keep first occurrence; orderly dedup.
    df_combined = df_combined.drop_duplicates(subset=["date", "iid"], keep="first")
    return cast(pd.DataFrame, df_combined[["date", "iid", "close", "volume"]])


def _fetch_nifty500(engine: Engine, since: date) -> pd.Series:
    """Fetch Nifty 500 benchmark closes.

    Note: ``public.de_index_prices`` uses ``index_code`` (not ``symbol``)
    as the index identifier column. Lookup is case-sensitive against the
    canonical ``NIFTY 500`` value (no UPPER() wrap needed).
    """
    sql = text(
        """
        SELECT date, close
        FROM public.de_index_prices
        WHERE index_code = :sym
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


# ---------------------------------------------------------------------------
# Universe diagnostics
# ---------------------------------------------------------------------------


def _fetch_universe_diagnostics(engine: Engine) -> dict[str, Any]:
    """Pull tier distribution + active vs historical counts from the universe.

    Used purely for the diagnostic printout — never alters the cache.
    """
    sql = text(
        """
        SELECT instrument_id::text AS iid,
               tier,
               effective_from,
               effective_to
        FROM atlas.atlas_universe_stocks
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    if not rows:
        return {
            "universe_iids": 0,
            "currently_active": 0,
            "historical_only": 0,
            "cap_tier_counts": {},
        }
    df = pd.DataFrame(rows, columns=cast(Any, ["iid", "tier", "effective_from", "effective_to"]))
    active = df[df["effective_to"].isna()]
    historical = df[df["effective_to"].notna()]
    return {
        "universe_iids": int(df["iid"].nunique()),
        "currently_active": int(active["iid"].nunique()),
        "historical_only": int(historical["iid"].nunique()),
        "cap_tier_counts": dict(Counter(active["tier"].astype(str).tolist())),
    }


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rebuild_v3_cache_universe_aware",
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


def rebuild_v3_cache_universe_aware(
    *,
    output: Path,
    since: date,
    nifty500_output: Path | None,
    blacklist_output: Path | None,
    inherit_blacklist: Path | None,
    engine: Engine | None = None,
) -> UniAwareRebuildStats:
    """Pull universe-aware OHLCV from DB; emit v3 cache pickle + companions."""
    t0 = time.monotonic()
    engine = engine if engine is not None else _get_engine()

    output = output.resolve()
    out_dir = output.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    nifty500_path = nifty500_output.resolve() if nifty500_output else out_dir / "nifty500_cache.pkl"
    blacklist_path = (
        blacklist_output.resolve() if blacklist_output else out_dir / "iid_blacklist.json"
    )

    # --- 1. Universe membership context (for diagnostics) ---
    uni_diag = _fetch_universe_diagnostics(engine)
    logger.info("v3_uniaware_universe_diagnostics", extra=uni_diag)

    # --- 2. OHLCV (universe-aware INNER JOIN) ---
    logger.info("v3_uniaware_fetch_start", extra={"since": str(since)})
    df = _fetch_ohlcv_universe_aware(engine, since)
    logger.info(
        "v3_uniaware_fetch_done",
        extra={
            "rows": len(df),
            "iids": int(df["iid"].nunique()),
            "elapsed_s": round(time.monotonic() - t0, 1),
        },
    )

    # --- 3. Nifty 500 ---
    nifty = _fetch_nifty500(engine, since)
    logger.info(
        "nifty500_fetched",
        extra={"rows": len(nifty), "date_min": str(nifty.index.min() if len(nifty) else None)},
    )

    # --- 4. Blacklist (inherit or empty) ---
    if inherit_blacklist is not None:
        if not inherit_blacklist.exists():
            raise FileNotFoundError(f"--inherit-blacklist not found: {inherit_blacklist}")
        with inherit_blacklist.open() as fh:
            blacklist_payload = json.load(fh)
    else:
        blacklist_payload = []

    # --- 5. Persist ---
    df.to_pickle(output)
    nifty.to_pickle(nifty500_path)
    with blacklist_path.open("w") as fh:
        json.dump(blacklist_payload, fh, indent=2)

    duration = time.monotonic() - t0
    date_min_val = df["date"].min()
    date_max_val = df["date"].max()
    stats = UniAwareRebuildStats(
        total_rows=len(df),
        unique_instruments=int(df["iid"].nunique()),
        universe_iids=int(uni_diag["universe_iids"]),
        historical_only_iids=int(uni_diag["historical_only"]),
        currently_active_iids=int(uni_diag["currently_active"]),
        cap_tier_counts=cast(dict[str, int], uni_diag["cap_tier_counts"]),
        date_min=cast("pd.Timestamp | None", date_min_val),
        date_max=cast("pd.Timestamp | None", date_max_val),
        duration_s=duration,
        output_path=output,
        nifty500_path=nifty500_path,
        blacklist_path=blacklist_path,
        pickle_size_bytes=output.stat().st_size,
    )

    if stats.date_max is not None:
        days_stale = (pd.Timestamp(date.today()) - stats.date_max).days
        if days_stale > STALENESS_WARN_DAYS:
            logger.warning(
                "v3_uniaware_cache_data_stale",
                extra={
                    "max_date": str(stats.date_max.date()),
                    "days_stale": days_stale,
                    "warn_threshold": STALENESS_WARN_DAYS,
                },
            )

    return stats


def _print_stats(stats: UniAwareRebuildStats) -> None:
    print()
    print("=" * 72)
    print("v3 universe-aware cache rebuild — summary")
    print("=" * 72)
    print(f"  output:                {stats.output_path}")
    print(f"  pickle size:           {stats.pickle_size_bytes / 1e6:,.1f} MB")
    print(f"  nifty500:              {stats.nifty500_path}")
    print(f"  blacklist:             {stats.blacklist_path}")
    print(f"  total rows:            {stats.total_rows:,}")
    print(f"  unique instruments:    {stats.unique_instruments:,}")
    print(f"  universe iids (table): {stats.universe_iids:,}")
    print(f"    currently active:    {stats.currently_active_iids:,}")
    print(f"    historical-only:     {stats.historical_only_iids:,}")
    print(f"  cap_tier (active):     {stats.cap_tier_counts}")
    print(f"  date range:            {stats.date_min} → {stats.date_max}")
    print(f"  duration:              {stats.duration_s:,.1f} s")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    args = _build_cli_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        stats = rebuild_v3_cache_universe_aware(
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
