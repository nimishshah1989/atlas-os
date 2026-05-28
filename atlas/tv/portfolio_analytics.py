# atlas/tv/portfolio_analytics.py
"""Compute risk/return analytics for Atlas paper portfolios."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine, load_thresholds

log = structlog.get_logger(__name__)

_MIN_BETA_OBS = 30
_ANNUALISE = 252


def _compute_sharpe(returns: pd.Series, rf_annual: Decimal) -> float:
    rf_daily = float(rf_annual) / _ANNUALISE
    excess = returns - rf_daily
    std = float(returns.std(ddof=1))
    if std == 0:
        return 0.0
    return float((excess.mean() / std) * math.sqrt(_ANNUALISE))


def _compute_sortino(returns: pd.Series, rf_annual: Decimal) -> float:
    rf_daily = float(rf_annual) / _ANNUALISE
    excess = returns - rf_daily
    downside = returns[returns < 0]
    if len(downside) == 0:
        return float("inf")
    dstd = float(downside.std(ddof=1))
    if dstd == 0:
        return float("inf")
    return float((excess.mean() / dstd) * math.sqrt(_ANNUALISE))


def _compute_beta(port_returns: pd.Series, mkt_returns: pd.Series) -> float | None:
    aligned = pd.concat([port_returns, mkt_returns], axis=1).dropna()
    if len(aligned) < _MIN_BETA_OBS:
        return None
    cov = np.cov(aligned.iloc[:, 0].values, aligned.iloc[:, 1].values)
    var_mkt = float(cov[1, 1])
    if var_mkt == 0:
        return None
    return float(cov[0, 1] / var_mkt)


def _compute_alpha(
    port_returns: pd.Series,
    mkt_returns: pd.Series,
    rf_annual: Decimal,
) -> float | None:
    beta = _compute_beta(port_returns, mkt_returns)
    if beta is None:
        return None
    rf = float(rf_annual)
    n_port = max(len(port_returns), 1)
    n_mkt = max(len(mkt_returns), 1)
    rp = float((1 + port_returns).prod() ** (_ANNUALISE / n_port) - 1)
    rm = float((1 + mkt_returns).prod() ** (_ANNUALISE / n_mkt) - 1)
    return rp - (rf + beta * (rm - rf))


def _compute_max_drawdown(returns: pd.Series) -> float:
    cumulative = (1 + returns.fillna(0)).cumprod()
    rolling_peak = cumulative.cummax()
    drawdown = cumulative / rolling_peak - 1
    return float(abs(drawdown.min()))


def _compute_calmar(returns: pd.Series) -> float | None:
    dd = _compute_max_drawdown(returns)
    if dd == 0:
        return None
    n = max(len(returns), 1)
    ann_return = float((1 + returns).prod() ** (_ANNUALISE / n) - 1)
    return ann_return / dd


def _compute_twr(returns: pd.Series) -> float:
    return float((1 + returns).prod() - 1)


def _fetch_portfolio_returns(portfolio_id: str, engine: Engine) -> pd.Series:
    """Build equal-weight daily return series from closed lots in a paper portfolio."""
    lots_sql = text("""
        SELECT
            au.symbol,
            p.entry_date,
            p.exit_date
        FROM atlas.atlas_paper_portfolio p
        JOIN atlas.atlas_universe_stocks au ON au.instrument_id = p.instrument_id
        WHERE p.portfolio_id = :pid
          AND p.exit_date IS NOT NULL
    """)
    with engine.connect() as conn:
        rows = conn.execute(lots_sql, {"pid": portfolio_id}).mappings().all()

    if not rows:
        return pd.Series(dtype=float)

    symbols = list({r["symbol"] for r in rows})
    prices_sql = text("""
        SELECT date, symbol, COALESCE(close_adj, close) AS close
        FROM public.de_equity_ohlcv
        WHERE symbol = ANY(:syms)
        ORDER BY symbol, date
    """)
    with engine.connect() as conn:
        price_rows = conn.execute(prices_sql, {"syms": symbols}).mappings().all()

    if not price_rows:
        return pd.Series(dtype=float)

    prices = pd.DataFrame(list(price_rows))
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.pivot(index="date", columns="symbol", values="close")
    daily_rets = prices.pct_change()
    return daily_rets.mean(axis=1).dropna()


def _fetch_nifty_returns(engine: Engine, start_date: str, end_date: str) -> pd.Series:
    sql = text("""
        SELECT date, close
        FROM public.de_index_prices
        WHERE index_code = 'NIFTY 50'
          AND date BETWEEN :start AND :end
        ORDER BY date
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start_date, "end": end_date}).mappings().all()
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["close"].pct_change().dropna()


def compute_portfolio_analytics(
    portfolio_id: str,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Compute and return risk/return analytics dict for a portfolio."""
    engine = engine or get_engine()
    thresholds = load_thresholds()
    rf = Decimal(str(thresholds.get("risk_free_91d", Decimal("0.065"))))

    port_returns = _fetch_portfolio_returns(portfolio_id, engine)
    if port_returns.empty:
        return {"error": "no_data", "portfolio_id": portfolio_id}

    start = str(port_returns.index.min().date())
    end = str(port_returns.index.max().date())
    nifty_returns = _fetch_nifty_returns(engine, start, end)

    sharpe = _compute_sharpe(port_returns, rf)
    sortino = _compute_sortino(port_returns, rf)
    calmar = _compute_calmar(port_returns)
    beta = _compute_beta(port_returns, nifty_returns)
    alpha = _compute_alpha(port_returns, nifty_returns, rf)
    max_dd = _compute_max_drawdown(port_returns)
    twr = _compute_twr(port_returns)
    n = max(len(port_returns), 1)
    ann_return = float((1 + port_returns).prod() ** (_ANNUALISE / n) - 1)

    aligned = pd.concat(
        {"portfolio_return": port_returns, "nifty50_return": nifty_returns},
        axis=1,
    ).dropna()

    daily_returns = [
        {
            "date": str(idx.date()),
            "portfolio_return": round(float(row["portfolio_return"]), 6),
            "nifty50_return": round(float(row["nifty50_return"]), 6),
        }
        for idx, row in aligned.iterrows()
    ]

    return {
        "portfolio_id": portfolio_id,
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4) if not math.isinf(sortino) else None,
        "calmar": round(calmar, 4) if calmar is not None else None,
        "beta": round(beta, 4) if beta is not None else None,
        "alpha": round(alpha, 4) if alpha is not None else None,
        "max_drawdown": round(max_dd, 4),
        "twr": round(twr, 4),
        "annualised_return": round(ann_return, 4),
        "observation_days": len(port_returns),
        "risk_free_rate_used": float(rf),
        "daily_returns": daily_returns,
    }
