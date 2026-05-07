#!/usr/bin/env python3
"""Atlas-M1 entry point — Schema and Reference Data.

Runs the M1 milestone end-to-end:

1. Verify Supabase connectivity and ``atlas`` schema exists
2. Run all Alembic migrations (001-010) to create tables / indexes / roles
3. Lock the universe (sectors, benchmarks, stocks, ETFs, indices, funds,
   thresholds)
4. Print the readiness summary

Usage::

    # Sanity check first
    python -m atlas.db

    # Apply all migrations and lock universe
    python scripts/m1_run.py

    # Optional: just lock universe (assumes migrations already applied)
    python scripts/m1_run.py --no-migrations

The script is idempotent — re-running upserts existing rows. Safe to invoke
multiple times during M1 dry-runs.
"""

from __future__ import annotations

import argparse
import sys
import time

import structlog

from atlas.config import Config
from atlas.db import get_engine, sanity_check
from atlas.universe.lock import lock_universe

log = structlog.get_logger()


def _run_alembic_migrations() -> None:
    """Invoke Alembic in-process to apply all migrations to head."""
    # Import lazily so module-import doesn't require alembic available
    # in environments that just need universe-lock helpers.
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig("alembic.ini")
    log.info("alembic_upgrade_starting", target="head")
    command.upgrade(cfg, "head")
    log.info("alembic_upgrade_complete")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas-M1 runner")
    parser.add_argument(
        "--no-migrations",
        action="store_true",
        help="Skip Alembic migrations (assumes tables already exist)",
    )
    parser.add_argument(
        "--no-universe",
        action="store_true",
        help="Skip universe lock (only run migrations)",
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("Atlas-M1 — Schema and Reference Data")
    print(f"  ATLAS_DB_URL set: {bool(Config.DB_URL)}")
    print(f"  Lock date:        {Config.UNIVERSE_LOCK_DATE}")
    print(f"  Historical start: {Config.HISTORICAL_START_DATE}")
    print("=" * 60)

    # Step 1 — sanity check
    print("\nStep 1: Connectivity sanity check...")
    try:
        result = sanity_check()
        for k, v in result.items():
            print(f"  {k:24s} {v}")
    except Exception as exc:
        log.exception("sanity_check_failed", error=str(exc))
        print(f"\n✗ Sanity check failed: {exc}")
        print("  Verify ATLAS_DB_URL points at a reachable Supabase Postgres.")
        return 2

    # Step 2 — migrations
    if args.no_migrations:
        print("\nStep 2: Migrations skipped (--no-migrations).")
    else:
        print("\nStep 2: Running Alembic migrations to head...")
        t0 = time.monotonic()
        try:
            _run_alembic_migrations()
        except Exception as exc:
            log.exception("alembic_failed", error=str(exc))
            print(f"\n✗ Migrations failed: {exc}")
            return 3
        print(f"  Migrations applied in {time.monotonic() - t0:.1f}s.")

    # Step 3 — universe lock
    if args.no_universe:
        print("\nStep 3: Universe lock skipped (--no-universe).")
        return 0

    print(
        "\nStep 3: Locking universe (sectors, benchmarks, stocks, ETFs, "
        "indices, funds, thresholds)..."
    )
    t0 = time.monotonic()
    try:
        counts = lock_universe(get_engine())
    except Exception as exc:
        log.exception("universe_lock_failed", error=str(exc))
        print(f"\n✗ Universe lock failed: {exc}")
        return 4
    elapsed = time.monotonic() - t0

    # Summary
    print("\n" + "=" * 60)
    print("M1 — Readiness Summary")
    print("=" * 60)
    for table in (
        "atlas_sector_master",
        "atlas_benchmark_master",
        "atlas_fund_category_benchmark_map",
        "atlas_universe_stocks",
        "atlas_universe_etfs",
        "atlas_universe_indices",
        "atlas_universe_funds",
        "atlas_thresholds",
    ):
        n = counts.get(table, 0)
        print(f"  {table:42s} {n:>6,d} rows")
    print(f"\n  Universe lock elapsed: {elapsed:.1f}s")
    print("\n→ Run validation: python -m atlas.validation.tier1_raw")
    print("→ Or proceed to M2 once validation report is signed off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
