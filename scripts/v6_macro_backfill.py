"""Backfill 10y of macro daily (USDINR + DXY + breadth) into atlas_macro_daily."""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd
import structlog
import yfinance as yf
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Allow running directly without editable install
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas.data_prereqs.v6.macro_daily import (
    BreadthComputer,
    MacroDailyUpserter,
)

log = structlog.get_logger()


def _fetch_yahoo(ticker: str, col_name: str, start: date, end: date) -> pd.DataFrame:
    """Fetch a single ticker from Yahoo Finance, handling multi-level columns.

    yfinance >= 0.2.38 returns MultiIndex columns (Price, Ticker) when
    auto_adjust is active. We flatten to a plain Series.
    """
    raw = yf.download(
        ticker,
        start=start,
        end=end + pd.Timedelta(days=1),
        progress=False,
    )
    if raw.empty:
        return pd.DataFrame(columns=["date", col_name])

    # Flatten MultiIndex columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    close = raw["Close"]
    # Squeeze to 1-D Series in case it's still a single-column DataFrame
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    return pd.DataFrame({"date": raw.index.date, col_name: close.values})


def main() -> None:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL is not set")

    eng = create_engine(db_url)
    session = sessionmaker(bind=eng)()
    start = date(2016, 1, 1)
    end = date.today()

    # Year-by-year to avoid Yahoo rate limits
    cur = start
    total = 0
    while cur <= end:
        yr_end = min(date(cur.year, 12, 31), end)
        log.info("backfill_year", year=cur.year, start=str(cur), end=str(yr_end))
        df_usd = _fetch_yahoo("INR=X", "usdinr", cur, yr_end)
        df_dxy = _fetch_yahoo("DX-Y.NYB", "dxy", cur, yr_end)

        log.info("fetched", year=cur.year, usd_rows=len(df_usd), dxy_rows=len(df_dxy))

        if df_usd.empty and df_dxy.empty:
            log.warning("both_empty_skipping", year=cur.year)
            cur = date(cur.year + 1, 1, 1)
            continue

        if not df_usd.empty and not df_dxy.empty:
            df = df_usd.merge(df_dxy, on="date", how="outer")
        elif not df_usd.empty:
            df = df_usd.copy()
        else:
            df = df_dxy.copy()

        # Ensure all expected columns exist for upserter
        for col in (
            "india_10y_yield",
            "risk_free_91d",
            "fii_cash_equity_flow_cr",
            "breadth_pct_above_200dma",
        ):
            if col not in df.columns:
                df[col] = None
        if "usdinr" not in df.columns:
            df["usdinr"] = None
        if "dxy" not in df.columns:
            df["dxy"] = None

        n = MacroDailyUpserter(session).upsert(df)
        log.info("upserted", year=cur.year, rows=n)
        total += n
        cur = date(cur.year + 1, 1, 1)

    log.info("yahoo_backfill_done", total_rows=total)

    # Compute breadth per date from existing atlas_stock_metrics_daily
    log.info("computing_breadth")
    dates = session.execute(
        text(
            "SELECT DISTINCT date FROM atlas.atlas_stock_metrics_daily "
            "WHERE date >= :s ORDER BY date"
        ),
        {"s": start},
    ).fetchall()
    log.info("breadth_dates_found", count=len(dates))

    bc = BreadthComputer(session)
    bread_rows = []
    for row in dates:
        val = bc.compute(row.date)
        bread_rows.append({"date": row.date, "breadth_pct_above_200dma": val})

    if bread_rows:
        for r in bread_rows:
            session.execute(
                text("""
                    INSERT INTO atlas.atlas_macro_daily (date, breadth_pct_above_200dma)
                    VALUES (:date, :breadth_pct_above_200dma)
                    ON CONFLICT (date) DO UPDATE SET
                      breadth_pct_above_200dma = EXCLUDED.breadth_pct_above_200dma
                """),
                r,
            )
        session.commit()
        log.info("breadth_upserted", days=len(bread_rows))

    log.info(
        "backfill_complete",
        total_rows=total,
        breadth_days=len(bread_rows),
    )


if __name__ == "__main__":
    main()
