#!/usr/bin/env python3
"""Historical backfill for atlas_lens_scores_daily.

Runs the six-lens pipeline point-in-time for each trading day in a date range,
producing the historical journal required by the Loop-A gate (≥250 dates).

Usage:
    python backfill_lenses.py                     # auto: last 300 trading days
    python backfill_lenses.py --start 2025-05-16  # from a specific date
    python backfill_lenses.py --workers 4         # parallelism (≤6)

Resumable: skips dates already present in atlas_lens_scores_daily.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

# Ensure repo root is on PYTHONPATH so workers can import atlas.*
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.environ.setdefault("PYTHONPATH", _REPO_ROOT)

import _db


def _get_trading_dates(start: date, end: date) -> list[date]:
    """Return real NSE trading days between start and end (inclusive).

    Sourced from the NIFTY 50 session calendar (foundation_staging.index_prices),
    NOT raw technical_daily DISTINCT dates — the latter carry sparse 2-/10-row
    junk rows on NSE holidays (e.g. Republic Day 2026-01-26) which previously
    leaked 6 non-session dates into the scored journal.
    """
    df = _db.read_df(
        "SELECT DISTINCT date FROM foundation_staging.index_prices "
        "WHERE index_code = 'NIFTY 50' AND date >= :s AND date <= :e ORDER BY date",
        params={"s": start, "e": end},
    )
    return [d.date() if hasattr(d, "date") else d for d in df["date"].tolist()]


def _get_done_dates() -> set[date]:
    """Return dates already present in atlas_lens_scores_daily for stocks."""
    df = _db.read_df(
        "SELECT DISTINCT date FROM atlas.atlas_lens_scores_daily "
        "WHERE asset_class = 'stock'"
    )
    return {d.date() if hasattr(d, "date") else d for d in df["date"].tolist()}


def _init_worker():
    """Ensure repo root is on sys.path in spawned workers."""
    import sys
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)


def _run_one_date(dt: date) -> dict:
    """Run the lens pipeline for a single date. Called in a worker process."""
    import sys
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from atlas.lenses.pipeline import run_pipeline
    return run_pipeline(as_of=dt)


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill lens scores historically")
    ap.add_argument("--start", type=date.fromisoformat, default=None,
                    help="Start date (default: 400 calendar days ago)")
    ap.add_argument("--end", type=date.fromisoformat, default=None,
                    help="End date (default: latest technical_daily date)")
    ap.add_argument("--workers", type=int, default=4,
                    help="Max parallel workers (≤6, default 4)")
    args = ap.parse_args()

    end_dt = args.end or date.fromisoformat(
        str(_db.scalar(
            "SELECT max(date) FROM foundation_staging.index_prices "
            "WHERE index_code = 'NIFTY 50'"
        ))
    )
    start_dt = args.start or (end_dt - timedelta(days=400))
    workers = min(args.workers, 6)

    print(f"Backfill range: {start_dt} → {end_dt}, workers={workers}")

    all_dates = _get_trading_dates(start_dt, end_dt)
    done = _get_done_dates()
    todo = [d for d in all_dates if d not in done]

    print(f"Trading days in range: {len(all_dates)}, already done: {len(done)}, "
          f"remaining: {len(todo)}")

    if not todo:
        print("Nothing to do — all dates already computed.")
        return

    t0 = time.time()
    completed = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one_date, d): d for d in todo}
        for fut in as_completed(futures):
            dt = futures[fut]
            try:
                summary = fut.result()
                completed += 1
                elapsed = time.time() - t0
                rate = completed / elapsed * 60
                print(f"  [{completed}/{len(todo)}] {dt}: "
                      f"scored={summary['instruments_scored']}, "
                      f"skipped={summary['instruments_skipped']} "
                      f"({rate:.1f} dates/min)")
            except Exception as e:
                failed += 1
                print(f"  [FAIL] {dt}: {e!r}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"\nDone: {completed} dates computed, {failed} failed, "
          f"in {elapsed:.0f}s ({elapsed/60:.1f}min)")


if __name__ == "__main__":
    main()
