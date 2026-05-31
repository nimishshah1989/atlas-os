# allow-large: single-pipeline script combining BHAV ingestion, sector mapping, ticker upsert, and verification; splitting would break cohesion
"""ETF sector backfill — NSE BHAV copy ingestion.

Seeds de_etf_master with 10 missing-sector canonical NSE tickers and
backfills their full OHLCV history from NSE equity bhavcopy archives.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py --dry-run
    PYTHONPATH=. .venv/bin/python scripts/etf_sector_backfill.py --start 2024-01-01
"""

from __future__ import annotations

import argparse
import csv
import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()

# Old format: archives.nseindia.com ZIP — available up to ~July 5, 2024
BHAV_URL_TEMPLATE = (
    "https://archives.nseindia.com/content/historical/EQUITIES"
    "/{year}/{mon}/cm{dd}{mon}{year}bhav.csv.zip"
)
BHAV_FALLBACK_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/historical/EQUITIES"
    "/{year}/{mon}/cm{dd}{mon}{year}bhav.csv.zip"
)
# New format: nsearchives full bhavcopy CSV — available from 2020-01-01 onwards
# Uses DDMMYYYY date format in the filename.
BHAV_NEW_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
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

# New format columns differ from old format.
# Old: SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY, TIMESTAMP
# New: SYMBOL, SERIES, DATE1, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, TTL_TRD_QNTY
_NEW_COL_MAP = {
    "date_col": "DATE1",
    "open_col": "OPEN_PRICE",
    "high_col": "HIGH_PRICE",
    "low_col": "LOW_PRICE",
    "close_col": "CLOSE_PRICE",
    "volume_col": "TTL_TRD_QNTY",
}
_OLD_COL_MAP = {
    "date_col": "TIMESTAMP",
    "open_col": "OPEN",
    "high_col": "HIGH",
    "low_col": "LOW",
    "close_col": "CLOSE",
    "volume_col": "TOTTRDQTY",
}


def build_bhav_url(trade_date: date, fallback: bool = False) -> str:
    """Build the old NSE archive ZIP URL for a given trading date (pre-July 2024).

    Args:
        trade_date: The trading date to build the URL for.
        fallback: If True, use the nsearchives.nseindia.com subdomain.

    Returns:
        Full URL string for the BHAV copy ZIP.
    """
    mon = trade_date.strftime("%b").upper()  # JAN, FEB, ...
    dd = trade_date.strftime("%d")  # zero-padded day
    year = trade_date.strftime("%Y")
    template = BHAV_FALLBACK_URL_TEMPLATE if fallback else BHAV_URL_TEMPLATE
    return template.format(mon=mon, dd=dd, year=year)


def build_new_bhav_url(trade_date: date) -> str:
    """Build the new NSE full-bhavcopy CSV URL for a given trading date (2020+).

    NSE introduced sec_bhavdata_full_{DDMMYYYY}.csv format from 2020 onwards.
    This URL works without session cookies.

    Args:
        trade_date: The trading date to build the URL for.

    Returns:
        Full URL string for the new-format plain CSV.
    """
    ddmmyyyy = trade_date.strftime("%d%m%Y")
    return BHAV_NEW_URL_TEMPLATE.format(ddmmyyyy=ddmmyyyy)


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
    """Create a requests.Session with NSE browser headers.

    Optionally fetches NSE homepage cookies (required for old-format ZIP
    archives). Uses a short (5, 10) timeout to avoid hanging when the NSE
    homepage is unreachable — the new-format CSV downloads work without cookies.

    Returns:
        Configured requests.Session.
    """
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    try:
        resp = session.get("https://www.nseindia.com/", timeout=(5, 10))
        resp.raise_for_status()
        log.info("nse_session_created", cookies=list(session.cookies.keys()))
    except requests.RequestException as exc:
        log.warning("nse_session_cookie_failed", error=str(exc))
    return session


