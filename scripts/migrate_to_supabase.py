#!/usr/bin/env python3
"""
JIP Data Core → Supabase migration.

Deploy to jsl-wealth-server and run:
    export SRC_DSN="postgresql://jip_admin:...@jip-data-engine...rds.amazonaws.com:5432/data_engine?sslmode=require"
    export DST_DSN="postgresql://postgres.<project-ref>:...@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    python3 migrate_to_supabase.py [--schema-only] [--skip-schema] [--table TABLE]
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime


def _dsn(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        sys.exit(f"Missing env var: {key}")
    return val


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_pipe(src_cmd: str, dst_cmd: str) -> None:
    src = subprocess.Popen(src_cmd, shell=True, stdout=subprocess.PIPE)  # noqa: S602
    dst = subprocess.Popen(dst_cmd, shell=True, stdin=src.stdout)  # noqa: S602
    if src.stdout:
        src.stdout.close()
    dst.communicate()
    if src.wait() != 0 or dst.returncode != 0:
        raise subprocess.CalledProcessError(1, src_cmd)


def row_count(dsn: str, table: str) -> int:
    r = subprocess.run(  # noqa: S603
        ["psql", dsn, "-t", "-c", f"SELECT COUNT(*) FROM public.{table};"],  # noqa: S607
        capture_output=True,
        text=True,
    )
    try:
        return int(r.stdout.strip())
    except ValueError:
        return -1


# Tables in dependency order. Partitioned parents are excluded from data copy
# (data goes via year-partition tables which auto-route to the parent).
SMALL_TABLES = [
    "de_trading_calendar",
    "de_instrument",
    "de_index_master",
    "de_etf_master",
    "de_mf_master",
    "de_sector_mapping",
    "de_global_instrument_master",
    "de_contributors",
    "de_index_constituents",
    "de_index_prices",
    "de_global_prices",
    "de_etf_ohlcv",
    "de_corporate_actions",
    "de_market_cap_history",
    "de_mf_holdings",
    "de_etf_holdings",
    "de_mf_lifecycle",
    "de_mf_dividends",
    "de_source_files",
    "de_pipeline_log",
    "de_cron_run",
    "de_healing_log",
    "de_adjustment_factors_daily",
    "de_global_technical_daily",
    "de_goldilocks_market_view",
    "de_goldilocks_sector_view",
    "de_goldilocks_stock_ideas",
    "de_data_anomalies",
    "de_migration_errors",
    "de_migration_log",
    "de_recompute_queue",
    "de_request_log",
    "de_symbol_history",
    "de_system_flags",
]

# Year partitions — data is inserted into the PARENT table on Supabase
EQUITY_YEARS = list(range(2000, 2035))
NAV_YEARS = list(range(2006, 2035))

# Source table → destination parent table
PARTITION_REMAP: dict[str, str] = {
    **{f"de_equity_ohlcv_y{y}": "de_equity_ohlcv" for y in EQUITY_YEARS},
    "de_equity_ohlcv_default": "de_equity_ohlcv",
    **{f"de_mf_nav_daily_y{y}": "de_mf_nav_daily" for y in NAV_YEARS},
    "de_mf_nav_daily_default": "de_mf_nav_daily",
}

EQUITY_PARTITIONS = [f"de_equity_ohlcv_y{y}" for y in EQUITY_YEARS] + ["de_equity_ohlcv_default"]
NAV_PARTITIONS = [f"de_mf_nav_daily_y{y}" for y in NAV_YEARS] + ["de_mf_nav_daily_default"]

ALL_TABLES = SMALL_TABLES + EQUITY_PARTITIONS + NAV_PARTITIONS + ["mf_nav_history"]


def apply_schema(src: str, dst: str) -> None:
    log("Dumping schema from source RDS…")
    dump = (
        f"pg_dump '{src}' --schema-only --no-owner --no-acl "
        f"-t 'public.de_*' -t 'public.mf_nav_history'"
    )
    run_pipe(dump, f"psql '{dst}'")
    log("Schema applied.")


def migrate_table(src: str, dst: str, src_table: str) -> None:
    dst_table = PARTITION_REMAP.get(src_table, src_table)
    src_count = row_count(src, src_table)

    if src_count == 0:
        log(f"  {src_table}: 0 rows — skip")
        return

    log(f"  {src_table} → {dst_table} ({src_count:,} rows)")
    t0 = time.time()

    copy_out = (
        f"psql '{src}' -c \"\\COPY (SELECT * FROM public.{src_table}) TO stdout WITH (FORMAT CSV)\""
    )
    copy_in = f"psql '{dst}' -c \"\\COPY public.{dst_table} FROM stdin WITH (FORMAT CSV)\""
    run_pipe(copy_out, copy_in)

    elapsed = time.time() - t0
    rate = src_count / elapsed if elapsed > 0 else 0
    log(f"  done in {elapsed:.1f}s ({rate:,.0f} rows/s)")


def validate(src: str, dst: str) -> None:
    log("Validation:")
    check_tables = [
        "de_equity_ohlcv",
        "de_mf_nav_daily",
        "mf_nav_history",
        "de_instrument",
        "de_etf_ohlcv",
        "de_index_prices",
        "de_global_prices",
        "de_mf_holdings",
        "de_corporate_actions",
    ]
    all_ok = True
    for tbl in check_tables:
        s = row_count(src, tbl)
        d = row_count(dst, tbl)
        ok = s == d
        if not ok:
            all_ok = False
        flag = "✓" if ok else "✗"
        log(f"  {flag} {tbl}: src={s:,}  dst={d:,}")
    if all_ok:
        log("All counts match.")
    else:
        log("MISMATCHES found — check above.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--schema-only", action="store_true", help="Apply schema then stop")
    p.add_argument("--skip-schema", action="store_true", help="Skip schema, go straight to data")
    p.add_argument("--table", help="Migrate a single named table")
    p.add_argument("--validate", action="store_true", help="Run validation only")
    args = p.parse_args()

    src = _dsn("SRC_DSN")
    dst = _dsn("DST_DSN")

    if args.validate:
        validate(src, dst)
        return

    if not args.skip_schema:
        apply_schema(src, dst)

    if args.schema_only:
        return

    tables = [args.table] if args.table else ALL_TABLES
    seen: set[str] = set()
    tables = [t for t in tables if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

    log(f"Migrating {len(tables)} tables…")
    for i, tbl in enumerate(tables, 1):
        log(f"[{i}/{len(tables)}] {tbl}")
        try:
            migrate_table(src, dst, tbl)
        except subprocess.CalledProcessError as exc:
            log(f"  ERROR: {exc} — continuing")

    validate(src, dst)


if __name__ == "__main__":
    main()
