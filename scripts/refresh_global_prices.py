"""Refresh de_global_prices for benchmark tickers used by Atlas compute.

Only fetches tickers that back Atlas benchmark codes in atlas_benchmark_master
where source_table = 'de_global_prices'. Designed for nightly runs; idempotent.

Usage::

    python scripts/refresh_global_prices.py                # last 7 days
    python scripts/refresh_global_prices.py --days 30
    python scripts/refresh_global_prices.py --from-date 2026-04-25
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = structlog.get_logger()


def _parse_date(s: str) -> date:
    from datetime import datetime

    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh de_global_prices for Atlas benchmarks")
    parser.add_argument("--days", type=int, default=7, help="Look-back days (default 7)")
    parser.add_argument("--from-date", type=_parse_date, default=None)
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance_not_installed", hint="pip install yfinance")
        return 1

    import pandas as pd
    from sqlalchemy import text

    from atlas.db import get_engine

    engine = get_engine()

    # Load benchmark tickers from atlas_benchmark_master
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
            SELECT source_identifier
            FROM atlas.atlas_benchmark_master
            WHERE is_active = TRUE AND source_table = 'de_global_prices'
        """)
        ).fetchall()
    tickers = [row[0] for row in rows]

    if not tickers:
        log.warning("no_global_benchmark_tickers_found")
        return 0

    start = args.from_date or (date.today() - timedelta(days=args.days))
    end = date.today()
    log.info("refresh_global_prices_start", tickers=tickers, start=str(start), end=str(end))

    total_rows = 0
    for ticker in tickers:
        try:
            raw = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
        except Exception as exc:
            log.warning("yfinance_download_failed", ticker=ticker, error=str(exc))
            continue

        if raw is None or raw.empty:
            log.warning("yfinance_empty", ticker=ticker)
            continue

        df = raw.reset_index()[["Date", "Close"]].dropna()
        df.columns = ["date", "close"]  # type: ignore[assignment]
        df["date"] = pd.to_datetime(df["date"]).dt.date  # type: ignore[union-attr]

        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(
                    text("""
                    INSERT INTO public.de_global_prices (ticker, date, close)
                    VALUES (:ticker, :date, :close)
                    ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
                """),
                    {"ticker": ticker, "date": row["date"], "close": float(row["close"])},
                )

        log.info(
            "global_price_refreshed", ticker=ticker, rows=len(df), latest=str(df["date"].max())
        )
        total_rows += len(df)

    log.info("refresh_global_prices_done", total_rows=total_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
