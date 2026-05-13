#!/usr/bin/env python3
"""Backfill Global Atlas OHLCV from Stooq bulk zip into global_atlas.stock_ohlcv.

Loads historical daily OHLCV for:
  - 30 country ETFs (US-listed, in Stooq US zip)
  - 4 RS benchmarks: ACWI, VT, EEM, GLD

All instruments are US-listed ETFs — only the US zip is needed.
No world zip, no VIX (Global Atlas derives volatility from VT realized vol).

Expected row count after full backfill: ~180K rows
Runtime: ~1-2 min

Usage:
    # Dry-run: parse zip, report row counts, do not write
    python3 scripts/stooq_backfill_global.py --dry-run

    # Full backfill
    python3 scripts/stooq_backfill_global.py

    # Specify alternate zip path
    python3 scripts/stooq_backfill_global.py --us-zip ~/Downloads/d_us_txt.zip
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from scripts.stooq_ingest import (  # noqa: E402
    build_file_map,
    load_stooq_zip,
    validate_ohlcv,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Global universe — 30 country ETFs + 4 RS benchmarks
# ---------------------------------------------------------------------------

# 4 RS benchmarks (must be loaded for all)
RS_BENCHMARKS = ["acwi", "vt", "eem", "gld"]

# Developed Markets — Americas
DM_AMERICAS = [
    "spy",  # United States (S&P 500 proxy — country ETF slot for USA)
    "ewc",  # Canada
]

# Developed Markets — Europe
DM_EUROPE = [
    "ewg",  # Germany
    "ewu",  # United Kingdom
    "ewq",  # France
    "ewi",  # Italy
    "ewp",  # Spain
    "ewd",  # Sweden
    "ewn",  # Netherlands
    "ewl",  # Switzerland (extra; not in universe but cheap to include)
    "epol",  # Poland (extra; not in universe but cheap to include)
]

# Developed Markets — Asia-Pacific
DM_ASIA_PAC = [
    "ewj",  # Japan
    "ewa",  # Australia
    "ews",  # Singapore
    "ewh",  # Hong Kong
]

# Emerging Markets — Americas
EM_AMERICAS = [
    "ewz",  # Brazil
    "eww",  # Mexico
    "ech",  # Chile
]

# Emerging Markets — Europe / Africa / Middle East
EM_EMEA = [
    "tur",  # Turkey
    "eza",  # South Africa
    "ksa",  # Saudi Arabia
    "uae",  # UAE
]

# Emerging Markets — Asia
EM_ASIA = [
    "inda",  # India
    "mchi",  # China (iShares MSCI China)
    "ewy",  # South Korea
    "ewt",  # Taiwan
    "ephe",  # Philippines
    "eido",  # Indonesia
    "thd",  # Thailand
    "vnm",  # Vietnam
]

ALL_COUNTRY_ETFS = DM_AMERICAS + DM_EUROPE + DM_ASIA_PAC + EM_AMERICAS + EM_EMEA + EM_ASIA

ALL_TICKERS = RS_BENCHMARKS + ALL_COUNTRY_ETFS


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def bulk_insert(engine, df: pd.DataFrame, table: str, *, chunk_size: int = 5000) -> int:
    """Insert rows via chunked upsert. Returns rows written."""
    if df.empty:
        return 0

    total = 0
    cols = list(df.columns)
    col_list = ", ".join(cols)
    placeholders = ", ".join([f":{c}" for c in cols])
    upsert_sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "  # noqa: S608
        f"ON CONFLICT (ticker, date) DO UPDATE SET "
        + ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c not in ("ticker", "date")])
    )

    with engine.begin() as conn:
        for i in range(0, len(df), chunk_size):
            chunk = df.iloc[i : i + chunk_size]
            rows = chunk.to_dict(orient="records")
            conn.execute(text(upsert_sql), rows)
            total += len(rows)

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Global Atlas OHLCV from Stooq zip")
    parser.add_argument("--us-zip", default="~/Downloads/d_us_txt.zip")
    parser.add_argument("--dry-run", action="store_true", help="Parse zip only; do not write to DB")
    parser.add_argument("--start-date", default="2008-01-01", help="Historical start (YYYY-MM-DD)")
    args = parser.parse_args()

    us_zip = Path(args.us_zip).expanduser()

    if not us_zip.exists():
        log.error("us_zip_not_found", path=str(us_zip))
        sys.exit(1)

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------
    engine = None
    if not args.dry_run:
        env = load_env(ROOT / ".env")
        db_url = env.get("ATLAS_DB_URL", "")
        if not db_url:
            log.error("ATLAS_DB_URL_not_set")
            sys.exit(1)
        engine = create_engine(db_url, pool_pre_ping=True)

    # ------------------------------------------------------------------
    # Step 1: Build file map (scan zip once)
    # ------------------------------------------------------------------
    log.info("building_us_file_map")
    us_file_map = build_file_map(us_zip)

    # ------------------------------------------------------------------
    # Step 2: Load all country ETFs + RS benchmarks from US zip
    # ------------------------------------------------------------------
    log.info("loading_global_tickers", count=len(ALL_TICKERS))
    df = load_stooq_zip(us_zip, us_file_map, ALL_TICKERS, start_date=args.start_date)
    validate_ohlcv(df, label="global_atlas")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    tickers_loaded = df["ticker"].unique().tolist()
    tickers_missing = [t for t in ALL_TICKERS if t not in tickers_loaded]

    log.info(
        "backfill_summary",
        tickers_requested=len(ALL_TICKERS),
        tickers_loaded=len(tickers_loaded),
        tickers_missing=tickers_missing,
        total_rows=len(df),
        date_min=str(df["date"].min()),
        date_max=str(df["date"].max()),
    )

    if args.dry_run:
        log.info("dry_run_complete", total_rows=len(df), action="no_writes")
        return

    # ------------------------------------------------------------------
    # Write to DB
    # ------------------------------------------------------------------
    t0 = time.time()

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.drop_duplicates(subset=["ticker", "date"], keep="last")

    assert engine is not None  # guaranteed by args.dry_run check above
    log.info("writing_to_db", rows=len(df), table="global_atlas.stock_ohlcv")
    n = bulk_insert(engine, df, "global_atlas.stock_ohlcv")
    elapsed = time.time() - t0

    log.info("backfill_complete", rows_written=n, elapsed_seconds=round(elapsed, 1))


if __name__ == "__main__":
    main()
