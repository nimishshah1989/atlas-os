"""vectorbt simulation harness: one genome -> SimResult across walk-forward windows.

Data flow:
  1. data_loader.pivot_metrics + signal computation → (n_stocks, n_days) arrays
  2. Layer 1: derive state matrices via perception.py
  3. Layer 2: compute conviction matrix via decision.py
  4. period_engine.run_window for each walk-forward window → vbt.Portfolio stats
  5. Aggregate per-window stats into SimResult

Post Chunk 1 (eng-review scope reduction): heavy logic split into
data_loader.py (pivot + signals + sanitize) and period_engine.py (vectorbt
window simulation). This file is the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog

from atlas.trading.config import PortfolioConfig
from atlas.trading.data_loader import (
    compute_beta_alpha_63d,
    compute_mom_low_vol,
    compute_natr_14,
    pivot_metrics,
    sanitize_close_adj,
)
from atlas.trading.decision import compute_conviction_matrix
from atlas.trading.genome import Genome
from atlas.trading.perception import (
    compute_blended_rs_pctile,
    derive_regime_state,
    derive_rs_exit_state,
)
from atlas.trading.period_engine import run_window

log = structlog.get_logger()


@dataclass
class SimResult:
    """Per-genome simulation outcome aggregated across walk-forward windows.

    v2 (alpha + confidence) — aligned with the goal post: maximize alpha,
    minimize drawdown, minimize risk, with quantified confidence.

    Confidence semantics:
      - hit_rate: fraction of OOS windows where portfolio beat the benchmark.
      - information_ratio: mean(alpha) / std(alpha).
      - alpha_t_stat: sqrt(n_windows) * IR; significance gate (> 2 ~= 95% conf).
    """

    sortino_oos: float
    calmar_oos: float
    sortino_insample: float
    max_drawdown: float
    total_trades: int
    turnover_pct: float
    alpha_oos: float = 0.0
    benchmark_return_oos: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    hit_rate: float = 0.0
    alpha_t_stat: float = 0.0
    avg_positions_held: float = 0.0
    equity_curve_oos: pd.Series | None = None


def simulate_genome(
    genome: Genome,
    metrics_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    config: PortfolioConfig,
    walk_forward_windows: list[tuple[date, date, date, date]],
    corp_actions: set[tuple[str, date]] | None = None,
) -> SimResult:
    """Run genome across walk-forward windows, return averaged OOS metrics.

    metrics_df: instrument_id, date, close, rs_pctile_1w, rs_pctile_1m,
                rs_pctile_3m, vol_ratio_63, ema_20_ratio
    regime_df:  date, pct_above_ema_50, india_vix
    walk_forward_windows: list of (train_start, train_end, test_start, test_end)
    corp_actions: optional set of (instrument_id_str, ex_date) pairs.
    """
    df = metrics_df.sort_values(["date", "instrument_id"])
    dates = sorted(df["date"].unique())
    instruments = sorted(df["instrument_id"].unique())

    arrays = pivot_metrics(df, instruments, dates)
    close = sanitize_close_adj(arrays["close"], instruments, dates, corp_actions)

    rs_arrays = {
        "1w": arrays["rs_1w"],
        "1m": arrays["rs_1m"],
        "3m": arrays["rs_3m"],
    }

    rdf = regime_df.set_index("date").reindex(dates)
    breadth = rdf["pct_above_ema_50"].values.astype(np.float32) * 100.0
    vix_arr = rdf["india_vix"].values.astype(np.float32)
    nifty500_close_arr = (
        np.asarray(rdf["nifty500_close"].astype(np.float64).ffill().values, dtype=np.float64)
        if "nifty500_close" in rdf.columns
        else np.full(len(dates), np.nan, dtype=np.float64)
    )

    cts_stage = arrays["cts_stage"]
    npc_arr = arrays["npc"]

    # v5 signals computed once for all windows
    natr_14_arr = compute_natr_14(arrays["high"], arrays["low"], close)
    beta_alpha_63d_arr = compute_beta_alpha_63d(close, nifty500_close_arr)
    mom_low_vol_arr = compute_mom_low_vol(arrays["ret_12m"], arrays["realized_vol_63"])

    # Layer 1: rs_exit_state (only state still consumed by run_window) + regime_state.
    # v5 conviction is signal-driven; v4 state matrices (rs/vol/mom/velocity) are
    # no longer required to compute the conviction matrix and have been removed.
    blended_rs = compute_blended_rs_pctile(rs_arrays, genome.layer1.rs_timeframe_weights)
    rs_exit_state = derive_rs_exit_state(blended_rs, genome.layer1)
    regime_state = derive_regime_state(breadth, vix_arr, genome.layer1)

    # Layer 2: v5 conviction (3 alphalens-monotonic OOS-robust signals)
    conv_matrix = compute_conviction_matrix(
        natr_14=natr_14_arr,
        beta_alpha_63d=beta_alpha_63d_arr,
        mom_low_vol=mom_low_vol_arr,
        layer1=genome.layer1,
    )

    oos_sortinos: list[float] = []
    oos_calmars: list[float] = []
    oos_max_drawdowns: list[float] = []
    oos_alphas: list[float] = []
    oos_portfolio_returns: list[float] = []
    oos_benchmark_returns: list[float] = []
    oos_avg_positions: list[float] = []
    insample_sortinos: list[float] = []
    all_trades = 0

    for train_start, train_end, test_start, test_end in walk_forward_windows:
        oos = run_window(
            genome,
            config,
            dates,
            close,
            conv_matrix,
            rs_exit_state,
            regime_state,
            cts_stage,
            npc_arr,
            nifty500_close_arr,
            test_start,
            test_end,
            instruments,
        )
        isn = run_window(
            genome,
            config,
            dates,
            close,
            conv_matrix,
            rs_exit_state,
            regime_state,
            cts_stage,
            npc_arr,
            nifty500_close_arr,
            train_start,
            train_end,
            instruments,
        )
        if oos is not None:
            oos_sortinos.append(oos["sortino"])
            oos_calmars.append(oos["calmar"])
            oos_max_drawdowns.append(oos["max_drawdown"])
            oos_alphas.append(oos["alpha"])
            oos_portfolio_returns.append(oos["portfolio_return"])
            oos_benchmark_returns.append(oos["benchmark_return"])
            oos_avg_positions.append(oos["avg_positions_held"])
            all_trades += oos["trades"]
        if isn is not None:
            insample_sortinos.append(isn["sortino"])

    alpha_mean = float(np.mean(oos_alphas)) if oos_alphas else 0.0
    alpha_std = float(np.std(oos_alphas, ddof=1)) if len(oos_alphas) > 1 else 0.0
    hit_rate = float(sum(1 for a in oos_alphas if a > 0)) / len(oos_alphas) if oos_alphas else 0.0
    information_ratio = alpha_mean / alpha_std if alpha_std > 1e-9 else 0.0
    alpha_t_stat = float(np.sqrt(len(oos_alphas))) * information_ratio if oos_alphas else 0.0
    benchmark_mean = float(np.mean(oos_benchmark_returns)) if oos_benchmark_returns else 0.0

    return SimResult(
        sortino_oos=float(np.mean(oos_sortinos)) if oos_sortinos else 0.0,
        calmar_oos=float(np.mean(oos_calmars)) if oos_calmars else 0.0,
        sortino_insample=float(np.mean(insample_sortinos)) if insample_sortinos else 0.0,
        max_drawdown=float(np.max(oos_max_drawdowns)) if oos_max_drawdowns else 0.0,
        total_trades=all_trades,
        turnover_pct=0.0,
        alpha_oos=alpha_mean,
        benchmark_return_oos=benchmark_mean,
        tracking_error=alpha_std,
        information_ratio=information_ratio,
        hit_rate=hit_rate,
        alpha_t_stat=alpha_t_stat,
        avg_positions_held=float(np.mean(oos_avg_positions)) if oos_avg_positions else 0.0,
        equity_curve_oos=None,
    )