def download_bhav_data(
    session: requests.Session,
    trade_date: date,
    retry: int = 2,
) -> tuple[bytes, str] | None:
    """Download one day's BHAV data, trying new CSV format then old ZIP format.

    Strategy:
    1. Try new CSV format (nsearchives sec_bhavdata_full_DDMMYYYY.csv) — works
       for 2020+ without session cookies.
    2. Fall back to old ZIP format (archives.nseindia.com, then nsearchives
       fallback) — works for 2016–July 2024.
    Returns None for 404 responses (holidays / weekends / pre-listing dates).

    Args:
        session: requests.Session from make_nse_session().
        trade_date: The trading date to download.
        retry: Maximum number of retry attempts per URL.

    Returns:
        (content_bytes, format_tag) where format_tag is "new" or "old",
        or None if no data available for this date.
    """
    # --- Attempt 1: new CSV format ---
    new_url = build_new_bhav_url(trade_date)
    for attempt in range(retry + 1):
        try:
            resp = session.get(new_url, timeout=(5, 20))
            if resp.status_code == 200:
                return resp.content, "new"
            if resp.status_code in (403, 404):
                break  # 404 = holiday/pre-2020; 403 = not in coverage range — try old
            log.warning(
                "bhav_new_download_unexpected_status",
                date=trade_date.isoformat(),
                status=resp.status_code,
                attempt=attempt,
            )
        except requests.RequestException as exc:
            log.warning(
                "bhav_new_download_error",
                date=trade_date.isoformat(),
                error=str(exc),
                attempt=attempt,
            )
        if attempt < retry:
            time.sleep(1)

    # --- Attempt 2: old ZIP format (primary + fallback subdomain) ---
    for use_fallback in (False, True):
        url = build_bhav_url(trade_date, fallback=use_fallback)
        for attempt in range(retry + 1):
            try:
                resp = session.get(url, timeout=(5, 20))
                if resp.status_code == 200:
                    return resp.content, "old"
                if resp.status_code == 404:
                    break
                log.warning(
                    "bhav_old_download_unexpected_status",
                    date=trade_date.isoformat(),
                    status=resp.status_code,
                    attempt=attempt,
                )
            except requests.RequestException as exc:
                log.warning(
                    "bhav_old_download_error",
                    date=trade_date.isoformat(),
                    error=str(exc),
                    attempt=attempt,
                )
            if attempt < retry:
                time.sleep(1)

    return None


# Keep old name as a thin wrapper for backwards compatibility with tests.
def download_bhav_zip(
    session: requests.Session,
    trade_date: date,
    retry: int = 2,
) -> bytes | None:
    """Download BHAV copy ZIP for a given trading date (old format only).

    Deprecated: use download_bhav_data() which tries both formats.
    Kept for test compatibility.
    """
    for use_fallback in (False, True):
        url = build_bhav_url(trade_date, fallback=use_fallback)
        for attempt in range(retry + 1):
            try:
                resp = session.get(url, timeout=(5, 20))
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code == 404:
                    break
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
    # ── Broad ETFs ──────────────────────────────────────────────────────────
    # sector="" means Broad (no linked_sector in atlas_universe_etfs)
    {
        "ticker": "MID150BEES",
        "name": "Nippon India ETF Nifty Midcap 150",
        "sector": "",
        "benchmark": "NIFTY MIDCAP 150",
    },
    # ── Sectoral ETFs ────────────────────────────────────────────────────────
    # sector must match atlas_sector_master.sector_name (= de_instrument.sector)
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
        "ticker": "AUTOBEES",
        "name": "Nippon India ETF Nifty Auto",
        "sector": "Automobile",  # JIP sector name is "Automobile" not "Auto"
        "benchmark": "NIFTY AUTO",
    },
    {
        "ticker": "FINIETF",
        "name": "Nippon India ETF Nifty Financial Services",
        "sector": "Financial Services",
        "benchmark": "NIFTY FINANCIAL SERVICES",
    },
    {
        "ticker": "ITBEES",
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
        "sector": "Realty",  # JIP sector name is "Realty" not "Real Estate"
        "benchmark": "NIFTY REALTY",
    },
    {
        "ticker": "METALIETF",
        "name": "Nippon India ETF Nifty Metal",
        "sector": "Metal",  # JIP sector name is "Metal" not "Metals"
        "benchmark": "NIFTY METAL",
    },
    {
        "ticker": "CONSDURBEES",
        "name": "Nippon India ETF Nifty Consumer Durables BeES",
        "sector": "Consumer Durables",
        "benchmark": "NIFTY CONSR DURBL",
    },
    {
        "ticker": "OILIETF",
        "name": "Nippon India ETF Nifty Oil & Gas",
        "sector": "Oil & Gas",
        "benchmark": "NIFTY OIL AND GAS",
    },
]

