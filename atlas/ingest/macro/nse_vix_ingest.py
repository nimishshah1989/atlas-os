"""NSE India VIX historical ingest via Yahoo Finance.

Source:
  Yahoo Finance ^INDIAVIX — daily India VIX close prices.
  API: https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX
       ?period1={unix_start}&period2={unix_end}&interval=1d
  No authentication required. Standard HTTP with User-Agent header.

Why Yahoo Finance (not NSE archives):
  NSE archives hist_vix_data.csv: HTTP 404 confirmed from EC2 (2026-05-27).
  NSE historical VIX API (nseindia.com/api/historical/vixhistory): HTTP 503.
  niftyindices.com INDIA_VIX_Historicaldata.csv: HTTP 404.
  Yahoo Finance ^INDIAVIX: HTTP 200, 2568 rows daily 2016-01-01 to 2026-05-26.

Verified 2026-05-27 with curl:
  period1=1451606400 (2016-01-01) period2=1748390400 (2026-05-27) interval=1d
  Returns JSON with "timestamp" array (Unix epoch) and "close" array.

Populates:
  atlas.atlas_macro_daily.vix_9d — 9-day backward EMA of India VIX daily close.
  NSE publishes India VIX (30-day implied vol). The 9-day variant is computed
  as ewm(span=9, adjust=False) on daily VIX close (documented proxy).

All values stored as Decimal. Idempotent upsert on date PK.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import requests
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# Yahoo Finance chart API for India VIX
_YAHOO_VIX_URL = "https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX"
_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; atlas-os/1.0; +https://github.com/nimishshah/atlas-os)"
    ),
    "Accept": "application/json",
}

# EMA span for vix_9d proxy (documented in approach doc)
_VIX_9D_SPAN = 9


def fetch_vix_from_yahoo(
    start: str,
    end: str,
) -> pd.DataFrame:
    """Fetch India VIX daily close from Yahoo Finance.

    Args:
        start: ISO date string "YYYY-MM-DD" (e.g. "2016-01-01")
        end:   ISO date string "YYYY-MM-DD" (e.g. "2026-05-27")

    Returns:
        DataFrame with columns ["date", "india_vix"].
        date is ISO string "YYYY-MM-DD".
        india_vix is float (daily VIX close).
        Rows with null close values are excluded.

    Raises:
        requests.HTTPError: on non-2xx response.

    Response shape (Yahoo Finance v8 chart API):
        {
          "chart": {
            "result": [{
              "timestamp": [unix_epoch, ...],
              "indicators": {
                "quote": [{"close": [float|null, ...]}]
              }
            }]
          }
        }
    """
    # Convert ISO dates to Unix timestamps (UTC midnight)
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=UTC)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=UTC)
    period1 = int(start_dt.timestamp())
    period2 = int(end_dt.timestamp()) + 86400  # include end date

    r = requests.get(
        _YAHOO_VIX_URL,
        params={
            "period1": str(period1),
            "period2": str(period2),
            "interval": "1d",
        },
        headers=_YAHOO_HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    chart_result = r.json().get("chart", {}).get("result", [])
    if not chart_result:
        log.warning("yahoo_vix_empty_result", start=start, end=end)
        return pd.DataFrame(columns=["date", "india_vix"])

    result = chart_result[0]
    timestamps = result.get("timestamp", [])
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close", [])

    rows = []
    for ts, close_val in zip(timestamps, closes, strict=False):
        if close_val is None or (isinstance(close_val, float) and math.isnan(close_val)):
            continue
        date_str = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
        rows.append({"date": date_str, "india_vix": float(close_val)})

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "india_vix"])
    log.info(
        "yahoo_vix_fetched",
        start=start,
        end=end,
        row_count=len(df),
    )
    return df


def parse_vix_csv(csv_path: str) -> pd.DataFrame:
    """Parse NSE India VIX CSV into a clean DataFrame.

    Legacy method retained for backward compatibility and tests.
    Production code now uses fetch_vix_from_yahoo().

    Args:
        csv_path: Path to a downloaded NSE VIX CSV file.

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

    Primary source: Yahoo Finance ^INDIAVIX (daily, 2008-present).
    Fallback: csv_path argument for local fixture files (used in testing).

    NSE archives hist_vix_data.csv is 404 as of 2026-05-27.
    Yahoo Finance provides equivalent or better coverage.

    Args:
        start:    Earliest date to upsert (ISO "YYYY-MM-DD").
                  Earlier rows are used for EMA warm-up but not upserted.
        engine:   Optional engine override.
        csv_path: Override: use this local CSV instead of Yahoo Finance.
                  Intended for tests with fixture data.

    Returns:
        Number of rows upserted.
    """
    from datetime import date as _date

    end = _date.today().isoformat()

    if csv_path is not None:
        df = parse_vix_csv(csv_path)
    else:
        # Fetch from Yahoo Finance (primary source)
        # Start 30 days early to provide EMA warm-up history
        import datetime

        warmup_start = (
            datetime.date.fromisoformat(start) - datetime.timedelta(days=30)
        ).isoformat()
        df = fetch_vix_from_yahoo(warmup_start, end)

    if df.empty:
        log.warning("vix_run_all_empty_after_fetch")
        return 0

    # Compute EMA on full history (warm-up needed before start date)
    df = compute_vix_9d_ema(df)

    # Filter to atlas scope for upsert (keep EMA warm-up rows out)
    df_upsert = df[df["date"] >= start].copy()
    log.info("vix_filtered", start=start, rows_to_upsert=len(df_upsert))

    return upsert_vix(df_upsert, engine=engine)
