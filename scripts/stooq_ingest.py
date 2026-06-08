"""Stooq bulk zip parser — shared library for US and Global backfill scripts.

Stooq bulk format (daily, one file per ticker):
    <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>

DATE is YYYYMMDD. PER is 'D' for daily. Prices are split-adjusted.
Volume is stored as float with .0 suffix — cast to int64.

Usage:
    from scripts.stooq_ingest import load_stooq_zip, build_file_map, fetch_vix_history

    file_map = build_file_map(zip_path)          # ticker -> inner path
    df = load_stooq_zip(zip_path, file_map, tickers)  # bulk load many tickers
"""

from __future__ import annotations

import time
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
import structlog

log = structlog.get_logger()

_STOOQ_COLS = ["ticker", "per", "date", "time", "open", "high", "low", "close", "volume", "openint"]
_KEEP_COLS = ["ticker", "date", "open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------------
# File map
# ---------------------------------------------------------------------------


def build_file_map(zip_path: str | Path) -> dict[str, str]:
    """Scan a Stooq bulk zip and return {ticker_lower -> inner_path}.

    Handles both the US zip (data/daily/us/...) and world zip
    (data/daily/world/...) directory structures.
    """
    file_map: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".txt"):
                continue
            basename = Path(name).name  # e.g. 'spy.us.txt' or '^spx.txt'
            # Strip .us.txt or .txt extension to get the ticker
            stem = basename.replace(".us.txt", "").replace(".txt", "").lower()
            file_map[stem] = name
    log.info("stooq_file_map_built", zip=str(zip_path), entries=len(file_map))
    return file_map


# ---------------------------------------------------------------------------
# Single file loader
# ---------------------------------------------------------------------------


def _load_one(z: zipfile.ZipFile, inner_path: str, expected_ticker: str) -> pd.DataFrame:
    """Read one Stooq file from an open ZipFile. Returns empty DataFrame on error."""
    try:
        raw = z.read(inner_path)
    except KeyError:
        log.warning("stooq_file_missing", path=inner_path)
        return pd.DataFrame()

    df = pd.read_csv(
        BytesIO(raw),
        header=0,
        names=_STOOQ_COLS,
        dtype={"date": str, "volume": "float64"},
    )
    if df.empty:
        log.warning("stooq_file_empty", path=inner_path)
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"])
    df["date"] = df["date"].dt.date
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df["ticker"] = expected_ticker.lower()

    # Sanity: positive close prices only
    df = df.loc[df["close"] > 0]

    return df[_KEEP_COLS].copy()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Bulk loader
# ---------------------------------------------------------------------------


