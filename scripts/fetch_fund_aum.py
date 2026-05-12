"""
Fetch monthly AUM for all funds in atlas_universe_funds from AMFI India.

AMFI publishes scheme-wise monthly average AUM as a downloadable text file.
We match via de_mf_master.amfi_code → atlas_universe_funds.mstar_id.

Usage:
    python scripts/fetch_fund_aum.py          # fetch latest published month
    python scripts/fetch_fund_aum.py --dry-run # print matches without writing
"""

import argparse
import logging
import os
import re
import sys
from decimal import Decimal

import pandas as pd
import requests
import structlog
from sqlalchemy import create_engine, text

log = structlog.get_logger()

AMFI_AUM_URL = (
    "https://www.amfiindia.com/modules/InavPerfReport" "?nav=SchemeWiseMonthlyAUM&rtntype=D"
)
AMFI_AUM_FALLBACK_URL = "https://www.amfiindia.com/research-information/aum-data"

# AMFI publishes a semicolon-delimited text file for scheme-wise AUM.
# Format varies by year; we try multiple layouts.
AMFI_TEXT_URL = "https://portal.amfiindia.com/DownloadData_Po.aspx?mf=0&dtype=3&OldNewFlag=O"


def fetch_amfi_aum_df() -> pd.DataFrame:
    """Download AMFI scheme-wise AUM data and return a DataFrame with
    columns: amfi_code (str), aum_cr (Decimal), period_end (date str YYYY-MM-DD).
    """
    log.info("fetching_amfi_aum", url=AMFI_TEXT_URL)
    resp = requests.get(AMFI_TEXT_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.text

    # Parse the semicolon-delimited AMFI format
    rows = []
    period_end = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Header line contains the period date, e.g. "Month Ended:March 2025"
        if line.startswith("Month Ended"):
            m = re.search(r"(\w+ \d{4})", line)
            if m:
                period_end = pd.to_datetime(m.group(1), format="%B %Y")
                period_end = period_end + pd.offsets.MonthEnd(0)
                period_end = period_end.date()
            continue
        parts = line.split(";")
        if len(parts) < 4:
            continue
        # Typical columns: Scheme Code ; Scheme Name ; ... ; AUM (Cr)
        code_str = parts[0].strip()
        if not code_str.isdigit():
            continue
        # Last numeric field is AUM in crore
        aum_str = parts[-1].strip().replace(",", "")
        try:
            aum_val = Decimal(aum_str)
        except Exception:
            log.debug("aum_parse_skip", code=code_str, raw=aum_str)
            continue
        rows.append({"amfi_code": code_str, "aum_cr": aum_val})

    if not rows:
        raise ValueError("AMFI AUM parse produced 0 rows — check format")

    df = pd.DataFrame(rows)
    df["period_end"] = str(period_end) if period_end else None
    log.info("amfi_aum_parsed", rows=len(df), period_end=period_end)
    return df


def run(dry_run: bool = False) -> None:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL environment variable not set")

    engine = create_engine(db_url, future=True)

    # Load the amfi_code → mstar_id mapping from de_mf_master
    with engine.connect() as conn:
        mapping = pd.read_sql(
            text(
                "SELECT mstar_id, amfi_code FROM public.de_mf_master " "WHERE amfi_code IS NOT NULL"
            ),
            conn,
        )
    log.info("mapping_loaded", rows=len(mapping))

    aum_df = fetch_amfi_aum_df()
    period_end = aum_df["period_end"].iloc[0] if len(aum_df) else None

    merged = aum_df.merge(mapping, on="amfi_code", how="inner")
    log.info(
        "matched_funds",
        amfi_rows=len(aum_df),
        matched=len(merged),
        period_end=period_end,
    )

    if dry_run:
        print(merged[["mstar_id", "amfi_code", "aum_cr", "period_end"]].to_string())
        return

    if len(merged) == 0:
        log.error("no_matches_aborting")
        sys.exit(1)

    # Upsert aum_cr + aum_as_of into atlas_universe_funds
    updated = 0
    with engine.begin() as conn:
        for _, row in merged.iterrows():
            result = conn.execute(
                text(
                    "UPDATE atlas.atlas_universe_funds "
                    "SET aum_cr = :aum, aum_as_of = :as_of, updated_at = NOW() "
                    "WHERE mstar_id = :mstar_id"
                ),
                {
                    "aum": float(row["aum_cr"]),
                    "as_of": period_end,
                    "mstar_id": row["mstar_id"],
                },
            )
            updated += result.rowcount

    log.info("aum_updated", rows_updated=updated, period_end=period_end)
    print(f"✓ AUM updated for {updated} funds (period: {period_end})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Fetch and store AMFI monthly AUM")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
