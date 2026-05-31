"""
Fetch monthly AUM for all funds in atlas_universe_funds from AMFI India.

AMFI publishes scheme-wise monthly average AUM via a Strapi-backed JSON API.
We match via de_mf_master.amfi_code → atlas_universe_funds.mstar_id.

Usage:
    python scripts/fetch_fund_aum.py          # fetch latest published period
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

AMFI_BASE = "https://www.amfiindia.com/api/average-aum-schemewise"

MONTH_END = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; atlas-os/1.0)",
    "Referer": "https://www.amfiindia.com/aum-data/average-aum",
}


def _get(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _latest_fy_period() -> tuple[int, int, str]:
    """Return (fy_id, period_id, period_label) for the most recently published period."""
    fy_data = _get(AMFI_BASE, params={"strType": "Categorywise"})
    # data is a list of {"id": N, "financial_year": "April YYYY - March YYYY"}
    years = fy_data.get("data", [])
    if not years:
        raise ValueError("No financial years returned from AMFI API")
    latest_fy = years[0]  # most recent FY is first
    fy_id = latest_fy["id"]
    log.info("amfi_fy_selected", fy_id=fy_id, fy=latest_fy.get("financial_year"))

    period_data = _get(AMFI_BASE, params={"strType": "Categorywise", "fyId": fy_id})
    periods = period_data.get("data", {}).get("periods", [])
    if not periods:
        raise ValueError(f"No periods returned for fyId={fy_id}")
    latest_period = periods[0]  # most recent period is first
    period_id = latest_period["id"]
    period_label = latest_period["period"]
    log.info("amfi_period_selected", period_id=period_id, period=period_label)
    return fy_id, period_id, period_label


def _period_end_date(period_label: str) -> str:
    """Convert 'January - March 2026' → '2026-03-31'."""
    # Period label format: "<Month> - <Month> <Year>"
    m = re.match(r"(\w+)\s*-\s*(\w+)\s+(\d{4})", period_label.strip())
    if not m:
        raise ValueError(f"Cannot parse period label: {period_label!r}")
    end_month_name, year = m.group(2), int(m.group(3))
    month_num = MONTH_END.get(end_month_name)
    if not month_num:
        raise ValueError(f"Unknown month: {end_month_name!r}")
    period_end = (pd.Timestamp(year=year, month=month_num, day=1) + pd.offsets.MonthEnd(0)).date()
    return str(period_end)


def fetch_amfi_aum_df() -> pd.DataFrame:
    """Download AMFI scheme-wise AUM data and return a DataFrame with
    columns: amfi_code (str), aum_cr (Decimal), period_end (date str YYYY-MM-DD).
    """
    fy_id, period_id, period_label = _latest_fy_period()
    period_end = _period_end_date(period_label)

    log.info("fetching_amfi_aum_data", fy_id=fy_id, period_id=period_id, period_end=period_end)
    payload = _get(
        AMFI_BASE,
        params={"strType": "Categorywise", "fyId": fy_id, "periodId": period_id, "MF_ID": 0},
    )

    # Nested structure: data[] → schemes[] → AMFI_Code + AverageAumForTheMonth
    rows = []
    for fund_house in payload.get("data", []):
        for scheme in fund_house.get("schemes", []):
            amfi_code = scheme.get("AMFI_Code")
            if amfi_code is None:
                continue
            aum_obj = scheme.get("AverageAumForTheMonth", {})
            # Use ex-domestic-FoF AUM (industry standard for scheme-level AUM)
            aum_raw = aum_obj.get("ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas", 0)
            if not aum_raw:
                continue
            try:
                aum_val = Decimal(str(aum_raw))
            except Exception:
                log.debug("aum_parse_skip", amfi_code=amfi_code, raw=aum_raw)
                continue
            rows.append({"amfi_code": str(amfi_code), "aum_cr": aum_val})

    if not rows:
        raise ValueError("AMFI AUM parse produced 0 rows — check API response structure")

    df = pd.DataFrame(rows)
    df["period_end"] = period_end
    log.info("amfi_aum_parsed", rows=len(df), period_end=period_end)
    return df


def run(dry_run: bool = False) -> None:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL environment variable not set")

    engine = create_engine(db_url, future=True)

    with engine.connect() as conn:
        mapping = pd.read_sql(
            text("SELECT mstar_id, amfi_code FROM public.de_mf_master WHERE amfi_code IS NOT NULL"),
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
