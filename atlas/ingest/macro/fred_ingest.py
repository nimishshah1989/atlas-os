"""FRED API ingest for macro columns: US 10Y, India 10Y, risk-free 91d.

Sources:
  - DGS10            → us_10y_yield   (US 10Y Treasury Constant Maturity Rate, daily)
  - INDIRLTLT01STM   → india_10y_yield (India 10Y Government Bond Yield, monthly)
  - IRSTCI01INM156N  → risk_free_91d   (India call money/interbank rate, monthly proxy)

NOTE: brent_inr is computed in runner.py by fetching DCOILBRENTEU separately and
crossing with usdinr from atlas_macro_daily. brent_usd is NOT a DB column and
NOT in SERIES_MAP — it is held in Python memory only.

NOTE on risk_free_91d series:
  FRED does not carry India 91-day T-bill (INTGSB91D156N returns 400 - series does
  not exist). The closest available series is IRSTCI01INM156N (RBI overnight call
  money / interbank rate, monthly). Call money tracks RBI policy rate closely and
  is a standard proxy for India's risk-free short-term rate in macro models.
  Values are monthly; runner.py applies forward-fill to propagate to daily rows.

FRED series are free (key at https://fred.stlouisfed.org/docs/api/api_key.html).
Set FRED_API_KEY in .env before running.

Verified 2026-05-27:
  DGS10:           HTTP 200, daily, 2016-2026, ~2600 rows
  INDIRLTLT01STM:  HTTP 200, monthly, 2016-2026, ~123 rows
  IRSTCI01INM156N: HTTP 200, monthly, 2016-2026-03, 123 rows

All monetary/yield values stored as Decimal (never float) per fintech standards.
Tz-aware datetimes used for all timestamps.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pandas as pd
import requests
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Columns we are allowed to write to (SQL injection guard — validated before interpolation)
# brent_usd intentionally excluded — it is NOT a column in atlas_macro_daily.
# brent_inr is computed in runner.py from in-memory brent_usd × usdinr.
_SAFE_COLS: frozenset[str] = frozenset(
    {
        "us_10y_yield",
        "india_10y_yield",
        "risk_free_91d",
    }
)

# Canonical FRED series IDs for each target column.
# brent_usd (DCOILBRENTEU) is intentionally NOT here — runner.py fetches it
# separately and holds in memory for brent_inr derivation without a DB write.
SERIES_MAP: dict[str, str] = {
    "us_10y_yield": "DGS10",
    "india_10y_yield": "INDIRLTLT01STM",
    # INTGSB91D156N returns 400 (series does not exist).
    # IRSTCI01INM156N is RBI call money/interbank (monthly). Close proxy.
    "risk_free_91d": "IRSTCI01INM156N",
}

# Default historical start date aligned with atlas_macro_daily scope
_DEFAULT_START = "2016-01-01"


def fetch_series(series_id: str, start: str, end: str) -> pd.DataFrame:
    """Fetch one FRED series and return a clean DataFrame.

    Args:
        series_id: FRED series ID (e.g. "DGS10")
        start: ISO date string "YYYY-MM-DD"
        end:   ISO date string "YYYY-MM-DD"

    Returns:
        DataFrame with columns ["date", "value"] where value is float.
        FRED missing observations (value == ".") are excluded.
        Returns empty DataFrame if no observations available.

    Raises:
        KeyError: if FRED_API_KEY is not set in environment.
        requests.HTTPError: on non-2xx response.
    """
    api_key: str = os.environ["FRED_API_KEY"]  # intentional KeyError if missing

    r = requests.get(
        FRED_BASE,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start,
            "observation_end": end,
        },
        timeout=30,
    )
    r.raise_for_status()

    observations = r.json().get("observations", [])

    rows = [
        {"date": obs["date"], "value": float(obs["value"])}
        for obs in observations
        if obs.get("value") not in (".", "", None)
    ]

    if not rows:
        return pd.DataFrame(columns=["date", "value"])

    df = pd.DataFrame(rows)
    log.info(
        "fred_series_fetched",
        series_id=series_id,
        start=start,
        end=end,
        row_count=len(df),
    )
    return df


def upsert_macro_col(
    col: str,
    df: pd.DataFrame,
    engine: Engine | None = None,
) -> int:
    """UPSERT rows into atlas.atlas_macro_daily for one column.

    Uses ON CONFLICT (date) DO UPDATE so re-runs are safe.
    All values are stored as Decimal to avoid float imprecision.

    Args:
        col:    Column name in atlas_macro_daily (must be a real column).
        df:     DataFrame with columns ["date", "value"].
        engine: Optional SQLAlchemy engine (defaults to process-wide engine).

    Returns:
        Number of rows upserted.

    Row counts are logged before and after for audit trail.
    """
    if df.empty:
        log.info("upsert_macro_col_skipped", col=col, reason="empty_dataframe")
        return 0

    eng = engine or get_engine()
    row_count_before = len(df)

    # Col name is from our SERIES_MAP or a known constant — not user input.
    # Validate against the module-level safe set to prevent SQL injection.
    if col not in _SAFE_COLS:
        raise ValueError(f"upsert_macro_col: col {col!r} not in safe column set")

    upserted = 0
    with eng.begin() as conn:
        for _, row in df.iterrows():  # 2,600 rows max — iterrows acceptable at this scale
            conn.execute(
                text(
                    f"INSERT INTO atlas.atlas_macro_daily (date, {col}) VALUES (:d, :v)"  # noqa: S608
                    f" ON CONFLICT (date) DO UPDATE SET {col} = EXCLUDED.{col}"
                ),
                {"d": row["date"], "v": Decimal(str(row["value"]))},
            )
            upserted += 1

    log.info(
        "upsert_macro_col_done",
        col=col,
        rows_in=row_count_before,
        rows_upserted=upserted,
    )
    return upserted


def run_all(start: str = _DEFAULT_START, engine: Engine | None = None) -> dict[str, int]:
    """Fetch all FRED series and upsert into atlas_macro_daily.

    Args:
        start:  Historical start date (ISO "YYYY-MM-DD").
        engine: Optional engine override (for testing).

    Returns:
        Dict mapping column name → rows upserted.
    """
    from datetime import date as _date

    end = _date.today().isoformat()
    results: dict[str, int] = {}

    for col, series_id in SERIES_MAP.items():
        log.info("fred_ingest_start", col=col, series_id=series_id, start=start, end=end)
        try:
            df = fetch_series(series_id, start, end)
            count = upsert_macro_col(col, df, engine=engine)
            results[col] = count
        except KeyError as exc:
            log.error("fred_api_key_missing", col=col, error=str(exc))
            results[col] = 0
        except Exception as exc:
            log.error("fred_ingest_error", col=col, series_id=series_id, error=str(exc))
            results[col] = 0

    return results