# NSE renamed several Nippon ETF symbols around June 2022.
# Maps current canonical ticker → [old BHAV symbol(s)] so the backfill
# can search old BHAV archives under the old name and store under the
# canonical name, giving continuous price history.
TICKER_BHAV_ALIASES: dict[str, list[str]] = {
    "ITBEES": ["NETFIT"],  # Nippon India ETF Nifty IT, renamed ~Jun 2022
    "MID150BEES": ["NETFMID150"],  # Nippon India ETF Nifty Midcap 150, renamed ~Jun 2022
    "PHARMABEES": ["NETFPHARMA"],  # renamed ~Jun 2022
    "HEALTHIETF": ["NETFHLT"],  # older BHAV symbol if applicable
    "AUTOBEES": ["NETFAUTO"],  # older BHAV symbol if applicable
    "METALIETF": ["NETFMETAL"],  # older BHAV symbol if applicable
    "FINIETF": ["NETFFIN"],  # older BHAV symbol if applicable
}


def safe_int_volume(value: str) -> int:
    """Parse TOTTRDQTY to int, handling float-format values NSE sometimes emits.

    Args:
        value: Raw TOTTRDQTY cell value (e.g. "50000" or "12345.00").

    Returns:
        int volume, or 0 for empty/invalid values.
    """
    v = value.strip()
    if not v:
        return 0
    try:
        return int(Decimal(v))
    except (InvalidOperation, ValueError):
        return 0


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


def _extract_rows_from_reader(
    reader: csv.DictReader,  # type: ignore[type-arg]
    targets: set[str],
    col: dict[str, str],
) -> list[dict[str, Any]]:
    """Shared row-extraction logic for both old and new BHAV CSV formats.

    Args:
        reader: csv.DictReader already positioned at the data rows.
        targets: Set of NSE ticker symbols to extract (uppercase).
        col: Column-name mapping (use _OLD_COL_MAP or _NEW_COL_MAP).

    Returns:
        List of normalised OHLCV dicts.
    """
    rows: list[dict[str, Any]] = []
    try:
        for row in reader:
            symbol = row["SYMBOL"].strip().upper()
            series = row.get("SERIES", "").strip().upper()
            if symbol not in targets or series != "EQ":
                continue
            trade_date = parse_bhav_date(row.get(col["date_col"], ""))
            if trade_date is None:
                continue
            close = safe_decimal(row.get(col["close_col"], ""))
            if close is None:
                continue
            rows.append(
                {
                    "ticker": symbol,
                    "date": trade_date,
                    "open": safe_decimal(row.get(col["open_col"], "")),
                    "high": safe_decimal(row.get(col["high_col"], "")),
                    "low": safe_decimal(row.get(col["low_col"], "")),
                    "close": close,
                    "volume": safe_int_volume(row.get(col["volume_col"], "")),
                }
            )
    except KeyError as exc:
        log.warning("bhav_csv_unexpected_schema", missing_column=str(exc))
    return rows


