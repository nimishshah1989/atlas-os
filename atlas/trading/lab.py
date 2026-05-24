"""V5 baseline backtest engine — promoted from /tmp/baseline_v5_*.py.

Same signal stack as atlas/trading/simulator.py (NATR-14, beta_alpha_63d,
mom_low_vol) but a much simpler portfolio loop: top-N by combined rank,
monthly rebalance, 21-day hold, no genome overlay.

Two strategy modes:
  BASELINE-V5             equal-weight, no overlay        (aggressive)
  BASELINE-V5-RP          inverse-vol weighting           (risk-parity)
  BASELINE-V5-TREND       equal-weight + trend filter     (defensive)
  BASELINE-V5-RP-TREND    inverse-vol + trend filter      (conservative)

The trend filter scales gross exposure to `gross_offtrend` (default 0.5)
when benchmark 50-day MA < 200-day MA at the rebalance date.

This module composes data_loader primitives — it does not duplicate signal
math. New universes (ETFs, MFs) plug in by providing an alternative
metrics_df schema with the same columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
import structlog

from atlas.trading.data_loader import (
    compute_beta_alpha_63d,
    compute_mom_low_vol,
    compute_natr_14,
)


def _lab_pivot(df: pd.DataFrame, col: str, instruments: list, dates: list) -> np.ndarray:
    """Minimal (n_stocks, n_days) pivot for the lab — only the columns lab needs."""
    pivoted = df.pivot(index="instrument_id", columns="date", values=col)
    return pivoted.reindex(index=instruments, columns=dates).values.astype(np.float32)


log = structlog.get_logger()


@dataclass
class BacktestResult:
    """Aggregated outcome of a single V5 backtest run.

    Fields parallel atlas_strategy_leaderboard + atlas_strategy_validation so
    deployment scripts can write them without translation.
    """

    strategy_name: str
    alpha_oos: float
    port_annual_return: float
    bench_annual_return: float
    port_max_drawdown: float
    bench_max_drawdown: float
    hit_rate: float
    information_ratio: float
    alpha_t_stat: float
    n_periods: int
    n_trades: int
    yearly: list[dict] = field(default_factory=list)


def _compute_conviction_panel(
    metrics_df: pd.DataFrame, regime_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build (n_stocks, n_days) conviction matrix from raw metrics.

    Returns:
        conviction_df: DataFrame indexed by (instrument_id, date) with `conv` col.
        bench_df:      regime DataFrame reindexed to the same date axis with
                       nifty500_close, ma50, ma200, trend_up columns.
    """
    df = metrics_df.sort_values(["date", "instrument_id"])
    dates = sorted(df["date"].unique())
    instruments = sorted(df["instrument_id"].unique())

    close = _lab_pivot(df, "close", instruments, dates)
    high = _lab_pivot(df, "high", instruments, dates)
    low = _lab_pivot(df, "low", instruments, dates)
    ret_12m = _lab_pivot(df, "ret_12m", instruments, dates)
    realized_vol = _lab_pivot(df, "realized_vol_63", instruments, dates)

    rdf = regime_df.set_index("date").reindex(dates)
    rdf["nifty500_close"] = rdf["nifty500_close"].ffill().bfill()
    rdf["ma50"] = rdf["nifty500_close"].rolling(50, min_periods=20).mean()
    rdf["ma200"] = rdf["nifty500_close"].rolling(200, min_periods=100).mean()
    rdf["trend_up"] = (rdf["ma50"] > rdf["ma200"]).astype(int)
    nifty500_close_arr = rdf["nifty500_close"].astype(np.float64).to_numpy()

    # v5 signals
    natr = compute_natr_14(high, low, close)
    beta_alpha = compute_beta_alpha_63d(close, nifty500_close_arr)
    mom_lv = compute_mom_low_vol(ret_12m, realized_vol)

    # Cross-sectional rank per day, then equal-weight mean
    def _xs_rank(arr: np.ndarray) -> np.ndarray:
        return pd.DataFrame(arr).rank(axis=0, pct=True).fillna(0.0).to_numpy().astype(np.float32)

    conviction = (_xs_rank(natr) + _xs_rank(beta_alpha) + _xs_rank(mom_lv)) / 3.0

    # Long-form for backtest loop
    conv_rows = []
    for s_idx, iid in enumerate(instruments):
        for d_idx, dt in enumerate(dates):
            conv_rows.append(
                {
                    "instrument_id": iid,
                    "date": dt,
                    "close": float(close[s_idx, d_idx]),
                    "realized_vol_63": float(realized_vol[s_idx, d_idx]),
                    "conv": float(conviction[s_idx, d_idx]),
                }
            )
    conv_df = pd.DataFrame(conv_rows)
    return conv_df, rdf.reset_index()


