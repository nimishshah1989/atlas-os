#!/usr/bin/env python3
"""Daily OHLCV incremental update for us_atlas and global_atlas via yfinance.

Fetches OHLCV since the last date in each schema and upserts into stock_ohlcv.
Uses yfinance batch downloads (100 tickers/call) — no API key required.

Ticker mapping (yfinance format):
  spy   → SPY       (uppercase, no suffix for US ETFs/stocks)
  ^spx  → ^SPX      (indices keep ^ prefix)

Usage:
    python3 scripts/stooq_daily_update.py              # auto: from last DB date
    python3 scripts/stooq_daily_update.py --days 7     # explicit lookback
    python3 scripts/stooq_daily_update.py --dry-run    # print counts, no write
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

log = structlog.get_logger()

_BATCH_SIZE = 100  # yfinance handles up to ~200 tickers per call reliably


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (ROOT / ".env", Path.home() / ".env"):
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        # Strip surrounding quotes so DSN parsing isn't broken by .env quoting.
                        v = v.strip().strip('"').strip("'")
                        env[k.strip()] = v
            break
    return env


def _to_yf_symbol(ticker: str) -> str:
    """Convert DB ticker (lowercase) to yfinance symbol (uppercase)."""
    return ticker.upper()


def _fetch_batch(tickers: list[str], d1: date, d2: date) -> pd.DataFrame:
    """Download OHLCV for a batch of tickers via yfinance. Returns combined DataFrame."""
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance_not_installed", hint="pip install yfinance")
        return pd.DataFrame()

    yf_symbols = [_to_yf_symbol(t) for t in tickers]
    symbol_to_db = {_to_yf_symbol(t): t for t in tickers}

    try:
        raw = yf.download(
            yf_symbols,
            start=d1.strftime("%Y-%m-%d"),
            end=(d2 + timedelta(days=1)).strftime("%Y-%m-%d"),  # yfinance end is exclusive
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as exc:
        log.warning("yfinance_batch_failed", tickers=len(tickers), error=str(exc))
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []

    if len(yf_symbols) == 1:
        # Single ticker: flat columns
        sym = yf_symbols[0]
        df = raw.copy()
        df.columns = [c.lower() for c in df.columns]
        needed = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        if not needed or "close" not in needed:
            return pd.DataFrame()
        df = df[needed].reset_index()
        df.columns = [c.lower() for c in df.columns]
        df["ticker"] = symbol_to_db.get(sym, sym.lower())
        frames.append(df)
    else:
        # Multi-ticker: top-level columns are price type, second level is ticker
        for sym in yf_symbols:
            try:
                df = raw[sym].copy()
            except KeyError:
                log.warning("yfinance_ticker_missing", symbol=sym)
                continue
            close_col = df.get("Close", df.get("close"))
            if df.empty or (close_col is not None and close_col.isna().all()):
                continue
            df.columns = [c.lower() for c in df.columns]
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df["ticker"] = symbol_to_db.get(sym, sym.lower())
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Normalise date column
    date_col = "date" if "date" in combined.columns else "datetime"
    combined = combined.rename(columns={date_col: "date"})
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce").dt.date
    combined = combined.dropna(subset=["date", "close"])

    for col in ("open", "high", "low", "close"):
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    if "volume" in combined.columns:
        combined["volume"] = pd.to_numeric(combined["volume"], errors="coerce").fillna(0)  # type: ignore[union-attr]
        combined["volume"] = combined["volume"].astype("int64")
    else:
        combined["volume"] = 0

    keep_cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    return combined.loc[:, keep_cols]


_VALID_SCHEMAS = frozenset({"us_atlas", "global_atlas"})


def _assert_schema(schema: str) -> str:
    if schema not in _VALID_SCHEMAS:
        raise ValueError(f"schema must be one of {_VALID_SCHEMAS}, got {schema!r}")
    return schema


def _get_latest_date(engine, schema: str) -> date:
    schema = _assert_schema(schema)
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT MAX(date) FROM {schema}.stock_ohlcv")
        ).fetchone()
    if row and row[0]:
        return row[0]
    return date(2020, 1, 1)


def _get_tickers(engine, schema: str) -> list[str]:
    schema = _assert_schema(schema)
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT ticker FROM {schema}.stock_ohlcv ORDER BY ticker")
        ).fetchall()
    return [r[0] for r in rows]


def _bulk_upsert(engine, schema: str, df: pd.DataFrame) -> int:
    schema = _assert_schema(schema)
    if df.empty:
        return 0
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("ticker", "date"))
    sql = text(f"""
        INSERT INTO {schema}.stock_ohlcv ({", ".join(cols)})
        VALUES (:ticker, :date, :open, :high, :low, :close, :volume)
        ON CONFLICT (ticker, date) DO UPDATE SET {set_clause}
    """)
    rows = [
        {c: row[c] for c in cols}
        for row in df[cols].to_dict(orient="index").values()  # type: ignore[call-overload]
    ]
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def _update_schema(
    engine,
    schema: str,
    from_date: date,
    to_date: date,
    dry_run: bool,
) -> dict[str, int]:
    tickers = _get_tickers(engine, schema)
    log.info(
        "schema_update_start",
        schema=schema,
        tickers=len(tickers),
        from_date=str(from_date),
        to_date=str(to_date),
    )

    all_frames: list[pd.DataFrame] = []
    failed_batches = 0

    for i in range(0, len(tickers), _BATCH_SIZE):
        batch = tickers[i : i + _BATCH_SIZE]
        df = _fetch_batch(batch, from_date, to_date)
        if df.empty:
            failed_batches += 1
            log.warning("batch_returned_empty", batch_start=i, batch_size=len(batch))
        else:
            all_frames.append(df)
        log.info(
            "batch_done",
            schema=schema,
            batch=f"{i // _BATCH_SIZE + 1}/{(len(tickers) - 1) // _BATCH_SIZE + 1}",
            rows=len(df),
        )

    if not all_frames:
        log.warning("no_data_fetched", schema=schema)
        return {"fetched": 0, "written": 0, "failed_batches": failed_batches}

    combined = pd.concat(all_frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")

    # Row count guard
    before_rows = len(combined)
    log.info(
        "schema_update_fetched", schema=schema, rows=before_rows, failed_batches=failed_batches
    )

    written = 0
    if not dry_run:
        written = _bulk_upsert(engine, schema, combined)
        log.info("schema_update_written", schema=schema, rows=written)

    return {"fetched": before_rows, "written": written, "failed_batches": failed_batches}


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily OHLCV incremental update (yfinance)")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Explicit lookback days (default: auto from last DB date)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and count rows; do not write to DB",
    )
    args = parser.parse_args()

    _load_env()  # env vars exported into process; get_engine reads from Config
    from atlas.db import get_engine

    engine = get_engine()
    to_date = datetime.now(UTC).date()

    results = {}
    total_fetched = 0
    total_failed_batches = 0
    for schema in ("us_atlas", "global_atlas"):
        latest: date | None = None
        if args.days:
            from_date = to_date - timedelta(days=args.days)
        else:
            latest = _get_latest_date(engine, schema)
            from_date = latest + timedelta(days=1)

        if from_date > to_date:
            log.info("schema_already_current", schema=schema, latest=str(latest or from_date))
            results[schema] = {"fetched": 0, "written": 0, "failed_batches": 0}
            continue

        results[schema] = _update_schema(engine, schema, from_date, to_date, args.dry_run)
        total_fetched += results[schema]["fetched"]
        total_failed_batches += results[schema]["failed_batches"]

    log.info("daily_price_update_done", dry_run=args.dry_run, results=results)

    # P1-1 guard: if every schema fetched zero rows AND we expected some, surface a non-zero
    # exit code so notify_failure.py fires. yfinance outages otherwise look like clean success.
    if total_fetched == 0 and total_failed_batches > 0:
        log.error(
            "daily_price_update_total_failure",
            hint="all yfinance batches returned empty — likely Yahoo outage or rate-limit",
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
