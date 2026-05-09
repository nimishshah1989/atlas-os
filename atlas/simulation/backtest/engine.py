# atlas/simulation/backtest/engine.py
"""vectorbt-backed backtesting engine.

Pure compute — no DB calls. Takes a SignalMatrix (from signal_adapter.py)
and returns a BacktestResult with Sharpe, drawdown, total return, and daily returns Series.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog

from atlas.simulation.core.signal_adapter import SignalMatrix

log = structlog.get_logger()

_INIT_CASH = 10_000_000.0  # ₹1 crore default
_FEES_PCT = 0.001  # 0.1% round-trip


@dataclass
class BacktestResult:
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_return: float | None
    daily_returns: pd.Series
    start_date: date | None
    end_date: date | None
    n_trades: int = 0


def run_backtest(
    signal_matrix: SignalMatrix,
    init_cash: float = _INIT_CASH,
    fees_pct: float = _FEES_PCT,
) -> BacktestResult:
    """Run vectorbt backtest on a SignalMatrix. No DB calls.

    Memory discipline: del pf; gc.collect() after use — vectorbt Portfolio
    objects hold full price history in RAM.
    """
    if signal_matrix.prices.size == 0 or len(signal_matrix.instruments) == 0:
        return BacktestResult(
            sharpe_ratio=None,
            max_drawdown=None,
            total_return=0.0,
            daily_returns=pd.Series(dtype=float),
            start_date=None,
            end_date=None,
            n_trades=0,
        )

    price_df = pd.DataFrame(
        signal_matrix.prices,
        index=signal_matrix.dates,
        columns=signal_matrix.instruments,
    )
    entry_df = pd.DataFrame(
        signal_matrix.entries,
        index=signal_matrix.dates,
        columns=signal_matrix.instruments,
    )
    exit_df = pd.DataFrame(
        signal_matrix.exits,
        index=signal_matrix.dates,
        columns=signal_matrix.instruments,
    )

    try:
        import vectorbt as vbt

        pf = vbt.Portfolio.from_signals(
            close=price_df,
            entries=entry_df,
            exits=exit_df,
            init_cash=init_cash,
            fees=fees_pct,
            freq="D",
        )

        daily_rets = pf.daily_returns()
        if isinstance(daily_rets, pd.DataFrame):
            daily_rets = daily_rets.mean(axis=1)

        sharpe_val = pf.sharpe_ratio()
        sharpe = float(sharpe_val) if not np.isnan(float(sharpe_val)) else None
        drawdown = float(pf.max_drawdown())
        total_ret = float(pf.total_return())

        try:
            stats = pf.stats()
            n_trades = int(stats.get("Total Trades", 0)) if hasattr(stats, "get") else 0
        except Exception:
            n_trades = 0

        dates_idx = pd.DatetimeIndex(price_df.index)
        if len(dates_idx) > 0:
            _t0: pd.Timestamp = dates_idx[0]  # type: ignore[assignment]
            _t1: pd.Timestamp = dates_idx[-1]  # type: ignore[assignment]
            start: date | None = _t0.date()
            end: date | None = _t1.date()
        else:
            start = None
            end = None

        result = BacktestResult(
            sharpe_ratio=sharpe,
            max_drawdown=drawdown,
            total_return=total_ret,
            daily_returns=daily_rets,
            start_date=start,
            end_date=end,
            n_trades=n_trades,
        )

        del pf
        gc.collect()

    except ImportError:
        # vectorbt not installed — use pandas/numpy fallback
        result = _run_backtest_fallback(price_df, entry_df, exit_df, init_cash, fees_pct)

    log.info(
        "backtest_engine_done",
        instruments=len(signal_matrix.instruments),
        sharpe=result.sharpe_ratio,
        total_return=result.total_return,
    )
    return result


def _run_backtest_fallback(
    price_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    exit_df: pd.DataFrame,
    init_cash: float,
    fees_pct: float,
) -> BacktestResult:
    """Pure pandas/numpy fallback when vectorbt is unavailable.

    Simulates equal-weight buy-and-hold between entry and exit signals.
    """
    dates_idx = pd.DatetimeIndex(price_df.index)
    if len(dates_idx) > 0:
        _t0: pd.Timestamp = dates_idx[0]  # type: ignore[assignment]
        _t1: pd.Timestamp = dates_idx[-1]  # type: ignore[assignment]
        start: date | None = _t0.date()
        end: date | None = _t1.date()
    else:
        start = None
        end = None

    # Simple simulation: track portfolio value
    # For each instrument, enter at entry signal price, exit at exit signal price
    portfolio_values = pd.Series(index=dates_idx, dtype=float)
    portfolio_values.iloc[0] = init_cash

    in_position = {col: False for col in price_df.columns}
    n_instruments = len(price_df.columns)
    allocation_per_inst = init_cash / max(n_instruments, 1)

    cash = init_cash
    holdings = {col: 0.0 for col in price_df.columns}  # shares held

    for i, dt in enumerate(dates_idx):
        for col in price_df.columns:
            price = price_df.loc[dt, col]
            if entry_df.loc[dt, col] and not in_position[col]:
                # Buy
                shares = (allocation_per_inst * (1 - fees_pct)) / price
                holdings[col] = shares
                cash -= allocation_per_inst
                in_position[col] = True
            elif exit_df.loc[dt, col] and in_position[col]:
                # Sell
                proceeds = holdings[col] * price * (1 - fees_pct)
                cash += proceeds
                holdings[col] = 0.0
                in_position[col] = False

        # Portfolio value = cash + mark-to-market
        mtm = sum(holdings[col] * price_df.iloc[i][col] for col in price_df.columns)
        portfolio_values.iloc[i] = cash + mtm

    daily_rets = portfolio_values.pct_change().fillna(0.0)
    total_ret = (portfolio_values.iloc[-1] / init_cash) - 1.0

    # Sharpe ratio (annualized, risk-free=0)
    if daily_rets.std() > 0:
        sharpe = float((daily_rets.mean() / daily_rets.std()) * np.sqrt(252))
    else:
        sharpe = None

    # Max drawdown
    running_max = portfolio_values.cummax()
    drawdown_series = (portfolio_values - running_max) / running_max
    max_dd = float(drawdown_series.min())

    return BacktestResult(
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        total_return=float(total_ret),
        daily_returns=daily_rets,
        start_date=start,
        end_date=end,
        n_trades=0,
    )
