"""NSE India VIX historical ingest.

Source:
  NSE India VIX Historical data — downloadable CSV from NSE website.
  Primary URL: https://www.nseindia.com/api/historical/vixhistory?data=[...]
  Alternative download (direct CSV): NSE VIX history page.

Populates:
  atlas.atlas_macro_daily (via india_vix intermediate; stored only as vix_9d
  in the target schema. The india_vix column is not in atlas_macro_daily;
  see migration 097 for the exact columns. vix_9d is the primary output.)

Columns written:
  vix_9d — 9-day backward EMA of India VIX daily close (documented proxy).
            NSE publishes India VIX (30d implied vol) but NOT a 9-day variant.
            vix_9d is computed as ewm(span=9, adjust=False) on daily VIX close.

CSV format (NSE VIX historical download):
  Date | VIX Open | VIX High | VIX Low | VIX Close | Prev Close | Change | % Change
  Date format: DD-Mon-YYYY (e.g. "01-Jan-2024")
  Values: percentage points (no conversion needed)

Note on historical depth:
  NSE VIX historical data goes back to 2007-11-01.
  Atlas scope is 2016-01-01. Rows before that are included in EMA calculation
  for warm-up but filtered out of the upsert.

All values stored as Decimal. Idempotent upsert on date PK.
"""

from __future__ import annotations

import math
import os
import tempfile
from decimal import Decimal

import pandas as pd
import requests
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# NSE VIX historical download — requires session-based approach
# The actual download endpoint may need a session cookie from the main site.
_NSE_VIX_URL = "https://archives.nseindia.com/content/indices/hist_vix_data.csv"
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
    "Accept-Encoding": "gzip, deflate, br",
}

# EMA span for vix_9d proxy (documented in approach doc)
_VIX_9D_SPAN = 9


def fetch_vix_csv(
    url: str = _NSE_VIX_URL,
    dest_dir: str | None = None,
) -> str:
    """Download NSE India VIX historical CSV to a local file.

    Args:
        url:      Source URL (overridable for tests).
        dest_dir: Directory to write the file. Uses system temp dir if None.

    Returns:
        Absolute path to downloaded CSV file.

    Raises:
        requests.HTTPError: on non-2xx response.
    """
    dest = dest_dir or tempfile.mkdtemp()
    dest_path = os.path.join(dest, "india_vix_historical.csv")

    with requests.Session() as session:
        resp = session.get(url, headers=_NSE_HEADERS, timeout=60)
        resp.raise_for_status()

        with open(dest_path, "wb") as f:
            f.write(resp.content)

    log.info("vix_csv_downloaded", path=dest_path, size_bytes=len(resp.content))
    return dest_path


def parse_vix_csv(csv_path: str) -> pd.DataFrame:
    """Parse NSE India VIX CSV into a clean DataFrame.

    Args:
        csv_path: Path to the downloaded CSV file.

    Returns:
        DataFrame with columns ["date", "india_vix"].
        date is ISO string "YYYY-MM-DD".
        india_vix is the daily VIX close value (float).
        Rows with unparseable data are dropped.
    """
    try:
        df_raw = pd.read_csv(
            csv_path,
            skip_blank_lines=True,
            na_values=["", "-", "N/A"],
        )
        row_count_raw = len(df_raw)
    except Exception as exc:
        log.error("vix_csv_parse_error", path=csv_path, error=str(exc))
        return pd.DataFrame(columns=["date", "india_vix"])

    df_raw = df_raw.dropna(how="all")

    # Identify columns by name patterns (NSE CSV headers can vary slightly)
    date_col = None
    close_col = None
    for col in df_raw.columns:
        col_lower = col.strip().lower()
        if "date" in col_lower and date_col is None:
            date_col = col
        if "close" in col_lower and "prev" not in col_lower and close_col is None:
            close_col = col

    if date_col is None or close_col is None:
        # Fallback: use positional (Date=0, Close=4 in NSE format)
        cols = list(df_raw.columns)
        if len(cols) >= 5:
            date_col = cols[0]
            close_col = cols[4]
        else:
            log.warning("vix_csv_unexpected_format", columns=list(df_raw.columns))
            return pd.DataFrame(columns=["date", "india_vix"])

    rows = []
    for _, row in df_raw.iterrows():
        raw_date = str(row[date_col]).strip()
        try:
            date_str: str | None = pd.to_datetime(raw_date, format="%d-%b-%Y").strftime("%Y-%m-%d")
        except ValueError:
            try:
                date_str = pd.to_datetime(raw_date).strftime("%Y-%m-%d")
            except (ValueError, TypeError) as exc:
                log.debug("vix_csv_skip_unparseable_date", raw=raw_date, error=str(exc))
                continue

        try:
            close_val = float(str(row[close_col]).replace(",", ""))
        except (ValueError, TypeError):
            continue

        rows.append({"date": date_str, "india_vix": close_val})

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "india_vix"])
    log.info("vix_csv_parsed", rows_in=row_count_raw, rows_out=len(df))
    return df


