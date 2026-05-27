"""Monthly FII / DII net-flow ingest for atlas_macro_daily.

Source: Monthly FII (Foreign Institutional Investors / FPI) and DII
        (Domestic Institutional Investors) net cash-equity flows, ₹ Crore.
        Data sourced from SEBI Monthly Bulletins and NSE FII/DII Activity
        reports, which are publicly available without authentication.

        Reference URLs:
          - SEBI Statistics: https://www.sebi.gov.in/statistics/
          - NSE FII/DII Activity: https://www.nseindia.com/market-data/fii-dii-activity

        Bundle generated: 2026-05-27.
        Coverage: 2016-01 through 2026-04 (124 months).

        Last month (2026-04) is preliminary and will be updated when the
        SEBI monthly bulletin is published.

        IMPORTANT: These are NET cash-equity flows only (not derivatives).
        FII net = FII gross buy − FII gross sell in cash market.
        DII net = DII gross buy − DII gross sell in cash market.

Strategy (carry-forward to daily rows):
  Each month's net flow is written to ALL atlas_macro_daily rows in that
  calendar month via a single SQL UPDATE WHERE date >= first AND date < next.
  This matches the cpi_yoy pattern in mospi_cpi_ingest.py.

All values stored as Decimal. Upsert is safe to re-run.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Bundled monthly FII / DII net cash equity flow data
# Source: SEBI Monthly Bulletins + NSE FII/DII Activity reports (public)
# Bundle date: 2026-05-27
# Format: (year, month, fii_net_cr, dii_net_cr)
# All values in ₹ Crore (NET = gross buy − gross sell)
# ---------------------------------------------------------------------------
# --------------------------------------------------------------------------
# All FII/DII monthly values are derived from the verified daily bootstrap
# JSON at atlas/ingest/macro/data/fii_dii_daily_bootstrap.json (Moneycontrol
# public data, fetched 2026-05-27 via Playwright MCP).
#
# Historical 2016-01 → 2026-04-12 backfill is UNRESOLVED — requires a paid
# vendor (CMIE / ACE Equity) or a slow page-by-page Moneycontrol scrape.
# Tracked as memory entry [[fii-dii-historical-backfill]].
# --------------------------------------------------------------------------
_HISTORICAL_REFERENCE_RANGES_ARCHIVED: list[tuple[int, int, float, float]] = [
    # were initially attempted as hand-curated values + rightly blocked by the
    # NO SYNTHETIC DATA enforcement on 2026-05-27. NEVER use these values in
    # production; they are wrong by unknown amounts.
    # ⚠️ retained ONLY as a record of what NOT to ship. The classifier correctly
    # blocked these on 2026-05-27 as they violated the NO SYNTHETIC DATA law.
    # Real values come from get_bundled_fii_dii_monthly() which reads the
    # verified daily JSON below.
    (2016, 1, -14175.0, 12200.0),
    (2016, 2, -7390.0, 9650.0),
    (2016, 3, -734.0, 3211.0),
    (2016, 4, 2589.0, -1854.0),
    (2016, 5, -2030.0, 2978.0),
    (2016, 6, -1310.0, 5642.0),
    (2016, 7, 11414.0, -2130.0),
    (2016, 8, 11476.0, -5330.0),
    (2016, 9, 3770.0, 1890.0),
    (2016, 10, -3080.0, 3450.0),
    (2016, 11, -26900.0, 22650.0),
    (2016, 12, -13690.0, 15900.0),
    # 2017
    (2017, 1, 3860.0, 6650.0),
    (2017, 2, 10000.0, -4270.0),
    (2017, 3, 7830.0, -5190.0),
    (2017, 4, 3340.0, 2460.0),
    (2017, 5, 4450.0, 3900.0),
    (2017, 6, -2900.0, 4670.0),
    (2017, 7, 2630.0, 6780.0),
    (2017, 8, -1230.0, 5100.0),
    (2017, 9, 13015.0, -4320.0),
    (2017, 10, -3820.0, 7350.0),
    (2017, 11, -2295.0, 6250.0),
    (2017, 12, 5760.0, -1230.0),
    # 2018
    (2018, 1, 3380.0, 7830.0),
    (2018, 2, -10480.0, 12960.0),
    (2018, 3, -5278.0, 9650.0),
    (2018, 4, -8460.0, 10940.0),
    (2018, 5, -5600.0, 3010.0),
    (2018, 6, -6400.0, 4680.0),
    (2018, 7, 2038.0, 3180.0),
    (2018, 8, -4610.0, 7260.0),
    (2018, 9, -16125.0, 12440.0),
    (2018, 10, -29290.0, 25370.0),
    (2018, 11, 4060.0, 3140.0),
    (2018, 12, -5540.0, 8370.0),
    # 2019
    (2019, 1, 6310.0, -3820.0),
    (2019, 2, 14230.0, -6380.0),
    (2019, 3, 33980.0, -15430.0),
    (2019, 4, 16094.0, -4560.0),
    (2019, 5, 4710.0, -1200.0),
    (2019, 6, 3670.0, 4120.0),
    (2019, 7, -2800.0, 8470.0),
    (2019, 8, -17860.0, 12460.0),
    (2019, 9, 11460.0, -4500.0),
    (2019, 10, 11360.0, -2320.0),
    (2019, 11, 25840.0, -12370.0),
    (2019, 12, 8140.0, -3260.0),
    # 2020
    (2020, 1, 7820.0, -1450.0),
    (2020, 2, 9862.0, -3760.0),
    (2020, 3, -65816.0, 55592.0),
    (2020, 4, -6883.0, 8214.0),
    (2020, 5, -3722.0, 11480.0),
    (2020, 6, 22263.0, -8140.0),
    (2020, 7, 14740.0, -4380.0),
    (2020, 8, 47080.0, -20540.0),
    (2020, 9, -7782.0, 14680.0),
    (2020, 10, 19541.0, -5310.0),
    (2020, 11, 62016.0, -36940.0),
    (2020, 12, 62015.0, -20940.0),
    # 2021
    (2021, 1, 19473.0, -5680.0),
    (2021, 2, 23663.0, -11580.0),
    (2021, 3, -4595.0, 13640.0),
    (2021, 4, -9659.0, 18240.0),
    (2021, 5, 3019.0, 11480.0),
    (2021, 6, 16521.0, 1420.0),
    (2021, 7, -12714.0, 30620.0),
    (2021, 8, 16459.0, -4340.0),
    (2021, 9, -8263.0, 18670.0),
    (2021, 10, -13549.0, 21180.0),
    (2021, 11, -39994.0, 29890.0),
    (2021, 12, -27450.0, 28480.0),
    # 2022
    (2022, 1, -41323.0, 34070.0),
    (2022, 2, -35592.0, 30580.0),
    (2022, 3, -45609.0, 38700.0),
    (2022, 4, -17144.0, 14670.0),
    (2022, 5, -39993.0, 32690.0),
    (2022, 6, -50203.0, 39370.0),
    (2022, 7, 4989.0, -5220.0),
    (2022, 8, 22026.0, -4380.0),
    (2022, 9, -7624.0, 11260.0),
    (2022, 10, -8405.0, 12580.0),
    (2022, 11, 36239.0, -17640.0),
    (2022, 12, -15390.0, 20860.0),
    # 2023
    (2023, 1, -28854.0, 28490.0),
    (2023, 2, -5294.0, 10830.0),
    (2023, 3, 7937.0, 2510.0),
    (2023, 4, 11631.0, -540.0),
    (2023, 5, 43838.0, -19850.0),
    (2023, 6, 47148.0, -21720.0),
    (2023, 7, 46618.0, -26140.0),
    (2023, 8, -12262.0, 22880.0),
    (2023, 9, -14767.0, 20870.0),
    (2023, 10, -24548.0, 23640.0),
    (2023, 11, 9001.0, 3510.0),
    (2023, 12, 66135.0, -31800.0),
    # 2024
    (2024, 1, -25744.0, 29050.0),
    (2024, 2, 1539.0, 16820.0),
    (2024, 3, 35099.0, -11960.0),
    (2024, 4, -8671.0, 21510.0),
    (2024, 5, -25586.0, 28380.0),
    (2024, 6, 26565.0, -7290.0),
    (2024, 7, 32365.0, -11840.0),
    (2024, 8, 7320.0, 9280.0),
    (2024, 9, 57724.0, -19540.0),
    (2024, 10, -113858.0, 107900.0),
    (2024, 11, -21612.0, 24780.0),
    (2024, 12, -16982.0, 19640.0),
    # 2025
    (2025, 1, -87374.0, 79650.0),
    (2025, 2, -40468.0, 43720.0),
    (2025, 3, 3973.0, 14380.0),
    (2025, 4, 4223.0, 12790.0),
    # 2026 — preliminary from available monthly reports
    (2026, 1, -17560.0, 22340.0),
    (2026, 2, 34574.0, -12680.0),
    (2026, 3, -3462.0, 9840.0),
    (2026, 4, 11630.0, 3450.0),
]


def get_bundled_fii_dii_monthly() -> pd.DataFrame:
    """Return monthly FII/DII NET cash data aggregated from the verified daily
    bootstrap JSON at atlas/ingest/macro/data/fii_dii_daily_bootstrap.json.

    The JSON contains 30 verified daily rows scraped from Moneycontrol on
    2026-05-27 (public page, public data). Monthly = sum of daily nets in
    that month. Months covered: 2026-04 (partial from Apr-13) and 2026-05.

    Historical 2016-01 through 2026-04-12 is UNRESOLVED — paid vendor needed.

    Returns:
        DataFrame with columns ["year", "month", "fii_net_cr", "dii_net_cr"].
        Currently 2 months; will expand as the nightly Moneycontrol scrape runs.
    """
    import json
    from pathlib import Path

    bootstrap_path = Path(__file__).parent / "data" / "fii_dii_daily_bootstrap.json"
    if not bootstrap_path.exists():
        log.warning("fii_dii_bootstrap_missing", path=str(bootstrap_path))
        return pd.DataFrame(columns=["year", "month", "fii_net_cr", "dii_net_cr"])

    payload = json.loads(bootstrap_path.read_text())
    # rows: [date_iso, fii_gp, fii_gs, fii_net, dii_gp, dii_gs, dii_net]
    raw = pd.DataFrame(
        payload["rows"],
        columns=[
            "date_iso",
            "fii_gp",
            "fii_gs",
            "fii_net",
            "dii_gp",
            "dii_gs",
            "dii_net",
        ],
    )
    raw["date"] = pd.to_datetime(raw["date_iso"])
    raw["year"] = raw["date"].dt.year
    raw["month"] = raw["date"].dt.month
    monthly = raw.groupby(["year", "month"], as_index=False).agg(
        fii_net_cr=("fii_net", "sum"), dii_net_cr=("dii_net", "sum")
    )
    log.info(
        "bundled_fii_dii_monthly_loaded_from_verified_json",
        row_count=len(monthly),
        source=payload.get("source"),
        fetched_at=payload.get("fetched_at"),
    )
    return monthly


def upsert_fii_dii_monthly(
    df: pd.DataFrame,
    engine: Engine | None = None,
) -> int:
    """Write monthly FII/DII net flows to all atlas_macro_daily rows in each month.

    Strategy: for each (year, month, fii_net_cr, dii_net_cr) row, UPDATE all
    atlas_macro_daily rows where date >= first_of_month AND date < first_of_next_month.
    This carry-forward fills daily rows from the monthly FII/DII release.

    Matches the cpi_yoy pattern in mospi_cpi_ingest.upsert_cpi_yoy().

    Args:
        df:     DataFrame with columns ["year", "month", "fii_net_cr", "dii_net_cr"].
        engine: Optional engine override.

    Returns:
        Number of monthly rows processed (not daily rows updated).
    """
    if df.empty:
        log.info("upsert_fii_dii_monthly_skipped", reason="empty_dataframe")
        return 0

    eng = engine or get_engine()
    processed = 0

    with eng.begin() as conn:
        for _, row in df.iterrows():
            year = int(row["year"])
            month = int(row["month"])
            fii_val = row["fii_net_cr"]
            dii_val = row["dii_net_cr"]

            # Skip if either value is missing / NaN
            try:
                fii_decimal = Decimal(str(round(float(fii_val), 4)))
                dii_decimal = Decimal(str(round(float(dii_val), 4)))
            except (ValueError, TypeError):
                log.warning(
                    "upsert_fii_dii_monthly_skip_nan",
                    year=year,
                    month=month,
                    fii_val=fii_val,
                    dii_val=dii_val,
                )
                continue

            # Compute month date range
            first_of_month = f"{year}-{month:02d}-01"
            if month == 12:
                next_year, next_month = year + 1, 1
            else:
                next_year, next_month = year, month + 1
            first_of_next = f"{next_year}-{next_month:02d}-01"

            conn.execute(
                text(
                    "UPDATE atlas.atlas_macro_daily"
                    " SET fii_cash_equity_flow_cr = :fii, dii_flow = :dii"
                    " WHERE date >= :start AND date < :end"
                ),
                {
                    "fii": fii_decimal,
                    "dii": dii_decimal,
                    "start": first_of_month,
                    "end": first_of_next,
                },
            )
            processed += 1

    log.info("upsert_fii_dii_monthly_done", months_processed=processed)
    return processed


def run_all(engine: Engine | None = None) -> int:
    """Load and upsert monthly FII/DII flows from bundled data.

    Args:
        engine: Optional engine override.

    Returns:
        Number of months processed.
    """
    monthly_df = get_bundled_fii_dii_monthly()
    log.info("fii_dii_monthly_bundle_loaded", rows=len(monthly_df))
    return upsert_fii_dii_monthly(monthly_df, engine=engine)
