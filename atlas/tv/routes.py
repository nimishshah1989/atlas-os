# atlas/tv/routes.py
"""TradingView integration API routes."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import text

from atlas.db import get_engine
from atlas.tv.csv_export import export_portfolio_csv  # type: ignore[import]
from atlas.tv.portfolio_analytics import compute_portfolio_analytics  # type: ignore[import]
from atlas.tv.rs_ratios import compute_rs_ratios  # type: ignore[import]
from atlas.tv.screener import fetch_and_upsert_all  # type: ignore[import]

router = APIRouter(prefix="/v1/tv", tags=["tv"])

_stocks_router = APIRouter(prefix="/v1/stocks", tags=["stocks-detail"])

_STALE_DAYS = 2


@router.get("/metrics/{symbol}")
async def get_tv_metrics(symbol: str) -> dict:
    """Return cached TV screener metrics for a symbol.

    meta.is_stale=True if data is >2 days old.
    """
    sql = text("""
        SELECT symbol, instrument_id::text, fetched_at,
               tv_recommend_label, recommend_all, recommend_ma, recommend_other,
               rsi_14, macd_macd, ema_20, ema_50, ema_200, atr_14,
               volume, volume_10d_avg, price, high_52w, low_52w,
               pe_ttm, ps_current, pb_fbs, debt_to_equity, roe
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


_portfolios_router = APIRouter(prefix="/v1/portfolios", tags=["portfolios-analytics"])


@_portfolios_router.get("/{portfolio_id}/analytics")
async def get_portfolio_analytics(portfolio_id: str) -> dict:
    """Return Sharpe, Sortino, Calmar, Beta, Alpha, MaxDD, TWR for a portfolio."""
    result = compute_portfolio_analytics(portfolio_id)
    if result.get("error") == "no_data":
        raise HTTPException(
            status_code=404,
            detail=f"No closed positions found for portfolio: {portfolio_id}",
        )
    daily = result.get("daily_returns")
    data_as_of = (daily[-1].get("date") if daily else None) or result.get("portfolio_date_end")
    return {
        "data": result,
        "meta": {
            "data_as_of": data_as_of,
            "fetched_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
            "source": "atlas-portfolio-analytics",
        },
    }


@_portfolios_router.get("/{portfolio_id}/tv-export.csv")
async def download_portfolio_csv(portfolio_id: str) -> Response:
    """Download portfolio as TradingView-compatible CSV."""
    csv_bytes = export_portfolio_csv(portfolio_id)
    if not csv_bytes or csv_bytes.count(b"\n") <= 1:
        raise HTTPException(status_code=404, detail=f"No lots found for portfolio: {portfolio_id}")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=portfolio-{portfolio_id}.csv"},
    )


_internal_router = APIRouter(prefix="/v1/tv/internal", tags=["tv-internal"])


@_internal_router.post("/run-screener")
async def trigger_screener() -> dict:
    """Called by pg_cron at 21:00 IST on weekdays.

    Fetches latest TradingView metrics for all universe symbols and upserts into atlas.tv_metrics.
    """
    try:
        fetch_and_upsert_all()
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@_stocks_router.get("/{symbol}/rs-ratios")
def get_rs_ratios(symbol: str, days: int = 252) -> dict:
    """Return stock/sector and stock/Nifty50 RS ratio time series."""
    result = compute_rs_ratios(symbol.upper(), days=days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=f"No price data for symbol: {symbol}")
    last_nifty_date = result["vs_nifty50"][-1]["date"] if result.get("vs_nifty50") else None
    return {
        "data": result,
        "meta": {
            "data_as_of": last_nifty_date,
            "fetched_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
            "source": "de_equity_ohlcv + de_index_prices",
        },
    }
