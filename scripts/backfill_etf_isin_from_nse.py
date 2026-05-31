#!/usr/bin/env python3
"""Backfill atlas_universe_etfs.isin (and atlas_etf_scorecard.isin) from NSE ETF master CSV.

NSE publishes the ETF symbol -> ISIN mapping at
https://archives.nseindia.com/content/equities/eq_etfseclist.csv

Columns:
    Symbol, Underlying, SecurityName, DateofListing, MarketLot, ISINNumber, FaceValue

Run on EC2 (Mac psycopg2 hangs):
    ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
      'cd ~/atlas-compute && python3 scripts/backfill_etf_isin_from_nse.py --write'
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

log = structlog.get_logger()

NSE_ETF_MASTER_URL = "https://archives.nseindia.com/content/equities/eq_etfseclist.csv"
NSE_HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_TIMEOUT = 60


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def fetch_nse_etf_master() -> dict[str, str]:
    """Return {symbol_upper: isin}."""
    log.info("nse_fetch", url=NSE_ETF_MASTER_URL)
    resp = requests.get(NSE_ETF_MASTER_URL, headers=NSE_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    rdr = csv.DictReader(io.StringIO(resp.text))
    out: dict[str, str] = {}
    for row in rdr:
        symbol = (row.get("Symbol") or "").strip().upper()
        isin = (row.get("ISINNumber") or "").strip().upper()
        if symbol and isin and len(isin) == 12:
            out[symbol] = isin
    log.info("nse_parsed", n=len(out))
    return out


def update_universe(engine, mapping: dict[str, str], dry_run: bool) -> tuple[int, list[str]]:
    """Set isin on atlas_universe_etfs and atlas_etf_scorecard for matched tickers.

    Returns (updated_universe_rows, list_of_unmatched_tickers).
    """
    with engine.connect() as conn:
        active = conn.execute(
            text("SELECT ticker FROM atlas.atlas_universe_etfs WHERE effective_to IS NULL")
        ).fetchall()
    active_tickers = [r[0] for r in active]

    matches = [
        {"ticker": t, "isin": mapping[t.upper()]} for t in active_tickers if t.upper() in mapping
    ]
    unmatched = [t for t in active_tickers if t.upper() not in mapping]

    if dry_run:
        log.info("dry_run", would_update=len(matches), unmatched=len(unmatched))
        return 0, unmatched

    updated = 0
    with engine.begin() as conn:
        for m in matches:
            res = conn.execute(
                text(
                    "UPDATE atlas.atlas_universe_etfs SET isin = :isin "
                    "WHERE ticker = :ticker AND effective_to IS NULL"
                ),
                m,
            )
            updated += res.rowcount
            conn.execute(
                text(
                    "UPDATE atlas.atlas_etf_scorecard SET isin = :isin "
                    "WHERE ticker = :ticker AND isin IS NULL"
                ),
                m,
            )
    return updated, unmatched


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill ETF ISINs from NSE master")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--env", default="/home/ubuntu/atlas-compute/.env")
    args = parser.parse_args()

    dry_run = not args.write
    print(f"NSE ETF ISIN backfill — dry_run={dry_run}")

    env = load_env(Path(args.env))
    engine = create_engine(env["ATLAS_DB_URL"], pool_pre_ping=True, pool_size=2)

    mapping = fetch_nse_etf_master()
    print(f"NSE master: {len(mapping)} ETF tickers")

    updated, unmatched = update_universe(engine, mapping, dry_run)
    print(f"Updated atlas_universe_etfs rows: {updated}")
    if unmatched:
        print(f"Unmatched tickers ({len(unmatched)}): {sorted(unmatched)}")
    if dry_run:
        print("\nRe-run with --write to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