def _monthly_rebalance_dates(all_dates: list, hold_days: int) -> list:
    """Return month-end trading dates with hold_days of forward room."""
    if len(all_dates) < hold_days + 1:
        return []
    series = pd.Series(pd.to_datetime(all_dates))
    last_per_month = series.groupby(series.dt.to_period("M")).idxmax().tolist()
    return [all_dates[i] for i in last_per_month if i < len(all_dates) - hold_days]


def _run_monthly_backtest(
    conv_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    top_n: int,
    rebalance_days: int,
    weighting: Literal["equal", "inverse_vol"],
    trend_filter: bool,
    gross_offtrend: float,
) -> tuple[list[dict], int]:
    """Loop over monthly rebalance dates, return per-period records + trade count.

    Each record: {rebal_date, end_date, port_return, bench_return, gross, n_holdings}.
    """
    conv_df = conv_df.copy()
    conv_df["date"] = pd.to_datetime(conv_df["date"])
    bench_df = bench_df.copy()
    bench_df["date"] = pd.to_datetime(bench_df["date"])

    all_dates = sorted(conv_df["date"].unique())
    rebal_dates = _monthly_rebalance_dates(all_dates, rebalance_days)
    bench_lookup = bench_df.set_index("date")

    periods: list[dict] = []
    total_trades = 0

    for rd in rebal_dates:
        try:
            d_idx = all_dates.index(rd)
        except ValueError:
            continue
        end_idx = d_idx + rebalance_days
        if end_idx >= len(all_dates):
            continue
        end_date = all_dates[end_idx]

        day_view = conv_df[conv_df["date"] == rd].dropna(subset=["conv"])
        if weighting == "inverse_vol":
            day_view = day_view[day_view["realized_vol_63"] > 0]
        cohort = day_view.nlargest(top_n, "conv")
        if len(cohort) < top_n:
            continue

        end_view = conv_df[conv_df["date"] == end_date].set_index("instrument_id")["close"]

        # Position weights
        if weighting == "inverse_vol":
            inv_vol = 1.0 / cohort["realized_vol_63"].to_numpy()
            weights = inv_vol / inv_vol.sum()
        else:
            weights = np.ones(len(cohort)) / len(cohort)

        # Apply trend filter gross scaler
        if trend_filter:
            trend_now = bench_lookup.loc[rd, "trend_up"] if rd in bench_lookup.index else 1
            gross = 1.0 if int(trend_now) == 1 else gross_offtrend
        else:
            gross = 1.0

        # Compute weighted return; drop stocks not present at end_date
        weighted_ret = 0.0
        total_weight = 0.0
        for w, (_, row) in zip(weights, cohort.iterrows(), strict=False):
            iid = row["instrument_id"]
            if iid in end_view.index:
                stock_ret = end_view[iid] / row["close"] - 1
                weighted_ret += w * float(stock_ret)
                total_weight += w
        if total_weight < 0.5:
            continue
        port_ret = (weighted_ret / total_weight) * gross

        # Benchmark return
        if rd not in bench_lookup.index or end_date not in bench_lookup.index:
            continue
        n500_s = float(bench_lookup.loc[rd, "nifty500_close"])
        n500_e = float(bench_lookup.loc[end_date, "nifty500_close"])
        bench_ret = (n500_e / n500_s - 1) if n500_s > 0 else 0.0

        periods.append(
            {
                "rebal_date": rd,
                "end_date": end_date,
                "port_return": port_ret,
                "bench_return": bench_ret,
                "gross": gross,
                "n_holdings": len(cohort),
            }
        )
        total_trades += len(cohort)

    return periods, total_trades


