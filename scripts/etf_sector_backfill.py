"""ETF sector backfill — NSE BHAV copy ingestion.

Seeds de_etf_master with 10 missing-sector canonical NSE tickers and
backfills their full OHLCV history from NSE equity bhavcopy archives.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py --dry-run
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py --start 2024-01-01
"""

from __future__ import annotations

import csv
import io
import time
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
import structlog

log = structlog.get_logger()

BHAV_URL_TEMPLATE = (
    "https://archives.nseindia.com/content/historical/EQUITIES"
    "/{year}/{mon}/cm{dd}{mon}{year}bhav.csv.zip"
)
BHAV_FALLBACK_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/historical/EQUITIES"
    "/{year}/{mon}/cm{dd}{mon}{year}bhav.csv.zip"
)
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
}


def build_bhav_url(trade_date: date, fallback: bool = False) -> str:
    """Build the NSE archive URL for a given trading date.

    Args:
        trade_date: The trading date to build the URL for.
        fallback: If True, use the nsearchives.nseindia.com subdomain.

    Returns:
        Full URL string for the BHAV copy ZIP.
    """
    mon = trade_date.strftime("%b").upper()   # JAN, FEB, ...
    dd = trade_date.strftime("%d")            # zero-padded day
    year = trade_date.strftime("%Y")
    template = BHAV_FALLBACK_URL_TEMPLATE if fallback else BHAV_URL_TEMPLATE
    return template.format(mon=mon, dd=dd, year=year)


def trading_dates(start: date, end: date) -> list[date]:
    """Return all weekdays between start and end (inclusive).

    NSE holidays are not excluded — 404 responses handle those gracefully.

    Args:
        start: First date (inclusive).
        end: Last date (inclusive).

    Returns:
        List of weekday dates in ascending order.
    """
    dates = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            dates.append(current)
        current += timedelta(days=1)
    return dates


def make_nse_session() -> requests.Session:
    """Create a requests.Session with NSE cookies.

    Hits nseindia.com once to capture session cookies required for archive
    downloads. Logs a warning if the cookie fetch fails but returns the
    session anyway — downloads may still succeed without cookies for recent
    files.

    Returns:
        Configured requests.Session.
    """
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    try:
        resp = session.get("https://www.nseindia.com/", timeout=15)
        resp.raise_for_status()
        log.info("nse_session_created", cookies=list(session.cookies.keys()))
    except requests.RequestException as exc:
        log.warning("nse_session_cookie_failed", error=str(exc))
    return session


def download_bhav_zip(
    session: requests.Session,
    trade_date: date,
    retry: int = 2,
) -> bytes | None:
    """Download one BHAV copy ZIP for a given trading date.

    Tries the primary NSE archive URL first, then the fallback subdomain.
    Returns None for 404 responses (holidays / weekends / pre-listing dates).
    Retries up to `retry` times on non-404 errors with a 1-second back-off.

    Args:
        session: Authenticated requests.Session from make_nse_session().
        trade_date: The trading date to download.
        retry: Maximum number of retry attempts per URL variant.

    Returns:
        Raw ZIP bytes on success, None if not a trading day or all retries fail.
    """
    for use_fallback in (False, True):
        url = build_bhav_url(trade_date, fallback=use_fallback)
        for attempt in range(retry + 1):
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code == 404:
                    break  # Not available on this URL variant; try fallback
                log.warning(
                    "bhav_download_unexpected_status",
                    date=trade_date.isoformat(),
                    status=resp.status_code,
                    attempt=attempt,
                )
            except requests.RequestException as exc:
                log.warning(
                    "bhav_download_error",
                    date=trade_date.isoformat(),
                    error=str(exc),
                    attempt=attempt,
                )
            if attempt < retry:
                time.sleep(1)
    return None


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
    rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_name = next(
                (n for n in zf.namelist() if n.endswith(".csv")),
                None,
            )
            if csv_name is None:
                return rows
            with zf.open(csv_name) as csv_file:
                reader = csv.DictReader(
                    io.TextIOWrapper(csv_file, encoding="utf-8", errors="replace")
                )
                for row in reader:
                    symbol = row["SYMBOL"].strip().upper()
                    series = row.get("SERIES", "").strip().upper()
                    if symbol not in targets or series != "EQ":
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
    except (zipfile.BadZipFile, KeyError):
        pass
    return rows


def verify_tickers(
    zip_bytes: bytes,
    targets: set[str],
) -> tuple[set[str], set[str]]:
    """Check which target tickers appear in a BHAV copy ZIP.

    Used before full backfill to catch typos in NSE ticker symbols.

    Args:
        zip_bytes: Raw bytes of a BHAV copy ZIP (any trading day).
        targets: Set of canonical NSE ticker symbols to verify.

    Returns:
        (found, missing) where found ∩ missing == ∅ and found ∪ missing == targets.
    """
    rows = parse_bhav_zip(zip_bytes, targets)
    found = {r["ticker"] for r in rows}
    missing = targets - found
    return found, missing