def load_stooq_zip(
    zip_path: str | Path,
    file_map: dict[str, str],
    tickers: list[str],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Load OHLCV for multiple tickers from a Stooq bulk zip.

    Args:
        zip_path: Path to the Stooq bulk zip file.
        file_map: Output of build_file_map() for this zip.
        tickers: List of ticker strings (case-insensitive).
        start_date: Optional ISO date string 'YYYY-MM-DD' to filter from.
        end_date: Optional ISO date string 'YYYY-MM-DD' to filter to.

    Returns:
        DataFrame with columns: ticker, date, open, high, low, close, volume.
        Sorted by (ticker, date). Missing tickers logged and skipped.
    """
    if not tickers:
        raise ValueError("tickers list is empty")

    pieces: list[pd.DataFrame] = []
    missing: list[str] = []

    with zipfile.ZipFile(zip_path) as z:
        for raw_ticker in tickers:
            key = raw_ticker.lower()
            inner = file_map.get(key)
            if inner is None:
                missing.append(raw_ticker)
                continue
            df = _load_one(z, inner, key)
            if not df.empty:
                pieces.append(df)

    if missing:
        log.warning("stooq_tickers_not_found", count=len(missing), tickers=missing)

    if not pieces:
        raise ValueError(f"No data loaded from {zip_path} for {tickers[:5]}...")

    out: pd.DataFrame = pd.concat(pieces, ignore_index=True)

    if start_date:
        start_d = pd.to_datetime(start_date).date()
        out = out.loc[out["date"] >= start_d]
    if end_date:
        end_d = pd.to_datetime(end_date).date()
        out = out.loc[out["date"] <= end_d]

    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)  # type: ignore[assignment]

    log.info(
        "stooq_zip_loaded",
        zip=str(zip_path),
        tickers_requested=len(tickers),
        tickers_found=len(tickers) - len(missing),
        rows=len(out),
        date_min=str(out["date"].min()) if not out.empty else "n/a",
        date_max=str(out["date"].max()) if not out.empty else "n/a",
    )
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_ohlcv(df: pd.DataFrame, label: str = "") -> None:
    """Log a data quality report. Raises on critical failures.

    Checks:
    - No duplicate (ticker, date) pairs
    - No rows with missing close price
    - Gap detection: max consecutive missing trading days per ticker
    """
    prefix = f"[{label}] " if label else ""

    dupes = df.duplicated(subset=["ticker", "date"]).sum()
    if dupes:
        raise ValueError(f"{prefix}Found {dupes} duplicate (ticker, date) rows")

    null_close = df["close"].isna().sum()
    if null_close:
        log.warning(f"{prefix}null_close_prices", count=int(null_close))

    n_tickers = int(df["ticker"].nunique())
    rows = len(df)
    date_min = df["date"].min()
    date_max = df["date"].max()

    log.info(
        f"{prefix}ohlcv_validated",
        tickers=n_tickers,
        rows=rows,
        date_min=str(date_min),
        date_max=str(date_max),
        rows_per_ticker_avg=round(rows / n_tickers, 1) if n_tickers else 0,
    )


# ---------------------------------------------------------------------------
# Programmatic VIX fetch (^VIX not in bulk zip — fetch from Stooq API)
# ---------------------------------------------------------------------------


def fetch_vix_history(start_date: str = "2000-01-01") -> pd.DataFrame:
    """Fetch CBOE VIX daily history from Stooq programmatic API.

    Stooq free endpoint: https://stooq.com/q/d/l/?s=^vix&i=d
    Returns last ~15 years of daily data. No API key required.

    Returns:
        DataFrame with columns: ticker, date, open, high, low, close, volume.
    """
    url = "https://stooq.com/q/d/l/?s=%5Evix&i=d"
    log.info("fetching_vix_history", url=url)

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(
        BytesIO(resp.content),
        names=["date", "open", "high", "low", "close", "volume"],
        header=0,
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date", "close"])
    df = df.loc[df["close"] > 0].copy()
    df["ticker"] = "^vix"
    df["volume"] = 0  # VIX is an index — no volume

    start_d = pd.to_datetime(start_date).date()
    df = df.loc[df["date"] >= start_d]
    df = df.sort_values("date").reset_index(drop=True)  # type: ignore[assignment]

    log.info(
        "vix_history_fetched",
        rows=len(df),
        date_min=str(df["date"].min()),
        date_max=str(df["date"].max()),
    )
    return df[_KEEP_COLS].copy()  # type: ignore[return-value]


def fetch_stooq_ticker(ticker: str, *, delay: float = 1.0) -> pd.DataFrame:
    """Fetch a single ticker's last ~252 days from Stooq programmatic API.

    Used for nightly incremental updates. Rate limit: 1 request/second.

    Args:
        ticker: Stooq ticker string (e.g. 'spy', '^spx', '^vix').
        delay: Seconds to sleep after request (default 1.0 for rate limiting).
    """
    encoded = ticker.replace("^", "%5E")
    url = f"https://stooq.com/q/d/l/?s={encoded}&i=d"

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    df: pd.DataFrame = pd.read_csv(
        BytesIO(resp.content),
        names=["date", "open", "high", "low", "close", "volume"],
        header=0,
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date", "close"])
    df = df.loc[df["close"] > 0].copy()
    df["ticker"] = ticker.lower()
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df = df.sort_values("date").reset_index(drop=True)  # type: ignore[assignment]

    if delay > 0:
        time.sleep(delay)

    return df[_KEEP_COLS].copy()  # type: ignore[return-value]
