#!/usr/bin/env python3
"""AMFI iNAV ingest for ETFs — fills atlas_etf_scorecard.premium_bps.

Pulls daily NAV from AMFI's consolidated NAV history file (the same source
already used by scripts/amfi_nav_backfill_direct.py), joins to market close
from public.de_etf_ohlcv, and writes premium_bps = ((close - nav) / nav) * 10000
back to atlas.atlas_etf_scorecard for the matching snapshot_date.

ISIN is the join key; atlas_universe_etfs.isin <-> AMFI NAV record ISIN1/ISIN2.

Run on EC2 (Mac psycopg2 hangs against Supabase):
    ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
      'cd ~/atlas-compute && python3 scripts/amfi_etf_inav_ingest.py --write'

Daily cron: schedule at 22:00 IST (after AMFI publishes day's NAV).

Usage:
    python3 scripts/amfi_etf_inav_ingest.py --write                  # latest day
    python3 scripts/amfi_etf_inav_ingest.py --write --backfill 30    # last 30 days
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import structlog  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

log = structlog.get_logger()

# AMFI publishes today's NAV for every open-ended scheme at this endpoint.
# Format: semicolon-delimited with header:
#   Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
# Hist endpoint DownloadNAVHistoryReport_Po.aspx now returns HTML (postback required),
# so this script runs daily against NAVAll.txt (today only).
AMFI_NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
REQUEST_TIMEOUT = 120


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def get_active_etf_isins(engine) -> dict[str, str]:
    """Return {isin: ticker} for active ETFs."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT isin, ticker FROM atlas.atlas_universe_etfs "
                "WHERE effective_to IS NULL AND isin IS NOT NULL"
            )
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def fetch_amfi_nav_all() -> bytes:
    log.info("amfi_fetch", url=AMFI_NAV_ALL_URL)
    resp = requests.get(AMFI_NAV_ALL_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    log.info("amfi_response", size_kb=len(resp.content) // 1024)
    return resp.content


def parse_amfi_for_etfs(content: bytes, target_isins: set[str]) -> list[tuple[str, date, float]]:
    """Parse AMFI NAVAll.txt. Return [(isin, nav_date, nav), ...] for target ISINs.

    NAVAll.txt line format (semicolon-delimited):
        SchemeCode;ISIN_Growth;ISIN_Reinvest;SchemeName;NAV;Date
    Header line starts with "Scheme Code"; AMC section headers and blanks are skipped
    (split yields < 6 parts).
    """
    rows: list[tuple[str, date, float]] = []
    text_content = content.decode("utf-8", errors="replace")

    for line in io.StringIO(text_content):
        line = line.strip()
        if not line or line.startswith("Scheme Code"):
            continue
        parts = line.split(";")
        if len(parts) < 6:
            continue
        isin_g = parts[1].strip().upper()
        isin_r = parts[2].strip().upper()
        match_isin = None
        if isin_g and isin_g in target_isins:
            match_isin = isin_g
        elif isin_r and isin_r in target_isins:
            match_isin = isin_r
        if not match_isin:
            continue
        nav_str = parts[4].strip()
        date_str = parts[5].strip()
        try:
            nav_val = float(nav_str)
            nav_date = datetime.strptime(date_str, "%d-%b-%Y").date()
        except (ValueError, IndexError):
            continue
        rows.append((match_isin, nav_date, nav_val))

    return rows


def compute_premium_bps(
    engine,
    nav_rows: list[tuple[str, date, float]],
    isin_to_ticker: dict[str, str],
) -> list[dict]:
    """Join NAV rows with same-date market close and compute premium_bps.

    premium_bps = ((close - nav) / nav) * 10000
    """
    if not nav_rows:
        return []

    ticker_to_navs: dict[str, list[tuple[date, float]]] = {}
    for isin, nav_date, nav in nav_rows:
        ticker = isin_to_ticker.get(isin)
        if not ticker:
            continue
        ticker_to_navs.setdefault(ticker, []).append((nav_date, nav))

    out: list[dict] = []
    with engine.connect() as conn:
        for ticker, nav_history in ticker_to_navs.items():
            dates = [d for d, _ in nav_history]
            close_rows = conn.execute(
                text(
                    "SELECT date, close FROM public.de_etf_ohlcv "
                    "WHERE ticker = :ticker AND date = ANY(:dates)"
                ),
                {"ticker": ticker, "dates": dates},
            ).fetchall()
            close_map = {r[0]: float(r[1]) for r in close_rows if r[1] is not None}
            for nav_date, nav in nav_history:
                close = close_map.get(nav_date)
                if close is None or nav <= 0:
                    continue
                premium_bps = ((close - nav) / nav) * 10000.0
                out.append(
                    {
                        "ticker": ticker,
                        "snapshot_date": nav_date.isoformat(),
                        "premium_bps": round(premium_bps, 2),
                    }
                )
    return out


def upsert_premium_bps(engine, rows: list[dict], dry_run: bool) -> int:
    """Update premium_bps on the LATEST scorecard row per ticker.

    AMFI's nav_date (today) frequently differs from scorecard's snapshot_date
    (last nightly compute run). Premium is freshness-sensitive — we overwrite
    the most recent scorecard row so the MV picks it up on next refresh.
    Keep only the most-recent NAV record per ticker.
    """
    if not rows:
        return 0
    latest_per_ticker: dict[str, dict] = {}
    for r in rows:
        cur = latest_per_ticker.get(r["ticker"])
        if cur is None or r["snapshot_date"] > cur["snapshot_date"]:
            latest_per_ticker[r["ticker"]] = r
    payload = list(latest_per_ticker.values())
    if dry_run:
        log.info("dry_run_skip_upsert", n=len(payload))
        return 0
    updated = 0
    with engine.begin() as conn:
        for r in payload:
            res = conn.execute(
                text(
                    "UPDATE atlas.atlas_etf_scorecard "
                    "SET premium_bps = :premium_bps "
                    "WHERE ticker = :ticker "
                    "  AND snapshot_date = ("
                    "    SELECT MAX(snapshot_date) FROM atlas.atlas_etf_scorecard "
                    "    WHERE ticker = :ticker"
                    "  )"
                ),
                {"ticker": r["ticker"], "premium_bps": r["premium_bps"]},
            )
            updated += res.rowcount
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="AMFI iNAV ingest for ETFs")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--env", default="/home/ubuntu/atlas-compute/.env")
    args = parser.parse_args()

    dry_run = not args.write
    print(f"AMFI iNAV ingest — dry_run={dry_run}")

    env = load_env(Path(args.env))
    engine = create_engine(env["ATLAS_DB_URL"], pool_pre_ping=True, pool_size=2)

    isin_to_ticker = get_active_etf_isins(engine)
    print(f"Active ETFs with ISIN: {len(isin_to_ticker)}")
    target_isins = set(isin_to_ticker.keys())

    try:
        content = fetch_amfi_nav_all()
    except requests.RequestException as e:
        print(f"ERROR fetching AMFI: {e}")
        return 1

    nav_rows = parse_amfi_for_etfs(content, target_isins)
    print(f"AMFI rows matched to active ETFs: {len(nav_rows)}")

    if not nav_rows:
        print("No NAV rows found — AMFI may not have published or ISIN mismatch.")
        return 0

    premium_rows = compute_premium_bps(engine, nav_rows, isin_to_ticker)
    print(f"Computed premium_bps for {len(premium_rows)} (ticker, date) pairs")

    updated = upsert_premium_bps(engine, premium_rows, dry_run)
    print(f"Updated atlas_etf_scorecard rows: {updated} (0 in dry-run)")

    if dry_run and premium_rows:
        print("\nRe-run with --write to update.")
    elif updated:
        print("\nNext: refresh MV — REFRESH MATERIALIZED VIEW atlas.mv_etf_list_v6;")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
