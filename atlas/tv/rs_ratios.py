"""Compute RS ratio time series for a stock vs its sector index and vs Nifty 50."""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

# Sector name → NSE index code mapping (primary sector indices).
# Falls back to NIFTY 50 for unmapped sectors.
_SECTOR_INDEX: dict[str, str] = {
    "Energy": "NIFTY ENERGY",
    "Oil Gas & Consumable Fuels": "NIFTY OIL GAS",
    "Information Technology": "NIFTY IT",
    "Financial Services": "NIFTY FINANCIAL SERVICES",
    "Banks": "NIFTY BANK",
    "Fast Moving Consumer Goods": "NIFTY FMCG",
    "Pharmaceuticals & Biotechnology": "NIFTY PHARMA",
    "Automobiles & Auto Components": "NIFTY AUTO",
    "Capital Goods": "NIFTY INDIA MANUFACTURING",
    "Metals & Mining": "NIFTY METAL",
    "Realty": "NIFTY REALTY",
    "Consumer Durables": "NIFTY CONSUMER DURABLES",
    "Telecommunication": "NIFTY MEDIA",
    "Healthcare": "NIFTY HEALTHCARE INDEX",
    "Chemicals": "NIFTY COMMODITIES",
    "Power": "NIFTY COMMODITIES",
}
_NIFTY50 = "NIFTY 50"


def _get_sector(symbol: str, engine: Engine) -> str | None:
    """Return the sector for *symbol* from atlas_universe_stocks, or None."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT sector FROM atlas.atlas_universe_stocks "
                    "WHERE symbol = :sym AND effective_to IS NULL LIMIT 1"
                ),
                {"sym": symbol},
            )
            .mappings()
            .first()
        )
    return row["sector"] if row else None


def _get_prices(
    symbol: str,
    index_codes: list[str],
    days: int,
    engine: Engine,
) -> pd.DataFrame:
    """Return wide DataFrame columns=[symbol, *index_codes], index=date.

    Joins on inner — only trading days where both stock and all requested
    indices have a close price are included.
    """
    stock_sql = text("""
        SELECT date, COALESCE(close_adj, close) AS close
        FROM public.de_equity_ohlcv
        WHERE symbol = :sym
          AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY date
    """)
    with engine.connect() as conn:
        stock_rows = conn.execute(stock_sql, {"sym": symbol, "days": days}).mappings().all()

    index_sql = text("""
        SELECT date, index_code, close
        FROM public.de_index_prices
        WHERE index_code = ANY(:codes)
          AND date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY date
    """)
    with engine.connect() as conn:
        index_rows = conn.execute(index_sql, {"codes": index_codes, "days": days}).mappings().all()

    if not stock_rows or not index_rows:
        return pd.DataFrame()

    stock_df = pd.DataFrame(list(stock_rows)).rename(columns={"close": symbol})
    stock_df["date"] = pd.to_datetime(stock_df["date"])
    stock_df = stock_df.set_index("date")

    idx_df = pd.DataFrame(list(index_rows))
    idx_df["date"] = pd.to_datetime(idx_df["date"])
    idx_wide = idx_df.pivot(index="date", columns="index_code", values="close")

    return stock_df.join(idx_wide, how="inner")


def _classify_rs_status(pct_from_resistance: float) -> str:
    """Map percentage below 52-week resistance to a human-readable status label.

    Rules:
      >= -3%  → BREAKING_OUT   (at or above the 97th percentile of the range)
      >= -8%  → AT_RESISTANCE  (approaching but not through)
      <  -8%  → BELOW_RESISTANCE
    """
    if pct_from_resistance >= -0.03:
        return "BREAKING_OUT"
    if pct_from_resistance >= -0.08:
        return "AT_RESISTANCE"
    return "BELOW_RESISTANCE"


def compute_rs_ratios(
    symbol: str,
    days: int = 252,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Return RS ratio time series for *symbol* vs its sector index and Nifty 50.

    Return shape:
    {
        "symbol": str,
        "sector": str | None,
        "sector_index_code": str,
        "vs_sector": [{"date": "YYYY-MM-DD", "ratio": float}, ...],
        "vs_sector_resistance": float,
        "vs_sector_status": "BREAKING_OUT" | "AT_RESISTANCE" | "BELOW_RESISTANCE",
        "vs_nifty50": [...],
        "vs_nifty50_resistance": float,
        "vs_nifty50_status": str,
    }

    Returns {"error": "no_data", "symbol": symbol} when price data is absent.
    """
    engine = engine or get_engine()
    sector = _get_sector(symbol, engine)
    sector_index_code = _SECTOR_INDEX.get(sector or "", _NIFTY50)

    # De-duplicate in case sector maps to NIFTY 50 (e.g. unmapped sector)
    index_codes = list({sector_index_code, _NIFTY50})
    df = _get_prices(symbol, index_codes, days, engine)

    if df.empty or symbol not in df.columns:
        return {"error": "no_data", "symbol": symbol}

    result: dict[str, Any] = {
        "symbol": symbol,
        "sector": sector,
        "sector_index_code": sector_index_code,
        "vs_sector": [],
        "vs_nifty50": [],
    }

    for col_name, key in [(sector_index_code, "vs_sector"), (_NIFTY50, "vs_nifty50")]:
        if col_name not in df.columns:
            continue
        ratio = (df[symbol] / df[col_name]).dropna()
        if ratio.empty:
            continue

        resistance = float(ratio.max())  # 52-week high of the ratio series
        current = float(ratio.iloc[-1])
        pct_from_resistance = (current - resistance) / resistance

        result[key] = [
            {"date": str(idx.date()), "ratio": round(float(val), 6)}  # type: ignore[arg-type]
            for idx, val in ratio.items()
        ]
        result[f"{key}_resistance"] = round(resistance, 6)
        result[f"{key}_status"] = _classify_rs_status(pct_from_resistance)

    return result
