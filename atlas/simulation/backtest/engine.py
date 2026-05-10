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
_FEES_PCT = 0.001  # 0.1% per leg (~0.2% round-trip)
_INDIA_RF = 0.065  # RBI repo rate (4% early 2022 → 6.5% mid-2022 onward; ~6.5% avg)


@dataclass
class BacktestResult:
    """Backtest output.

    max_drawdown: negative float (e.g. -0.15 = 15% peak-to-trough drawdown).
    sharpe_ratio / max_drawdown / total_return are None when non-finite (NaN, ±inf).
    """

    sharpe_ratio: float | None
    max_drawdown: float | None
    total_return: float | None
    daily_returns: pd.Series
    start_date: date | None
    end_date: date | None
    n_trades: int = 0


def _extract_date_range(idx: pd.DatetimeIndex) -> tuple[date | None, date | None]:
    """Return (start, end) as date objects. Returns (None, None) for empty index."""
    if len(idx) == 0:
        return None, None
    return pd.Timestamp(idx[0]).date(), pd.Timestamp(idx[-1]).date()  # type: ignore[arg-type]


def _finite_or_none(val: float) -> float | None:
    """Map NaN / ±inf to None. Preserves valid floats unchanged."""
    return float(val) if np.isfinite(val) else None


def _scalar_metric(val: float | pd.Series) -> float:  # type: ignore[type-arg]
    """Reduce a per-instrument Series to a portfolio-level scalar by mean."""
    if isinstance(val, pd.Series):
        return float(val.mean())
    return float(val)


def _sharpe_from_daily(daily_rets: pd.Series, annual_rf: float) -> float | None:
    """Annualized Sharpe using the given risk-free rate. Returns None when std=0."""
    daily_rf = (1 + annual_rf) ** (1 / 252) - 1
    excess = daily_rets - daily_rf
    std = float(excess.std())
    if std <= 0:
        return None
    return float(excess.mean() / std * np.sqrt(252))


def run_backtest(
    signal_matrix: SignalMatrix,
    init_cash: float = _INIT_CASH,
    fees_pct: float = _FEES_PCT,
    risk_free_rate: float = _INDIA_RF,
    max_positions: int = 0,
) -> BacktestResult:
    """Run vectorbt backtest on a SignalMatrix. No DB calls.

    max_positions > 0 activates cash-sharing portfolio mode: capital is shared
    across all columns with 1/max_positions allocated per position. vectorbt
    naturally skips new entries when all slots are filled (cash exhausted).
    This is the correct model for a concentrated equal-weight portfolio.

    Memory discipline: pf deleted in finally block — vectorbt Portfolio
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

        if max_positions > 0:
            # Cash-sharing portfolio: 1/max_positions allocated per position.
            # vectorbt skips entries when cash is exhausted (all slots filled).
            pf = vbt.Portfolio.from_signals(
                close=price_df,
                entries=entry_df,
                exits=exit_df,
                init_cash=init_cash,
                fees=fees_pct,
                freq="D",
                size=1.0 / max_positions,
                size_type="targetpercent",
                group_by=True,
                cash_sharing=True,
            )
        else:
            pf = vbt.Portfolio.from_signals(
                close=price_df,
                entries=entry_df,
                exits=exit_df,
                init_cash=init_cash,
                fees=fees_pct,
                freq="D",
            )

        try:
            daily_rets = pf.daily_returns()
            if isinstance(daily_rets, pd.DataFrame):
                daily_rets = daily_rets.mean(axis=1)

            # Sharpe: compute from daily returns using proper Indian risk-free rate.
            # Do NOT use pf.sharpe_ratio() — it defaults to rf=0% which inflates Sharpe.
            sharpe = _sharpe_from_daily(daily_rets, risk_free_rate)
            drawdown = _finite_or_none(_scalar_metric(pf.max_drawdown()))
            total_ret = _finite_or_none(_scalar_metric(pf.total_return()))

            try:
                stats = pf.stats()
                n_trades = int(stats.get("Total Trades", 0)) if hasattr(stats, "get") else 0
            except Exception:
                log.warning("backtest_stats_failed", exc_info=True)
                n_trades = 0

            start, end = _extract_date_range(pd.DatetimeIndex(price_df.index))

            result = BacktestResult(
                sharpe_ratio=sharpe,
                max_drawdown=drawdown,
                total_return=total_ret,
                daily_returns=daily_rets,
                start_date=start,
                end_date=end,
                n_trades=n_trades,
            )
        finally:
            del pf
            gc.collect()

    except ImportError:
        # vectorbt not installed — use pandas/numpy fallback
        result = _run_backtest_fallback(
            price_df, entry_df, exit_df, init_cash, fees_pct, risk_free_rate
        )

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
    risk_free_rate: float = _INDIA_RF,
) -> BacktestResult:
    """Pure pandas/numpy fallback when vectorbt is unavailable.

    Simulates equal-weight buy-and-hold between entry and exit signals.

    NOTE: O(n_days * n_instruments) Python loop. Acceptable only as a
    development fallback; never call in production — vectorbt runs on EC2.
    """
    dates_idx = pd.DatetimeIndex(price_df.index)
    start, end = _extract_date_range(dates_idx)

    portfolio_values = pd.Series(index=dates_idx, dtype=float)
    portfolio_values.iloc[0] = init_cash

    in_position = {col: False for col in price_df.columns}
    n_instruments = len(price_df.columns)
    allocation_per_inst = init_cash / max(n_instruments, 1)

    cash = init_cash
    holdings = {col: 0.0 for col in price_df.columns}

    for i, dt in enumerate(dates_idx):
        for col in price_df.columns:
            price = price_df.loc[dt, col]
            if entry_df.loc[dt, col] and not in_position[col]:
                shares = (allocation_per_inst * (1 - fees_pct)) / price
                holdings[col] = shares
                cash -= allocation_per_inst
                in_position[col] = True
            elif exit_df.loc[dt, col] and in_position[col]:
                proceeds = holdings[col] * price * (1 - fees_pct)
                cash += proceeds
                holdings[col] = 0.0
                in_position[col] = False

        mtm = sum(holdings[col] * price_df.iloc[i][col] for col in price_df.columns)
        portfolio_values.iloc[i] = cash + mtm

    daily_rets = portfolio_values.pct_change().fillna(0.0)
    total_ret = (portfolio_values.iloc[-1] / init_cash) - 1.0

    sharpe = _sharpe_from_daily(daily_rets, risk_free_rate)

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
