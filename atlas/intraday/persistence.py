"""Batch persistence layer for intraday bar data."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import psycopg2
import psycopg2.extras
import structlog

log = structlog.get_logger()


@dataclass
class BarRecord:
    """One 15-minute OHLCV bar with derived intraday metrics."""

    instrument_id: uuid.UUID
    bar_time: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    volume: int | None
    tick_count: int | None
    ema_20: Decimal | None
    ema_50: Decimal | None
    rs_vs_nifty: Decimal | None
    gap_filled: bool = False


def _strip_dialect(conn_str: str) -> str:
    """Strip SQLAlchemy dialect prefix for raw psycopg2 connections."""
    if conn_str.startswith("postgresql+psycopg2://"):
        return conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
    return conn_str


def upsert_bars(bars: list[BarRecord], *, conn_str: str) -> int:
    """Batch UPSERT a list of BarRecord rows into atlas_stock_metrics_intraday.

    Uses psycopg2 execute_values for efficient batch insert. On conflict on
    (instrument_id, bar_time), updates all mutable columns — reconnection may
    arrive with better OHLCV data for the same bar.

    Args:
        bars: List of BarRecord instances to upsert.
        conn_str: DSN for the atlas database.

    Returns:
        Number of rows upserted (not affected — estimated from len(bars)).
    """
    if not bars:
        return 0

    rows = [
        (
            str(bar.instrument_id),
            bar.bar_time,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            bar.tick_count,
            bar.ema_20,
            bar.ema_50,
            bar.rs_vs_nifty,
            bar.gap_filled,
        )
        for bar in bars
    ]

    upsert_sql = """
        INSERT INTO atlas.atlas_stock_metrics_intraday
            (instrument_id, bar_time, open, high, low, close, volume,
             tick_count, ema_20, ema_50, rs_vs_nifty, gap_filled, updated_at)
        VALUES %s
        ON CONFLICT (instrument_id, bar_time) DO UPDATE SET
            open        = EXCLUDED.open,
            high        = EXCLUDED.high,
            low         = EXCLUDED.low,
            close       = EXCLUDED.close,
            volume      = EXCLUDED.volume,
            tick_count  = EXCLUDED.tick_count,
            ema_20      = EXCLUDED.ema_20,
            ema_50      = EXCLUDED.ema_50,
            rs_vs_nifty = EXCLUDED.rs_vs_nifty,
            gap_filled  = EXCLUDED.gap_filled,
            updated_at  = NOW()
    """

    # Template with explicit NOW() for the updated_at extra column
    template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"

    dsn = _strip_dialect(conn_str)
    conn = psycopg2.connect(dsn)  # type: ignore[attr-defined]
    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    upsert_sql,
                    rows,
                    template=template,
                    page_size=500,
                )
    finally:
        conn.close()

    n = len(bars)
    bar_time_sample = bars[0].bar_time.isoformat() if bars else "n/a"
    log.debug("bars_upserted", bars_upserted=n, bar_time=bar_time_sample)
    return n