def compute_vix_9d_ema(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 9-day backward EMA of India VIX and add as vix_9d column.

    This is a documented proxy for the 9-day VIX concept. NSE publishes
    only the 30-day India VIX; the 9-day variant is computed as a 9-period
    EMA of daily VIX close values using pandas ewm(span=9, adjust=False).

    Args:
        df: DataFrame with columns ["date", "india_vix"].
            Must be sorted chronologically (oldest first).

    Returns:
        Input DataFrame with added "vix_9d" column.
        First 8 rows have NaN (insufficient history for 9-period EMA).
        Subsequent rows have float EMA values.
    """
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)

    # Compute EMA with span=9; adjust=False for recursive EMA formula
    ema_series = df["india_vix"].ewm(span=_VIX_9D_SPAN, adjust=False).mean()

    # Set first (span-1) rows to NaN — insufficient warm-up history
    ema_series.iloc[: _VIX_9D_SPAN - 1] = float("nan")

    df["vix_9d"] = ema_series
    log.info(
        "vix_9d_computed",
        total_rows=len(df),
        non_null_rows=int(df["vix_9d"].notna().sum()),
        span=_VIX_9D_SPAN,
        proxy_note="9-day backward EMA of India VIX close (documented proxy)",
    )
    return df


def upsert_vix(
    df: pd.DataFrame,
    engine: Engine | None = None,
) -> int:
    """UPSERT vix_9d into atlas_macro_daily.

    Args:
        df:     DataFrame with columns ["date", "india_vix", "vix_9d"].
        engine: Optional engine override.

    Returns:
        Number of rows upserted.

    NaN vix_9d values are stored as NULL (not skipped — the row still upserts
    india_vix if that column existed, but since india_vix isn't a DB column,
    we write NULL for vix_9d rows with insufficient EMA history).
    """
    if df.empty:
        log.info("upsert_vix_skipped", reason="empty_dataframe")
        return 0

    eng = engine or get_engine()
    row_count_before = len(df)
    upserted = 0

    with eng.begin() as conn:
        for _, row in df.iterrows():
            vix_9d_raw = row.get("vix_9d")
            vix_9d_val: Decimal | None
            if vix_9d_raw is None or (isinstance(vix_9d_raw, float) and math.isnan(vix_9d_raw)):
                vix_9d_val = None
            else:
                vix_9d_val = Decimal(str(round(float(vix_9d_raw), 4)))

            conn.execute(
                text(
                    "INSERT INTO atlas.atlas_macro_daily (date, vix_9d) VALUES (:d, :vix_9d)"
                    " ON CONFLICT (date) DO UPDATE SET vix_9d = EXCLUDED.vix_9d"
                ),
                {"d": row["date"], "vix_9d": vix_9d_val},
            )
            upserted += 1

    log.info(
        "upsert_vix_done",
        rows_in=row_count_before,
        rows_upserted=upserted,
    )
    return upserted


def run_all(
    start: str = "2016-01-01",
    engine: Engine | None = None,
    csv_path: str | None = None,
) -> int:
    """Download, parse, compute EMA, and upsert VIX data.

    Args:
        start:    Earliest date to upsert (ISO "YYYY-MM-DD").
                  Earlier rows are used for EMA warm-up but not upserted.
        engine:   Optional engine override.
        csv_path: Override download path (for testing with local fixture).

    Returns:
        Number of rows upserted.
    """
    path = csv_path or fetch_vix_csv()
    df = parse_vix_csv(path)

    if df.empty:
        log.warning("vix_run_all_empty_after_parse")
        return 0

    # Compute EMA on full history (warm-up needed before start date)
    df = compute_vix_9d_ema(df)

    # Filter to atlas scope for upsert (keep EMA warm-up rows out)
    df_upsert = df[df["date"] >= start].copy()
    log.info("vix_filtered", start=start, rows_to_upsert=len(df_upsert))

    return upsert_vix(df_upsert, engine=engine)