def parse_bhav_zip(zip_bytes: bytes, targets: set[str]) -> list[dict[str, Any]]:
    """Extract OHLCV rows for target tickers from an old-format NSE BHAV ZIP.

    The ZIP contains a single CSV with columns: SYMBOL, SERIES, OPEN, HIGH,
    LOW, CLOSE, TOTTRDQTY, TIMESTAMP. Available for dates up to ~July 2024.

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
                rows = _extract_rows_from_reader(reader, targets, _OLD_COL_MAP)
    except zipfile.BadZipFile:
        log.warning("bad_zip_file", zip_size=len(zip_bytes))
    return rows


def parse_bhav_csv(csv_bytes: bytes, targets: set[str]) -> list[dict[str, Any]]:
    """Extract OHLCV rows for target tickers from a new-format NSE BHAV CSV.

    NSE introduced sec_bhavdata_full_DDMMYYYY.csv from 2020 onwards. Columns
    are: SYMBOL, SERIES, DATE1, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE,
    TTL_TRD_QNTY. Headers have trailing spaces that are stripped before parsing.

    Args:
        csv_bytes: Raw bytes of the downloaded plain CSV file.
        targets: Set of NSE ticker symbols to extract (uppercase).

    Returns:
        List of dicts with keys: ticker, date, open, high, low, close, volume.
    """
    reader = csv.DictReader(
        io.TextIOWrapper(io.BytesIO(csv_bytes), encoding="utf-8", errors="replace")
    )
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]
    return _extract_rows_from_reader(reader, targets, _NEW_COL_MAP)


def verify_tickers(
    content: bytes,
    targets: set[str],
    fmt: str = "old",
) -> tuple[set[str], set[str]]:
    """Check which target tickers appear in a BHAV data download.

    Used before full backfill to catch typos in NSE ticker symbols.

    Args:
        content: Raw bytes of a BHAV copy (ZIP for old format, CSV for new format).
        targets: Set of canonical NSE ticker symbols to verify.
        fmt: "old" for ZIP format (pre-July 2024), "new" for plain CSV format.

    Returns:
        (found, missing) where found ∩ missing == ∅ and found ∪ missing == targets.
    """
    if fmt == "new":
        rows = parse_bhav_csv(content, targets)
    else:
        rows = parse_bhav_zip(content, targets)
    found = {r["ticker"] for r in rows}
    missing = targets - found
    return found, missing


def build_master_upsert_params(etf: dict[str, str]) -> dict:
    """Build the parameter dict for a de_etf_master upsert row.

    Args:
        etf: One entry from TARGET_ETFS with keys: ticker, name, sector, benchmark.

    Returns:
        Dict matching de_etf_master columns for use with executemany.
    """
    sector = etf.get("sector") or None  # empty string → NULL (Broad ETFs have no sector)
    return {
        "ticker": etf["ticker"],
        "name": etf["name"],
        "exchange": "NSE",
        "country": "IN",
        "currency": "INR",
        "sector": sector,
        "benchmark": etf.get("benchmark"),
        "is_active": True,
        "source": "nse_bhav",
    }


def seed_etf_master(
    engine: Engine,
    etfs: list[dict],
    dry_run: bool = False,
) -> None:
    """Ensure all target ETFs have canonical (no .NS) rows in de_etf_master.

    Uses ON CONFLICT (ticker) DO UPDATE, so safe to re-run. Logs inserted
    vs already-present counts via row count before/after.

    Args:
        engine: SQLAlchemy engine from get_engine().
        etfs: List of ETF dicts (same shape as TARGET_ETFS).
        dry_run: If True, log what would happen but make no DB changes.
    """
    upsert_sql = text("""
        INSERT INTO public.de_etf_master
            (ticker, name, exchange, country, currency, sector, benchmark, is_active, source)
        VALUES
            (:ticker, :name, :exchange, :country, :currency, :sector, :benchmark, :is_active, :source)
        ON CONFLICT (ticker) DO UPDATE SET
            name       = EXCLUDED.name,
            sector     = EXCLUDED.sector,
            benchmark  = EXCLUDED.benchmark,
            is_active  = TRUE,
            source     = EXCLUDED.source
    """)

    params_list = [build_master_upsert_params(etf) for etf in etfs]
    tickers = [p["ticker"] for p in params_list]

    if dry_run:
        log.info("dry_run_seed_etf_master", tickers=tickers)
        return

    with engine.begin() as conn:
        before = conn.execute(
            text("SELECT COUNT(*) FROM public.de_etf_master WHERE ticker = ANY(:tickers)"),
            {"tickers": tickers},
        ).scalar_one()

        conn.execute(upsert_sql, params_list)

        after = conn.execute(
            text("SELECT COUNT(*) FROM public.de_etf_master WHERE ticker = ANY(:tickers)"),
            {"tickers": tickers},
        ).scalar_one()

    log.info(
        "seed_etf_master_done",
        already_present=before,
        tickers_after=after,
        inserted=after - before,
    )


def build_ohlcv_insert_params(row: dict) -> dict:
    """Map a parsed BHAV row to de_etf_ohlcv insert params.

    Args:
        row: Dict from parse_bhav_zip with keys: ticker, date, open, high, low, close, volume.

    Returns:
        Dict ready for executemany insert into de_etf_ohlcv.
    """
    return {
        "ticker": row["ticker"],
        "date": row["date"],
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
    }


def get_tickers_needing_backfill(
    engine: Engine,
    tickers: list[str],
    min_days: int = 30,
    lookback_days: int = 90,
) -> list[str]:
    """Return tickers that have fewer than min_days of OHLCV in the last lookback_days.

    Args:
        engine: SQLAlchemy engine.
        tickers: Candidate tickers to check.
        min_days: Minimum required trading days in lookback window.
        lookback_days: How many calendar days back to look.

    Returns:
        Subset of tickers that need backfill.
    """
    sql = text("""
        SELECT m.ticker
        FROM public.de_etf_master m
        LEFT JOIN (
            SELECT ticker, COUNT(*) AS day_count
            FROM public.de_etf_ohlcv
            WHERE date >= CURRENT_DATE - (:lookback_days * INTERVAL '1 day')
            GROUP BY ticker
        ) o ON m.ticker = o.ticker
        WHERE m.ticker = ANY(:tickers)
          AND COALESCE(o.day_count, 0) < :min_days
    """)
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"tickers": tickers, "min_days": min_days, "lookback_days": lookback_days},
        ).fetchall()
    return [r[0] for r in rows]


def bulk_insert_ohlcv(
    engine: Engine,
    rows: list[dict],
    dry_run: bool = False,
) -> int:
    """Insert OHLCV rows into public.de_etf_ohlcv using ON CONFLICT DO UPDATE.

    Args:
        engine: SQLAlchemy engine.
        rows: List of dicts from parse_bhav_zip.
        dry_run: If True, log count but make no DB changes.

    Returns:
        Number of rows inserted/updated.
    """
    if not rows:
        return 0

    insert_sql = text("""
        INSERT INTO public.de_etf_ohlcv
            (ticker, date, open, high, low, close, volume)
        VALUES
            (:ticker, :date, :open, :high, :low, :close, :volume)
        ON CONFLICT (ticker, date) DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume
    """)
    params = [build_ohlcv_insert_params(r) for r in rows]

    if dry_run:
        log.info("dry_run_bulk_insert", row_count=len(params))
        return len(params)

    with engine.begin() as conn:
        conn.execute(insert_sql, params)

    return len(params)


def run_backfill(
    engine: Engine,
    tickers: list[str],
    start: date,
    end: date,
    workers: int = 8,
    dry_run: bool = False,
    session: requests.Session | None = None,
) -> dict[str, int]:
    """Download BHAV copies in parallel and insert OHLCV for target tickers.

    Args:
        engine: SQLAlchemy engine.
        tickers: Canonical NSE ticker symbols to backfill.
        start: First date to download (inclusive).
        end: Last date to download (inclusive).
        workers: Parallel download threads.
        dry_run: If True, count rows but do not write.
        session: Optional pre-authenticated NSE session. Created internally if None.

    Returns:
        Dict of ticker -> row count inserted. Zero means no data found in BHAV.
    """
    target_set = set(tickers)
    all_dates = trading_dates(start, end)
    rows_by_ticker: dict[str, list[dict]] = {t: [] for t in tickers}

    # Build reverse alias map: old_bhav_symbol → canonical ticker.
    # The BHAV search set expands to include old symbols so parse_bhav_*
    # picks them up; rows are then stored under the canonical ticker.
    alias_to_canonical: dict[str, str] = {
        alias: canonical
        for canonical, aliases in TICKER_BHAV_ALIASES.items()
        for alias in aliases
        if canonical in target_set
    }
    search_set = target_set | set(alias_to_canonical)

    log.info(
        "backfill_start",
        tickers=tickers,
        date_count=len(all_dates),
        start=start.isoformat(),
        end=end.isoformat(),
        workers=workers,
    )

    if session is None:
        session = make_nse_session()

    def fetch_one(trade_date: date) -> list[dict]:
        result = download_bhav_data(session, trade_date)
        if result is None:
            return []
        content, fmt = result
        if fmt == "new":
            return parse_bhav_csv(content, search_set)
        return parse_bhav_zip(content, search_set)

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, d): d for d in all_dates}
        for future in as_completed(futures):
            trade_date = futures[future]
            try:
                parsed = future.result()
                for row in parsed:
                    # Remap old alias → canonical before bucketing.
                    canonical = alias_to_canonical.get(row["ticker"], row["ticker"])
                    if canonical in target_set:
                        row["ticker"] = canonical
                        rows_by_ticker[canonical].append(row)
            except Exception as exc:
                log.warning(
                    "bhav_fetch_failed",
                    date=trade_date.isoformat(),
                    error=str(exc),
                )
            completed += 1
            if completed % 100 == 0:
                log.info("backfill_progress", completed=completed, total=len(all_dates))

    results: dict[str, int] = {}
    for ticker, rows in rows_by_ticker.items():
        if not rows:
            log.warning(
                "ticker_no_data",
                ticker=ticker,
                reason="UNRESOLVED — ticker not found in any BHAV file",
            )
            results[ticker] = 0
            continue
        n = bulk_insert_ohlcv(engine, rows, dry_run=dry_run)
        log.info("ticker_inserted", ticker=ticker, rows=n)
        results[ticker] = n

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="ETF sector BHAV backfill")
    parser.add_argument(
        "--start",
        default=Config.HISTORICAL_START_DATE,
        help="Start date YYYY-MM-DD (default: HISTORICAL_START_DATE)",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing to DB",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel download threads (default: 8)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip gap check and run backfill for all tickers in the given date range",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    engine = get_engine()
    tickers = [etf["ticker"] for etf in TARGET_ETFS]

    # Phase 1: Seed de_etf_master
    log.info("phase1_seed_master")
    seed_etf_master(engine, TARGET_ETFS, dry_run=args.dry_run)

    # Phase 2: Verify tickers against most-recent BHAV (new or old format)
    log.info("phase2_verify_tickers")
    session = make_nse_session()
    recent_result: tuple[bytes, str] | None = None
    for days_back in range(1, 8):
        check_date = date.today() - timedelta(days=days_back)
        if check_date.weekday() >= 5:
            continue
        recent_result = download_bhav_data(session, check_date)
        if recent_result:
            break

    if recent_result:
        recent_content, recent_fmt = recent_result
        found, missing = verify_tickers(recent_content, set(tickers), fmt=recent_fmt)
        if missing:
            log.warning(
                "tickers_not_in_bhav",
                missing=sorted(missing),
                action="These tickers returned no rows — verify NSE symbol spelling",
            )
        log.info("ticker_verification", found=sorted(found), missing=sorted(missing))
    else:
        log.warning("could_not_fetch_recent_bhav")

    # Phase 3: Gap check (skip when --force, e.g. for nightly incremental runs)
    if args.force:
        needs_backfill = tickers
        log.info("phase3_skipped_force", tickers=needs_backfill)
    else:
        log.info("phase3_gap_check")
        needs_backfill = get_tickers_needing_backfill(engine, tickers)
        if not needs_backfill:
            log.info("all_tickers_sufficient", tickers=tickers)
            return
        log.info("tickers_needing_backfill", count=len(needs_backfill), tickers=needs_backfill)

    # Phase 4: Download and insert (reuse the Phase 2 session — one cookie fetch)
    log.info("phase4_backfill", start=start.isoformat(), end=end.isoformat())
    results = run_backfill(
        engine,
        needs_backfill,
        start=start,
        end=end,
        workers=args.workers,
        dry_run=args.dry_run,
        session=session,
    )

    # Phase 5: Summary
    total = sum(results.values())
    unresolved = [t for t, n in results.items() if n == 0]
    log.info(
        "backfill_complete",
        total_rows_inserted=total,
        unresolved_tickers=unresolved,
        per_ticker=results,
    )
    if unresolved:
        print(f"\nWARNING: {len(unresolved)} tickers returned 0 rows from BHAV:")
        for t in unresolved:
            print(f"  {t} — verify at nseindia.com/market-data/all-etf")


if __name__ == "__main__":
    main()
