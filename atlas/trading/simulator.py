"""vectorbt simulation harness: one genome -> SimResult across walk-forward windows.

Data flow:
  1. Pivot metrics into (n_stocks x n_days) numpy arrays
  2. Layer 1: derive state matrices via perception.py
  3. Layer 2: compute conviction matrix via decision.py
  4. Per walk-forward window: build entry/exit masks, run vbt.Portfolio, extract stats
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog

from atlas.trading.config import PortfolioConfig
from atlas.trading.decision import apply_entry_rules, apply_exit_rules, compute_conviction
from atlas.trading.genome import Genome
from atlas.trading.perception import (
    REGIME_RISK_OFF,
    compute_blended_rs_pctile,
    compute_rs_velocity,
    derive_momentum_state,
    derive_regime_state,
    derive_rs_exit_state,
    derive_rs_state,
    derive_vol_state,
)

log = structlog.get_logger()


@dataclass
class SimResult:
    """Per-genome simulation outcome aggregated across walk-forward windows.

    v2 (alpha + confidence) — aligned with the goal post: maximize alpha,
    minimize drawdown, minimize risk, with quantified confidence.

    Confidence semantics:
      - hit_rate: fraction of OOS windows where portfolio beat the benchmark
        (0.0–1.0). Higher = more regime-robust.
      - information_ratio: mean(alpha) / std(alpha). The standard quant-finance
        measure of risk-adjusted excess return. IR > 0.5 decent, > 1.0 good.
      - alpha_t_stat: sqrt(n_windows) * IR. T-statistic on the alpha series;
        used as a significance gate (> 2 ~= 95% confidence alpha is non-zero).
    """

    sortino_oos: float
    calmar_oos: float
    sortino_insample: float
    max_drawdown: float
    total_trades: int
    turnover_pct: float
    # v2 — alpha + confidence (goal-post-aligned metrics)
    alpha_oos: float = 0.0  # mean per-window alpha (portfolio return − benchmark return)
    benchmark_return_oos: float = 0.0  # mean per-window Nifty 500 return
    tracking_error: float = 0.0  # std-dev of per-window alpha
    information_ratio: float = 0.0  # alpha_oos / tracking_error
    hit_rate: float = 0.0  # % of windows where portfolio beat benchmark
    alpha_t_stat: float = 0.0  # sqrt(n_windows) * information_ratio
    # Core 4 — diversification realization. Tournament gates on this so optimizer
    # can't cheat by finding a "lucky 2-stock" genome that looks good statistically.
    avg_positions_held: float = 0.0
    equity_curve_oos: pd.Series | None = None


def _sanitize_close_adj(
    close: np.ndarray,
    instruments: list,
    dates: list,
    corp_actions: set[tuple[str, date]] | None = None,
    jump_threshold: float = 1.0,
) -> np.ndarray:
    """Drop stocks with close_adj corruption; preserve corp-action moves.

    Stocks with close_adj backfill bugs show scale-change discontinuities
    (one big jump UP that persists at the new scale). Forward-filling
    masked days creates a NEW discontinuity, so masking single days
    doesn't work. The clean approach: if a stock has ANY >100% one-day
    jump that isn't a recorded corp action, drop the whole stock from
    the universe (set its close row to NaN; vectorbt won't trade NaN).

    Tradeoff: loses ~14% of universe (~107 of 750 stocks). Remaining
    643 stocks have clean continuous price series. Better than feeding
    fake mega-returns to the optimizer.

    Fully vectorized: runs in ~50ms on 750x2600. Safe to call per-trial.
    Threshold 1.0 = 100% one-day move. 50% catches too many legitimate
    small-cap moves; 100% is rare without corp action.
    """
    sanitized = close.copy().astype(np.float64)
    n_stocks, n_days = sanitized.shape
    corp_actions = corp_actions or set()

    # One-day return ratios
    prev = np.empty_like(sanitized)
    prev[:, 0] = sanitized[:, 0]
    prev[:, 1:] = sanitized[:, :-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = sanitized / prev
    big_jumps = np.isfinite(ratios) & (prev > 0) & (np.abs(ratios - 1.0) > jump_threshold)

    # Build corp action mask via direct (iid, date) -> grid index lookups.
    has_ca = np.zeros_like(big_jumps, dtype=bool)
    iid_to_idx = {str(instruments[s]): s for s in range(n_stocks)}
    date_to_idx = {dates[d]: d for d in range(n_days)}
    for iid, dt in corp_actions:
        s = iid_to_idx.get(iid)
        d = date_to_idx.get(dt)
        if s is not None and d is not None:
            has_ca[s, d] = True
            if d + 1 < n_days:
                has_ca[s, d + 1] = True  # price drop may appear day-after

    suspect = big_jumps & ~has_ca
    # If a stock has ANY suspect day, drop it from the universe.
    bad_stock_mask = suspect.any(axis=1)
    bad_count = int(bad_stock_mask.sum())
    sanitized[bad_stock_mask, :] = np.nan

    if bad_count > 0:
        log.info(
            "close_adj_dropped_stocks",
            dropped=bad_count,
            of_total=n_stocks,
            drop_pct=round(100.0 * bad_count / max(1, n_stocks), 2),
            threshold=jump_threshold,
        )
    return sanitized.astype(np.float32)


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
    corp_actions: optional set of (instrument_id_str, ex_date) pairs from
                  de_corporate_actions. Exempts legitimate split/bonus drops
                  from the close_adj sanitizer. None = mask everything > 50%.
    """
    df = metrics_df.sort_values(["date", "instrument_id"])
    dates = sorted(df["date"].unique())
    instruments = sorted(df["instrument_id"].unique())

    def _pivot(col: str) -> np.ndarray:
        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return pivoted.reindex(index=instruments, columns=dates).values.astype(np.float32)

    def _safe_pivot(col: str, default: float) -> np.ndarray:
        """Pivot an optional column; fills with default when column is absent."""
        n_stocks_local = len(instruments)
        n_days_local = len(dates)
        if col not in df.columns:
            return np.full((n_stocks_local, n_days_local), default, dtype=np.float32)
        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return (
            pivoted.reindex(index=instruments, columns=dates)
            .fillna(default)
            .values.astype(np.float32)
        )

    close = _pivot("close")
    close = _sanitize_close_adj(close, instruments, dates, corp_actions)
    n_stocks, n_days = close.shape

    # CRITICAL: rs_pctile_1w/1m/3m are stored 0-1 in atlas_stock_metrics_daily
    # but genome thresholds (rs_leader_cutoff_pct=60-80, etc.) and the
    # /100 normalization inside compute_conviction both assume 0-100 scale.
    # Scale here so the rest of the pipeline is consistent.
    rs_arrays = {
        "1w": _pivot("rs_pctile_1w") * 100.0,
        "1m": _pivot("rs_pctile_1m") * 100.0,
        "3m": _pivot("rs_pctile_3m") * 100.0,
    }
    vol_ratio = _pivot("vol_ratio_63")
    ema_ratio = _pivot("ema_20_ratio")

    rdf = regime_df.set_index("date").reindex(dates)
    # Same scale fix for breadth: stored 0-1 but compared against 0-100 thresholds.
    breadth = rdf["pct_above_ema_50"].values.astype(np.float32) * 100.0
    vix_arr = rdf["india_vix"].values.astype(np.float32)  # absolute scale, no fix needed
    # Benchmark price series for alpha computation. ffill is intentional —
    # on a non-trading day Nifty 500 doesn't move, so carrying forward the
    # last close is correct (vs leaving NaN and breaking the alpha calc).
    nifty500_close_arr = (
        np.asarray(rdf["nifty500_close"].astype(np.float64).ffill().values, dtype=np.float64)
        if "nifty500_close" in rdf.columns
        else np.full(len(dates), np.nan, dtype=np.float64)
    )

    # CTS stage signals (default: Stage 2 = neutral, no PPC/NPC/contraction)
    cts_stage = _safe_pivot("cts_stage", default=2.0).astype(np.int8)
    ppc = _safe_pivot("ppc", default=0.0).astype(np.int8)
    npc_arr = _safe_pivot("npc", default=0.0).astype(np.int8)
    contraction = _safe_pivot("contraction", default=0.0).astype(np.int8)

    # Layer 1: state matrices computed once for all windows
    blended_rs = compute_blended_rs_pctile(rs_arrays, genome.layer1.rs_timeframe_weights)
    rs_state = derive_rs_state(blended_rs, genome.layer1)
    rs_exit_state = derive_rs_exit_state(blended_rs, genome.layer1)
    regime_state = derive_regime_state(breadth, vix_arr, genome.layer1)
    vol_state = derive_vol_state(vol_ratio, genome.layer1)
    mom_state = derive_momentum_state(ema_ratio, genome.layer1)
    days_in_state, direction = compute_rs_velocity(
        rs_state, genome.layer1.state_velocity_lookback_days
    )

    # Layer 2: conviction matrix
    conv_matrix = np.zeros((n_stocks, n_days), dtype=np.float32)
    for s in range(n_stocks):
        for d in range(n_days):
            if np.isnan(blended_rs[s, d]):
                continue
            conv_matrix[s, d] = compute_conviction(
                rs_pctile_norm=float(blended_rs[s, d]) / 100.0,
                rs_state=int(rs_state[s, d]),
                momentum_state=int(mom_state[s, d]),
                vol_state=int(vol_state[s, d]),
                days_in_state=int(days_in_state[s, d]),
                direction=int(direction[s, d]),
                layer1=genome.layer1,
                ppc=int(ppc[s, d]),
                contraction=int(contraction[s, d]),
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
        oos = _run_window(
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
        isn = _run_window(
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

    # v2 confidence aggregation. Hit rate + IR + t-stat are the standard
    # quant-finance triple for "how confident are we this alpha is real?"
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
        equity_curve_oos=None,  # populated by incubator when equity curve storage is needed
    )


def _run_window(
    genome: Genome,
    config: PortfolioConfig,
    dates: list,
    close: np.ndarray,
    conv_matrix: np.ndarray,
    rs_exit_state: np.ndarray,
    regime_state: np.ndarray,
    cts_stage: np.ndarray,
    npc: np.ndarray,
    nifty500_close_arr: np.ndarray,
    window_start: date,
    window_end: date,
    instruments: list,
) -> dict | None:
    """Simulate one walk-forward window. Returns None if window < 20 days.

    Computes per-window alpha = portfolio_return − Nifty 500 return so the
    incubator can aggregate hit rate + IR + t-stat across windows.
    """
    import vectorbt as vbt

    d_start = next((i for i, d in enumerate(dates) if d >= window_start), None)
    d_end = next((i for i, d in enumerate(dates) if d > window_end), len(dates))
    if d_start is None or d_end - d_start < 20:
        return None

    w_dates = dates[d_start:d_end]
    w_close = close[:, d_start:d_end]
    w_conv = conv_matrix[:, d_start:d_end]
    w_rs_exit = rs_exit_state[:, d_start:d_end]
    w_regime = regime_state[d_start:d_end]
    w_stage = cts_stage[:, d_start:d_end]
    w_npc = npc[:, d_start:d_end]
    w_n500 = nifty500_close_arr[d_start:d_end]

    n_stocks, n_days = w_close.shape
    entries = np.zeros((n_days, n_stocks), dtype=bool)
    exits = np.zeros((n_days, n_stocks), dtype=bool)

    # Track exit state for continuity (hysteresis)
    prev_rs = w_rs_exit[:, 0].copy()
    position_days = np.zeros(n_stocks, dtype=int)

    eff_heat = min(float(genome.layer1.genome_max_heat_pct), float(config.max_portfolio_heat_pct))
    # Core 4 risk-parity sizing: position size scales with stop distance.
    # If 1% risk + 10% stop, position = 10% of portfolio. Capped at hard limits.
    # When stop is tight, position grows; when stop is wide, position shrinks.
    risk_parity_size = float(genome.layer1.risk_per_trade_pct) / max(
        float(genome.layer1.stop_loss_pct), 0.001
    )
    eff_pos = min(
        risk_parity_size,
        float(genome.layer1.genome_max_position_pct),
        float(config.max_position_pct),
    )
    max_concurrent = int(genome.layer1.max_concurrent_positions)
    stop_loss_frac = float(genome.layer1.stop_loss_pct)

    # Track positions held per day so the aggregator can compute avg_positions_held —
    # tournament gate enforces diversification floor via this stat.
    daily_held_counts: list[int] = []

    for d in range(1, n_days):
        regime = int(w_regime[d])
        if regime == REGIME_RISK_OFF:
            exits[d, :] = True
            position_days[:] = 0
            prev_rs = w_rs_exit[:, d].copy()
            continue

        playbook = (
            genome.risk_on
            if regime == 3
            else (genome.constructive if regime == 2 else genome.cautious)
        )

        exit_mask = apply_exit_rules(
            prev_rs_state=prev_rs,
            curr_rs_state=w_rs_exit[:, d],  # exit state uses hysteresis thresholds
            holding_days=position_days,
            min_hold_days=playbook.min_hold_days,
            exit_rs_drop_tiers=playbook.exit_rs_drop_tiers,
            npc=w_npc[:, d],
            npc_overrides_min_hold=genome.layer1.npc_overrides_min_hold,
        )
        exits[d, :] = exit_mask
        position_days[exit_mask] = 0

        n_held = int((position_days > 0).sum())
        portfolio_heat = n_held * eff_pos  # upper-bound approx — assumes full fills at eff_pos

        entry_mask = apply_entry_rules(
            conviction=w_conv[:, d],
            regime=regime,
            portfolio_heat=portfolio_heat,
            genome=genome,
            max_portfolio_heat_pct=eff_heat,
            stage=w_stage[:, d],
        )
        new_entries = entry_mask & ~exit_mask

        # Core 4 max-position gate: cap new entries so total holdings <= max_concurrent.
        # When more candidates than capacity, keep top-K by conviction (the model's own
        # ranking). When capacity <= 0, no new entries today regardless of signals.
        capacity = max_concurrent - n_held
        if capacity < int(new_entries.sum()):
            if capacity <= 0:
                new_entries = np.zeros_like(new_entries)
            else:
                candidate_idx = np.where(new_entries)[0]
                top_k = candidate_idx[np.argsort(-w_conv[candidate_idx, d])[:capacity]]
                new_entries = np.zeros_like(new_entries)
                new_entries[top_k] = True

        entries[d, :] = new_entries
        # Increment holding days for all currently-held positions (including new entries today)
        held_before = position_days > 0
        position_days[held_before | new_entries] += 1
        daily_held_counts.append(int((position_days > 0).sum()))
        prev_rs = w_rs_exit[:, d].copy()  # track exit state for next day's comparison

    price_df = pd.DataFrame(
        w_close.T,
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in w_dates]),
        columns=pd.Index([str(iid) for iid in instruments]),
    )
    entries_df = pd.DataFrame(entries, index=price_df.index, columns=price_df.columns)
    exits_df = pd.DataFrame(exits, index=price_df.index, columns=price_df.columns)

    try:
        # Decimal arithmetic executes first (precise); float() is a single
        # conversion required by vectorbt's numpy internals. Fee rates are
        # ≤0.1% each so the float representation is exact to 17 digits.
        total_fees = float(
            config.brokerage_rate
            + config.stt_rate_sell
            + config.exchange_charge_rate
            + config.sebi_charge_rate
        )
        pf = vbt.Portfolio.from_signals(
            price_df,
            entries_df,
            exits_df,
            init_cash=float(config.starting_capital),
            fees=total_fees,
            size=eff_pos,
            size_type="Percent",
            sl_stop=stop_loss_frac,  # Core 4 stop-loss exit (vectorbt-native)
            # vectorbt 1.0 requires explicit freq on the index when it isn't set;
            # walk-forward windows are trading days with weekend gaps, so we
            # declare daily frequency. Without this, Portfolio.from_signals
            # raises "Index frequency is None" on every window.
            freq="D",
            group_by=True,
            cash_sharing=True,
        )

        def _scalar(v: object) -> float:
            """Extract a Python float from a vectorbt scalar, Series, or array."""
            if v is None:
                return 0.0
            try:
                f = float(v)  # type: ignore[arg-type]
                return 0.0 if (f != f) else f  # NaN -> 0.0
            except (TypeError, ValueError):
                return 0.0

        sortino = _scalar(pf.sortino_ratio())
        calmar = _scalar(pf.calmar_ratio())
        # vectorbt returns max_drawdown as a negative fraction (e.g. -0.22 for
        # 22% drawdown). Tournament gates compare against positive thresholds
        # (STRESS_COVID_MAX_DRAWDOWN = 0.25). Convert to absolute magnitude so
        # the aggregator's np.max correctly picks the WORST window — without
        # the abs, np.max selects the LEAST negative (closest to zero, often
        # a zero-trade window) and the COVID gate would never trigger.
        max_dd = abs(_scalar(pf.max_drawdown()))
        trades = int(pf.trades.count() or 0)
        portfolio_return = _scalar(pf.total_return())

        # Benchmark return: simple start-to-end, NaN-safe. ffill in
        # simulate_genome guarantees no NaN inside the window, but we still
        # defend against an all-NaN window (e.g. early-history regime gaps).
        if (
            len(w_n500) >= 2
            and not np.isnan(w_n500[0])
            and not np.isnan(w_n500[-1])
            and w_n500[0] > 0
        ):
            benchmark_return = float(w_n500[-1] / w_n500[0] - 1.0)
        else:
            benchmark_return = 0.0
        alpha = portfolio_return - benchmark_return

        avg_positions_held = float(np.mean(daily_held_counts)) if daily_held_counts else 0.0
        return {
            "sortino": sortino,
            "calmar": calmar,
            "max_drawdown": max_dd,
            "trades": trades,
            "portfolio_return": portfolio_return,
            "benchmark_return": benchmark_return,
            "alpha": alpha,
            "avg_positions_held": avg_positions_held,
        }
    except Exception as e:
        log.warning("simulation_window_error", error=str(e))
        return None
