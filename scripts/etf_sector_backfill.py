"""ETF sector backfill — NSE BHAV copy ingestion.

Seeds de_etf_master with 10 missing-sector canonical NSE tickers and
backfills their full OHLCV history from NSE equity bhavcopy archives.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py --dry-run
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py --start 2024-01-01
"""

from __future__ import annotations

import argparse  # noqa: F401 — used in Task 2 CLI entry point
import csv
import io
import time  # noqa: F401 — used in Task 3 rate-limiting
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: F401 — Task 4
from datetime import date, datetime, timedelta  # noqa: F401 — timedelta used in Task 2
from decimal import Decimal, InvalidOperation
from typing import Any

import requests  # noqa: F401 — used in Task 3 HTTP download
import structlog
from sqlalchemy import text  # noqa: F401 — used in Task 5 DB writes

from atlas.config import Config  # noqa: F401 — used in Task 5
from atlas.db import get_engine  # noqa: F401 — used in Task 5

log = structlog.get_logger()

TARGET_ETFS: list[dict[str, str]] = [
    {
        "ticker": "NETFMID150",
        "name": "Nippon India ETF Nifty Midcap 150",
        "sector": "Midcap",
        "benchmark": "NIFTY MIDCAP 150",
    },
    {
        "ticker": "PHARMABEES",
        "name": "Nippon India ETF Nifty Pharma",
        "sector": "Pharma",
        "benchmark": "NIFTY PHARMA",
    },
    {
        "ticker": "HEALTHIETF",
        "name": "Nippon India ETF Nifty Healthcare",
        "sector": "Healthcare",
        "benchmark": "NIFTY HEALTHCARE",
    },
    {
        "ticker": "CONSUMBEES",
        "name": "Nippon India ETF Nifty Consumption",
        "sector": "Consumption",
        "benchmark": "NIFTY INDIA CONSUMPTION",
    },
    {
        "ticker": "AUTOBEES",
        "name": "Nippon India ETF Nifty Auto",
        "sector": "Auto",
        "benchmark": "NIFTY AUTO",
    },
    {
        "ticker": "FINIETF",
        "name": "Nippon India ETF Nifty Financial Svcs",
        "sector": "Financial Services",
        "benchmark": "NIFTY FINANCIAL SERVICES",
    },
    {
        "ticker": "NETFIT",
        "name": "Nippon India ETF Nifty IT",
        "sector": "IT",
        "benchmark": "NIFTY IT",
    },
    {
        "ticker": "MOENERGY",
        "name": "Motilal Oswal Nifty Energy ETF",
        "sector": "Energy",
        "benchmark": "NIFTY ENERGY",
    },
    {
        "ticker": "MOREALTY",
        "name": "Motilal Oswal Nifty Realty ETF",
        "sector": "Real Estate",
        "benchmark": "NIFTY REALTY",
    },
    {
        "ticker": "NETFMETAL",
        "name": "Nippon India ETF Nifty Metal",
        "sector": "Metals",
        "benchmark": "NIFTY METAL",
    },
]


def safe_decimal(value: str) -> Decimal | None:
    """Parse a string into Decimal, returning None for empty or invalid input.

    Args:
        value: Raw string from CSV cell.

    Returns:
        Decimal on success, None for empty string or unparseable value.
    """
    v = value.strip()
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def parse_bhav_date(timestamp: str) -> date | None:
    """Parse NSE BHAV copy date string into a date object.

    NSE uses DD-MON-YYYY format (e.g. "07-APR-2016"). Tries abbreviated month
    name first (%b), then full month name (%B) as a fallback.

    Args:
        timestamp: Raw TIMESTAMP cell value from BHAV CSV.

    Returns:
        date on success, None if the string cannot be parsed.
    """
    v = timestamp.strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def parse_bhav_zip(zip_bytes: bytes, targets: set[str]) -> list[dict[str, Any]]:
    """Extract OHLCV rows for target tickers from an NSE BHAV copy ZIP.

    The ZIP contains a single CSV with one row per traded symbol. This
    function filters to EQ-series rows whose SYMBOL is in ``targets``,
    parses date and price columns, and returns a list of normalised dicts.

    Args:
        zip_bytes: Raw bytes of the downloaded ZIP archive.
        targets: Set of NSE ticker symbols to extract (uppercase).

    Returns:
        List of dicts with keys: ticker, date, open, high, low, close, volume.
        Returns an empty list on any archive / parsing error.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
            with zf.open(csv_name) as csv_file:
                reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8"))
                rows: list[dict[str, Any]] = []
                for row in reader:
                    symbol = row["SYMBOL"].strip().upper()
                    if symbol not in targets:
                        continue
                    if row["SERIES"].strip() != "EQ":
                        continue
                    trade_date = parse_bhav_date(row["TIMESTAMP"])
                    if trade_date is None:
                        continue
                    close = safe_decimal(row["CLOSE"])
                    if close is None:
                        continue
                    rows.append(
                        {
                            "ticker": symbol,
                            "date": trade_date,
                            "open": safe_decimal(row["OPEN"]),
                            "high": safe_decimal(row["HIGH"]),
                            "low": safe_decimal(row["LOW"]),
                            "close": close,
                            "volume": int(row["TOTTRDQTY"].strip() or "0"),
                        }
                    )
                return rows
    except (zipfile.BadZipFile, KeyError, StopIteration):
        return []
