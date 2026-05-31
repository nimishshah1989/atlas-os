#!/usr/bin/env python3
"""Backfill US Atlas OHLCV from Stooq bulk zip into us_atlas.stock_ohlcv.

Loads historical daily OHLCV for:
  - S&P 500 stocks (from Wikipedia manifest + Stooq US zip)
  - 80 curated ETFs (sector, commodity, broad market, thematic)
  - 4 RS benchmarks: ACWI, VT, EEM, GLD
  - Regime inputs: ^SPX (from world zip), ^VIX (via Stooq API)

Expected row count after full backfill: ~4.5M rows
Runtime: ~8-12 min (dominated by bulk_insert to RDS)

Usage:
    # Dry-run: parse zip, report row counts, do not write
    python3 scripts/stooq_backfill_us.py --dry-run

    # Full backfill
    python3 scripts/stooq_backfill_us.py

    # ETFs + benchmarks only (skip stocks)
    python3 scripts/stooq_backfill_us.py --etfs-only

    # Specify alternate zip paths
    python3 scripts/stooq_backfill_us.py \\
        --us-zip ~/Downloads/d_us_txt.zip \\
        --world-zip ~/Downloads/d_world_txt.zip
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
    fetch_vix_history,
    load_stooq_zip,
    validate_ohlcv,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# US ETF universe — 80 curated instruments + 4 benchmarks + regime inputs
# ---------------------------------------------------------------------------

# 4 RS benchmarks (must be loaded for all)
RS_BENCHMARKS = ["acwi", "vt", "eem", "gld"]

# Regime inputs
REGIME_INPUTS = ["spy"]  # ^SPX loaded from world zip; ^VIX from API

# Sector ETFs — 11 GICS sectors
SECTOR_ETFS = ["xlk", "xlf", "xle", "xlv", "xli", "xly", "xlp", "xlb", "xlre", "xlu", "xlc"]

# Broad market ETFs
BROAD_MARKET_ETFS = ["qqq", "iwm", "dia", "voo", "ivv", "vxf"]

# Factor ETFs
FACTOR_ETFS = ["mtum", "qual", "vlue", "usmv"]

# Commodity ETFs — precious metals
PRECIOUS_METALS_ETFS = ["slv", "sil", "gdx", "gdxj", "iau", "sgol", "pplt", "pall"]

# Commodity ETFs — energy
ENERGY_ETFS = ["uso", "dbo", "ung", "amlp"]

# Commodity ETFs — agriculture + base metals + broad
COMMODITY_ETFS = ["dba", "dbb", "copx", "xme", "pdbc", "dbc", "gsg", "remx", "lit"]

# Thematic ETFs
THEMATIC_ETFS = ["arkk", "botz", "soxx", "smh", "hack"]

ALL_ETFS = (
    RS_BENCHMARKS
    + REGIME_INPUTS
    + SECTOR_ETFS
    + BROAD_MARKET_ETFS
    + FACTOR_ETFS
    + PRECIOUS_METALS_ETFS
    + ENERGY_ETFS
    + COMMODITY_ETFS
    + THEMATIC_ETFS
)


def get_sp500_tickers(engine=None) -> list[str]:
    """Fetch S&P 500 constituents — DB universe first, Wikipedia fallback."""
    if engine is not None:
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT ticker FROM us_atlas.atlas_universe_stocks "
                        "WHERE in_sp500 = TRUE AND is_active = TRUE ORDER BY ticker"
                    )
                ).fetchall()
            if rows:
                tickers = [r[0] for r in rows]
                log.info("sp500_tickers_from_db", count=len(tickers))
                return tickers
        except Exception as e:
            log.warning("sp500_db_fetch_failed", error=str(e), action="falling_back_to_wikipedia")

    log.info("fetching_sp500_constituents_from_wikipedia")
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )
        tickers = tables[0]["Symbol"].str.lower().str.replace(".", "-", regex=False).tolist()
        log.info("sp500_tickers_fetched", count=len(tickers))
        return tickers
    except Exception as e:
        log.error("sp500_fetch_failed", error=str(e))
        raise


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
    """Insert rows via COPY (fast path). Returns rows written."""
    if df.empty:
        return 0

    total = 0
    cols = list(df.columns)
    col_list = ", ".join(cols)
    placeholders = ", ".join([f":{c}" for c in cols])
    upsert_sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
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
    parser = argparse.ArgumentParser(description="Backfill US Atlas OHLCV from Stooq zip")
    parser.add_argument("--us-zip", default="~/Downloads/d_us_txt.zip")
    parser.add_argument("--world-zip", default="~/Downloads/d_world_txt.zip")
    parser.add_argument("--dry-run", action="store_true", help="Parse zip only; do not write to DB")
    parser.add_argument("--etfs-only", action="store_true", help="Skip S&P 500 stocks")
    parser.add_argument("--start-date", default="2008-01-01", help="Historical start (YYYY-MM-DD)")
    args = parser.parse_args()

    us_zip = Path(args.us_zip).expanduser()
    world_zip = Path(args.world_zip).expanduser()

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
    # Step 1: ETFs + benchmarks from US zip
    # ------------------------------------------------------------------
    log.info("building_us_file_map")
    us_file_map = build_file_map(us_zip)

    log.info("loading_etfs_and_benchmarks", count=len(ALL_ETFS))
    etf_df = load_stooq_zip(us_zip, us_file_map, ALL_ETFS, start_date=args.start_date)
    validate_ohlcv(etf_df, label="us_etfs")

    # ------------------------------------------------------------------
    # Step 2: ^SPX from world zip (regime benchmark index)
    # ------------------------------------------------------------------
    log.info("loading_spx_from_world_zip")
    world_file_map = build_file_map(world_zip)
    spx_df = load_stooq_zip(world_zip, world_file_map, ["^spx"], start_date=args.start_date)
    validate_ohlcv(spx_df, label="^spx")

    # ------------------------------------------------------------------
    # Step 3: ^VIX from Stooq API (not in bulk zip)
    # ------------------------------------------------------------------
    log.info("fetching_vix_from_api")
    try:
        vix_df = fetch_vix_history(start_date=args.start_date)
        validate_ohlcv(vix_df, label="^vix")
    except Exception as e:
        log.warning("vix_fetch_failed", error=str(e), action="skipping_vix")
        vix_df = pd.DataFrame()

    # ------------------------------------------------------------------
    # Step 4: S&P 500 stocks (optional)
    # ------------------------------------------------------------------
    stock_df = pd.DataFrame()
    if not args.etfs_only:
        sp500_tickers = get_sp500_tickers(engine)
        log.info("loading_sp500_stocks", count=len(sp500_tickers))
        stock_df = load_stooq_zip(us_zip, us_file_map, sp500_tickers, start_date=args.start_date)
        validate_ohlcv(stock_df, label="sp500_stocks")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_rows = len(etf_df) + len(spx_df) + len(vix_df) + len(stock_df)
    log.info(
        "backfill_summary",
        etf_rows=len(etf_df),
        spx_rows=len(spx_df),
        vix_rows=len(vix_df),
        stock_rows=len(stock_df),
        total_rows=total_rows,
    )

    if args.dry_run:
        log.info("dry_run_complete", total_rows=total_rows, action="no_writes")
        return

    # ------------------------------------------------------------------
    # Write to DB
    # ------------------------------------------------------------------
    t0 = time.time()

    all_df = pd.concat(
        [df for df in [etf_df, spx_df, vix_df, stock_df] if not df.empty],
        ignore_index=True,
    )
    # Ensure date is Python date (not datetime) for psycopg2
    all_df["date"] = pd.to_datetime(all_df["date"]).dt.date

    # Deduplicate: keep last occurrence of any (ticker, date)
    all_df = all_df.drop_duplicates(subset=["ticker", "date"], keep="last")

    assert engine is not None  # guaranteed by args.dry_run check above
    log.info("writing_to_db", rows=len(all_df), table="us_atlas.stock_ohlcv")
    n = bulk_insert(engine, all_df, "us_atlas.stock_ohlcv")
    elapsed = time.time() - t0

    log.info("backfill_complete", rows_written=n, elapsed_seconds=round(elapsed, 1))


if __name__ == "__main__":
    main()
