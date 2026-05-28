# atlas/tv/routes.py
"""TradingView integration API routes."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from atlas.db import get_engine
from atlas.tv.screener import fetch_and_upsert_all

router = APIRouter(prefix="/v1/tv", tags=["tv"])

_STALE_DAYS = 2


@router.get("/metrics/{symbol}")
def get_tv_metrics(symbol: str) -> dict:
    """Return cached TV screener metrics for a symbol.

    meta.is_stale=True if data is >2 days old.
    """
    sql = text("""
        SELECT symbol, instrument_id::text, fetched_at,
               tv_recommend_label, recommend_all, recommend_ma, recommend_other,
               rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
               volume, volume_10d_avg, price, high_52w, low_52w
        FROM atlas.tv_metrics
        WHERE symbol = :symbol
    """)
    with get_engine().connect() as conn:
        row = conn.execute(sql, {"symbol": symbol.upper()}).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No TV metrics for symbol: {symbol}")

    # row may be a plain dict (in tests) or a SQLAlchemy RowMapping
    row_dict = dict(row)

    fetched_at = row_dict["fetched_at"]
    if isinstance(fetched_at, str):
        fetched_at = datetime.datetime.fromisoformat(fetched_at)
    now = datetime.datetime.now(tz=datetime.UTC)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=datetime.UTC)
    is_stale = (now - fetched_at).days >= _STALE_DAYS

    return {
        "data": row_dict,
        "meta": {
            "data_as_of": fetched_at.isoformat(),
            "fetched_at": now.isoformat(),
            "is_stale": is_stale,
            "source": "tradingview-screener",
        },
    }


_internal_router = APIRouter(prefix="/v1/tv/internal", tags=["tv-internal"])


@_internal_router.post("/run-screener")
def trigger_screener() -> dict:
    """Called by pg_cron at 21:00 IST on weekdays.

    Fetches latest TradingView metrics for all universe symbols and upserts into atlas.tv_metrics.
    """
    try:
        fetch_and_upsert_all()
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