def _aggregate_yearly(periods: list[dict]) -> list[dict]:
    """Group per-period records by year, compute per-year stats."""
    if not periods:
        return []
    pdf = pd.DataFrame(periods)
    pdf["year"] = pdf["rebal_date"].dt.year
    yearly_records = []
    for yr, grp in pdf.groupby("year"):
        py = (1 + grp["port_return"]).prod() - 1
        by = (1 + grp["bench_return"]).prod() - 1
        p_eq = (1 + grp["port_return"]).cumprod()
        b_eq = (1 + grp["bench_return"]).cumprod()
        p_dd = (p_eq / p_eq.cummax() - 1).min()
        b_dd = (b_eq / b_eq.cummax() - 1).min()
        yearly_records.append(
            {
                "year": int(yr),
                "strategy_return": float(py),
                "benchmark_return": float(by),
                "alpha": float(py - by),
                "max_drawdown": float(abs(p_dd)),
                "benchmark_max_drawdown": float(abs(b_dd)),
                "n_trades": int(grp["n_holdings"].sum()),
            }
        )
    return yearly_records


def _strategy_name(weighting: str, trend_filter: bool) -> str:
    parts = ["BASELINE-V5"]
    if weighting == "inverse_vol":
        parts.append("RP")
    if trend_filter:
        parts.append("TREND")
    return "-".join(parts)


def run_baseline_v5(
    metrics_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    top_n: int = 20,
    rebalance_days: int = 21,
    weighting: Literal["equal", "inverse_vol"] = "equal",
    trend_filter: bool = False,
    gross_offtrend: float = 0.5,
) -> BacktestResult:
    """Run the V5 baseline backtest with configurable weighting + trend filter.

    metrics_df columns: instrument_id, date, close, high, low, ret_12m, realized_vol_63
    regime_df columns:  date, nifty500_close
    """
    conv_df, bench_df = _compute_conviction_panel(metrics_df, regime_df)
    periods, total_trades = _run_monthly_backtest(
        conv_df,
        bench_df,
        top_n=top_n,
        rebalance_days=rebalance_days,
        weighting=weighting,
        trend_filter=trend_filter,
        gross_offtrend=gross_offtrend,
    )
    strategy_name = _strategy_name(weighting, trend_filter)

    if not periods:
        return BacktestResult(
            strategy_name=strategy_name,
            alpha_oos=0.0,
            port_annual_return=0.0,
            bench_annual_return=0.0,
            port_max_drawdown=0.0,
            bench_max_drawdown=0.0,
            hit_rate=0.0,
            information_ratio=0.0,
            alpha_t_stat=0.0,
            n_periods=0,
            n_trades=0,
            yearly=[],
        )

    pdf = pd.DataFrame(periods)
    port_eq = (1 + pdf["port_return"]).cumprod()
    bench_eq = (1 + pdf["bench_return"]).cumprod()
    port_dd = float(abs((port_eq / port_eq.cummax() - 1).min()))
    bench_dd = float(abs((bench_eq / bench_eq.cummax() - 1).min()))
    ann_port = float(port_eq.iloc[-1] ** (12 / len(pdf)) - 1)
    ann_bench = float(bench_eq.iloc[-1] ** (12 / len(pdf)) - 1)
    hit_rate = float((pdf["port_return"] > pdf["bench_return"]).mean())
    alpha_series = pdf["port_return"] - pdf["bench_return"]
    alpha_std = float(alpha_series.std())
    information_ratio = float(alpha_series.mean() / alpha_std) if alpha_std > 1e-9 else 0.0
    alpha_t_stat = float(np.sqrt(len(pdf)) * information_ratio)

    return BacktestResult(
        strategy_name=strategy_name,
        alpha_oos=ann_port - ann_bench,
        port_annual_return=ann_port,
        bench_annual_return=ann_bench,
        port_max_drawdown=port_dd,
        bench_max_drawdown=bench_dd,
        hit_rate=hit_rate,
        information_ratio=information_ratio,
        alpha_t_stat=alpha_t_stat,
        n_periods=len(pdf),
        n_trades=total_trades,
        yearly=_aggregate_yearly(periods),
    )
