#!/usr/bin/env python3
"""Incremental JIP RDS → Supabase sync for missing trading days.

Copies rows with date >= SYNC_FROM from JIP RDS into Supabase's public.de_* tables.
Safe to re-run: deletes the date range from Supabase first, then inserts fresh from JIP.

Usage:
    python3 scripts/jip_incremental_sync.py
    python3 scripts/jip_incremental_sync.py --from-date 2026-05-06
    python3 scripts/jip_incremental_sync.py --dry-run
    python3 scripts/jip_incremental_sync.py --table de_equity_ohlcv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.config import Config  # noqa: E402

log = structlog.get_logger()

# --- Configuration ---

DEFAULT_SYNC_FROM = "2026-05-06"

JIP_DB_URL = (
    "postgresql+psycopg2://"
    "jip_admin:JipDataEngine2026Secure"
    "@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432"
    "/data_engine"
    "?sslmode=require"
)

# Tables to sync with their date column names
# de_source_files must come first — de_equity_ohlcv has a FK on it
# NAV is now Atlas-owned (scripts/foundation/ingest_nav.py pulls from AMFI/mfapi.in into
# atlas_foundation.de_mf_nav_daily directly) — removed from the JIP sync (consolidation
# step 2). The remaining OHLCV tables are still synced ONLY because the legacy dirty pages
# (Market Pulse, sector pulse) still read public.de_equity_ohlcv / de_index_prices; once
# step 5 repoints those pages to atlas_foundation.ohlcv_stock / index_prices, this whole
# script is retired.
TABLES: list[tuple[str, str]] = [
    ("de_source_files", "created_at"),
    ("de_equity_ohlcv", "date"),
    ("de_index_prices", "date"),
    ("de_etf_ohlcv", "date"),
    ("de_cron_run", "started_at"),
    ("de_pipeline_log", "started_at"),
]

CHUNK_SIZE = 5000


def get_jip_engine() -> Engine:
    return create_engine(JIP_DB_URL, pool_pre_ping=True, pool_size=2)


def get_supabase_engine() -> Engine:
    return create_engine(Config.assert_db_url(), pool_pre_ping=True, pool_size=2)


def count_rows(engine: Engine, table: str, date_col: str, from_date: str) -> int:
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 30000"))
        row = conn.execute(
            text(f"SELECT COUNT(*) FROM public.{table} WHERE {date_col} >= :d"),
            {"d": from_date},
        ).one()
    return int(row[0])


def sync_table(
    jip: Engine,
    supa: Engine,
    table: str,
    date_col: str,
    from_date: str,
    dry_run: bool,
) -> dict:
    log.info("sync_table_starting", table=table, from_date=from_date)

    jip_count = count_rows(jip, table, date_col, from_date)
    supa_before = count_rows(supa, table, date_col, from_date)
    print(f"  {table}: JIP={jip_count:,} rows  |  Supabase_before={supa_before:,} rows")

    if jip_count == 0:
        print(f"  {table}: nothing to sync (JIP has 0 new rows)")
        return {"table": table, "jip_rows": 0, "inserted": 0, "skipped": True}

    if dry_run:
        print(f"  {table}: DRY RUN — would delete {supa_before:,} and insert {jip_count:,}")
        return {"table": table, "jip_rows": jip_count, "inserted": 0, "dry_run": True}

    # Fetch from JIP in chunks
    with jip.connect() as jip_conn:
        jip_conn.execute(text("SET statement_timeout = 60000"))
        result = jip_conn.execute(
            text(f"SELECT * FROM public.{table} WHERE {date_col} >= :d ORDER BY {date_col}"),
            {"d": from_date},
        )
        columns = list(result.keys())
        rows = result.fetchall()

    print(f"  {table}: fetched {len(rows):,} rows from JIP RDS")

    # Delete existing range from Supabase then insert fresh
    with supa.begin() as supa_conn:
        deleted = supa_conn.execute(
            text(f"DELETE FROM public.{table} WHERE {date_col} >= :d"),
            {"d": from_date},
        ).rowcount
        print(f"  {table}: deleted {deleted:,} existing rows from Supabase")

        # Bulk insert in chunks
        inserted = 0
        for i in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[i : i + CHUNK_SIZE]
            col_list = ", ".join(columns)
            placeholders = ", ".join([f":{c}" for c in columns])
            supa_conn.execute(
                text(f"INSERT INTO public.{table} ({col_list}) VALUES ({placeholders})"),
                [dict(zip(columns, row, strict=False)) for row in chunk],
            )
            inserted += len(chunk)
            if len(rows) > CHUNK_SIZE:
                print(f"  {table}: inserted {inserted:,}/{len(rows):,}...", end="\r")

    supa_after = count_rows(supa, table, date_col, from_date)
    print(f"  {table}: DONE — inserted={inserted:,}, Supabase_after={supa_after:,}")

    if supa_after != jip_count:
        print(f"  WARNING: count mismatch! JIP={jip_count} vs Supabase={supa_after}")

    return {"table": table, "jip_rows": jip_count, "inserted": inserted, "supa_after": supa_after}


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental JIP RDS → Supabase sync")
    parser.add_argument("--from-date", default=DEFAULT_SYNC_FROM, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print counts, do not write")
    parser.add_argument("--table", help="Sync only this table name")
    args = parser.parse_args()

    print(f"JIP Incremental Sync: {args.from_date} → now")
    print(f"Dry run: {args.dry_run}")
    print()

    jip = get_jip_engine()
    supa = get_supabase_engine()

    # Connectivity check
    with jip.connect() as c:
        c.execute(text("SELECT 1"))
    print("JIP RDS: connected")

    with supa.connect() as c:
        c.execute(text("SELECT 1"))
    print("Supabase: connected")
    print()

    tables_to_sync = TABLES
    if args.table:
        tables_to_sync = [(t, c) for t, c in TABLES if t == args.table]
        if not tables_to_sync:
            print(f"Unknown table: {args.table}. Options: {[t for t, _ in TABLES]}")
            return 1

    results = []
    for table, date_col in tables_to_sync:
        print(f"[{table}]")
        try:
            r = sync_table(jip, supa, table, date_col, args.from_date, args.dry_run)
            results.append(r)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({"table": table, "error": str(exc)})
        print()

    print("=== SUMMARY ===")
    total_inserted = sum(r.get("inserted", 0) for r in results)
    errors = [r for r in results if "error" in r]
    print(f"Tables synced: {len(results) - len(errors)}/{len(results)}")
    print(f"Total rows inserted: {total_inserted:,}")
    if errors:
        print(f"Errors: {[r['table'] for r in errors]}")
        return 1

    print("Sync complete. Run Atlas backfill next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
