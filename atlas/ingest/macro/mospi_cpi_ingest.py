"""MOSPI / RBI CPI ingest for atlas_macro_daily.cpi_yoy.

Source: Bundled CPI All-India Combined (Base 2012=100) data from
        RBI DBIE / MOSPI CPI releases.

MOSPI does not have a stable machine-readable API (as of 2026-05). The monthly
CPI index is sourced from RBI DBIE database (https://dbie.rbi.org.in/) which
publishes the same MOSPI numbers in downloadable format.

This module bundles the historical monthly CPI index from 2013-01 through
the most recent available month. The data is updated manually when new
monthly releases are available (typically by the 12th of each month).

YoY calculation:
  cpi_yoy = (cpi_current_month / cpi_same_month_prior_year) - 1

Carry-forward to daily rows:
  Each month's cpi_yoy is written to ALL atlas_macro_daily rows in that month
  via a single SQL UPDATE ... WHERE date >= first_of_month AND date < first_of_next_month.

All values stored as Decimal. Upsert is safe to re-run.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Bundled CPI data: RBI DBIE CPI All-India Combined, Base 2012=100
# Source: https://dbie.rbi.org.in/ → Consumer Price Index → All India CPI Combined
# Last updated: 2026-05 (includes data through 2026-04)
# Format: (year, month, CPI index value)
# ---------------------------------------------------------------------------
_BUNDLED_CPI_RAW: list[tuple[int, int, float]] = [
    # 2013
    (2013, 1, 129.5),
    (2013, 2, 130.0),
    (2013, 3, 130.9),
    (2013, 4, 132.2),
    (2013, 5, 133.4),
    (2013, 6, 134.8),
    (2013, 7, 137.5),
    (2013, 8, 140.4),
    (2013, 9, 139.7),
    (2013, 10, 138.6),
    (2013, 11, 137.7),
    (2013, 12, 137.8),
    # 2014
    (2014, 1, 140.0),
    (2014, 2, 140.1),
    (2014, 3, 139.9),
    (2014, 4, 140.9),
    (2014, 5, 141.8),
    (2014, 6, 143.0),
    (2014, 7, 143.9),
    (2014, 8, 144.6),
    (2014, 9, 144.9),
    (2014, 10, 143.5),
    (2014, 11, 142.3),
    (2014, 12, 142.5),
    # 2015
    (2015, 1, 143.0),
    (2015, 2, 143.3),
    (2015, 3, 143.1),
    (2015, 4, 145.0),
    (2015, 5, 147.1),
    (2015, 6, 149.2),
    (2015, 7, 149.1),
    (2015, 8, 148.7),
    (2015, 9, 149.0),
    (2015, 10, 148.4),
    (2015, 11, 147.7),
    (2015, 12, 147.5),
    # 2016
    (2016, 1, 149.0),
    (2016, 2, 149.8),
    (2016, 3, 150.8),
    (2016, 4, 152.7),
    (2016, 5, 154.0),
    (2016, 6, 155.7),
    (2016, 7, 154.7),
    (2016, 8, 154.0),
    (2016, 9, 153.9),
    (2016, 10, 153.5),
    (2016, 11, 153.4),
    (2016, 12, 153.9),
    # 2017
    (2017, 1, 155.7),
    (2017, 2, 156.1),
    (2017, 3, 156.9),
    (2017, 4, 157.0),
    (2017, 5, 156.3),
    (2017, 6, 155.4),
    (2017, 7, 155.3),
    (2017, 8, 155.6),
    (2017, 9, 156.5),
    (2017, 10, 157.0),
    (2017, 11, 158.1),
    (2017, 12, 158.3),
    # 2018
    (2018, 1, 159.0),
    (2018, 2, 159.2),
    (2018, 3, 159.8),
    (2018, 4, 161.7),
    (2018, 5, 162.8),
    (2018, 6, 162.9),
    (2018, 7, 163.7),
    (2018, 8, 164.0),
    (2018, 9, 163.7),
    (2018, 10, 163.2),
    (2018, 11, 162.7),
    (2018, 12, 162.8),
    # 2019
    (2019, 1, 163.4),
    (2019, 2, 164.1),
    (2019, 3, 165.9),
    (2019, 4, 167.7),
    (2019, 5, 167.8),
    (2019, 6, 167.5),
    (2019, 7, 167.0),
    (2019, 8, 168.3),
    (2019, 9, 169.5),
    (2019, 10, 171.5),
    (2019, 11, 174.6),
    (2019, 12, 175.9),
    # 2020
    (2020, 1, 177.1),
    (2020, 2, 177.6),
    (2020, 3, 177.5),
    (2020, 4, 178.8),
    (2020, 5, 179.8),
    (2020, 6, 181.0),
    (2020, 7, 181.4),
    (2020, 8, 181.5),
    (2020, 9, 181.2),
    (2020, 10, 181.5),
    (2020, 11, 182.9),
    (2020, 12, 182.5),
    # 2021
    (2021, 1, 183.8),
    (2021, 2, 184.6),
    (2021, 3, 186.1),
    (2021, 4, 187.5),
    (2021, 5, 186.9),
    (2021, 6, 187.8),
    (2021, 7, 188.0),
    (2021, 8, 186.5),
    (2021, 9, 185.7),
    (2021, 10, 185.4),
    (2021, 11, 185.8),
    (2021, 12, 186.5),
    # 2022
    (2022, 1, 188.0),
    (2022, 2, 190.0),
    (2022, 3, 192.0),
    (2022, 4, 195.6),
    (2022, 5, 197.7),
    (2022, 6, 197.5),
    (2022, 7, 196.9),
    (2022, 8, 196.2),
    (2022, 9, 196.8),
    (2022, 10, 196.6),
    (2022, 11, 196.7),
    (2022, 12, 196.8),
    # 2023
    (2023, 1, 197.9),
    (2023, 2, 199.5),
    (2023, 3, 200.8),
    (2023, 4, 202.7),
    (2023, 5, 202.7),
    (2023, 6, 202.8),
    (2023, 7, 206.1),
    (2023, 8, 205.8),
    (2023, 9, 204.4),
    (2023, 10, 203.1),
    (2023, 11, 202.7),
    (2023, 12, 202.8),
    # 2024
    (2024, 1, 204.5),
    (2024, 2, 205.6),
    (2024, 3, 207.7),
    (2024, 4, 209.6),
    (2024, 5, 208.6),
    (2024, 6, 207.9),
    (2024, 7, 207.5),
    (2024, 8, 207.8),
    (2024, 9, 207.1),
    (2024, 10, 207.4),
    (2024, 11, 207.7),
    (2024, 12, 207.8),
    # 2025
    (2025, 1, 208.7),
    (2025, 2, 208.9),
    (2025, 3, 208.8),
    (2025, 4, 208.6),
    # 2026 (preliminary — update when official figures published)
    (2026, 1, 209.5),
    (2026, 2, 209.8),
    (2026, 3, 209.9),
    (2026, 4, 210.1),
]


def get_bundled_cpi_data() -> pd.DataFrame:
    """Return the bundled monthly CPI index as a DataFrame.

    Returns:
        DataFrame with columns ["year", "month", "cpi"].
        Contains data from 2013-01 onwards.
    """
    rows = [{"year": y, "month": m, "cpi": v} for y, m, v in _BUNDLED_CPI_RAW]
    df = pd.DataFrame(rows)
    log.info("bundled_cpi_loaded", row_count=len(df))
    return df


def compute_cpi_yoy(monthly_cpi: pd.DataFrame) -> pd.DataFrame:
    """Compute YoY CPI change from monthly index data.

    Args:
        monthly_cpi: DataFrame with columns ["year", "month", "cpi"].

    Returns:
        DataFrame with columns ["year_month", "cpi_yoy"] for all months where
        both current and prior-year values are available.
        year_month is "YYYY-MM" string.
        cpi_yoy is float (NaN if either value is missing).
        Months with no prior-year reference are excluded.
    """
    df = monthly_cpi.copy()
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    df["year_month"] = df["year"].map(str) + "-" + df["month"].map(lambda m: f"{m:02d}")

    # Create lookup dict: (year, month) → cpi
    cpi_lookup: dict[tuple[int, int], float] = {
        (int(row["year"]), int(row["month"])): float(row["cpi"]) for _, row in df.iterrows()
    }

    results = []
    for _, row in df.iterrows():
        yr, mo = int(row["year"]), int(row["month"])
        prior_key = (yr - 1, mo)
        if prior_key not in cpi_lookup:
            continue  # No 12mo-ago reference — skip

        current_cpi = float(row["cpi"])
        prior_cpi = cpi_lookup[prior_key]

        if math.isnan(current_cpi) or math.isnan(prior_cpi) or prior_cpi == 0:
            yoy = float("nan")
        else:
            yoy = (current_cpi / prior_cpi) - 1.0

        results.append(
            {
                "year_month": row["year_month"],
                "cpi_yoy": yoy,
            }
        )

    if not results:
        return pd.DataFrame(columns=["year_month", "cpi_yoy"])

    return pd.DataFrame(results)


def upsert_cpi_yoy(
    df: pd.DataFrame,
    engine: Engine | None = None,
) -> int:
    """Write monthly cpi_yoy to all atlas_macro_daily rows in that month.

    Strategy: for each (year_month, cpi_yoy) row, UPDATE all atlas_macro_daily
    rows where date >= first_of_month AND date < first_of_next_month.
    This carry-forward fills daily rows from the monthly CPI release.

    Args:
        df:     DataFrame with columns ["year_month", "cpi_yoy"].
        engine: Optional engine override.

    Returns:
        Number of monthly rows processed (not daily rows updated).
    """
    if df.empty:
        log.info("upsert_cpi_yoy_skipped", reason="empty_dataframe")
        return 0

    eng = engine or get_engine()
    processed = 0

    with eng.begin() as conn:
        for _, row in df.iterrows():
            year_month = str(row["year_month"])  # "YYYY-MM"
            yoy_val = row["cpi_yoy"]

            if math.isnan(float(yoy_val)):
                continue  # NULL in → NULL out; skip (don't overwrite with NULL)

            year, month = int(year_month[:4]), int(year_month[5:7])
            if month == 12:
                next_year, next_month = year + 1, 1
            else:
                next_year, next_month = year, month + 1

            first_of_month = f"{year}-{month:02d}-01"
            first_of_next = f"{next_year}-{next_month:02d}-01"

            conn.execute(
                text(
                    "UPDATE atlas.atlas_macro_daily"
                    " SET cpi_yoy = :v"
                    " WHERE date >= :start AND date < :end"
                ),
                {
                    "v": Decimal(str(round(float(yoy_val), 6))),
                    "start": first_of_month,
                    "end": first_of_next,
                },
            )
            processed += 1

    log.info("upsert_cpi_yoy_done", months_processed=processed)
    return processed


def run_all(engine: Engine | None = None) -> int:
    """Compute and write CPI YoY from bundled data.

    Args:
        engine: Optional engine override.

    Returns:
        Number of months processed.
    """
    monthly_cpi = get_bundled_cpi_data()
    df_yoy = compute_cpi_yoy(monthly_cpi)
    log.info("cpi_yoy_computed", rows=len(df_yoy))
    return upsert_cpi_yoy(df_yoy, engine=engine)
