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
    sortino_oos: float
    calmar_oos: float
    sortino_insample: float
    max_drawdown: float
    total_trades: int
    turnover_pct: float
    equity_curve_oos: pd.Series | None = None


def simulate_genome(
    genome: Genome,
    metrics_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    config: PortfolioConfig,
    walk_forward_windows: list[tuple[date, date, date, date]],
) -> SimResult:
    """Run genome across walk-forward windows, return averaged OOS metrics.

    metrics_df: instrument_id, date, close, rs_pctile_1w, rs_pctile_1m,
                rs_pctile_3m, vol_ratio_63, ema_20_ratio
    regime_df:  date, pct_above_ema_50, india_vix
    walk_forward_windows: list of (train_start, train_end, test_start, test_end)
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
    n_stocks, n_days = close.shape

    rs_arrays = {
        "1w": _pivot("rs_pctile_1w"),
        "1m": _pivot("rs_pctile_1m"),
        "3m": _pivot("rs_pctile_3m"),
    }
    vol_ratio = _pivot("vol_ratio_63")
    ema_ratio = _pivot("ema_20_ratio")

    rdf = regime_df.set_index("date").reindex(dates)
    breadth = rdf["pct_above_ema_50"].values.astype(np.float32)
    vix_arr = rdf["india_vix"].values.astype(np.float32)

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
    insample_sortinos: list[float] = []
    all_trades = 0

    for train_start, train_end, test_start, test_end in walk_forward_windows:
        oos = _run_window(
            genome,
            config,
            dates,
            close,
            conv_matrix,
            rs_state,
            rs_exit_state,
            regime_state,
            cts_stage,
            ppc,
            npc_arr,
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
            rs_state,
            rs_exit_state,
            regime_state,
            cts_stage,
            ppc,
            npc_arr,
            train_start,
            train_end,
            instruments,
        )
        if oos is not None:
            oos_sortinos.append(oos["sortino"])
            oos_calmars.append(oos["calmar"])
            oos_max_drawdowns.append(oos["max_drawdown"])
            all_trades += oos["trades"]
        if isn is not None:
            insample_sortinos.append(isn["sortino"])

    return SimResult(
        sortino_oos=float(np.mean(oos_sortinos)) if oos_sortinos else 0.0,
        calmar_oos=float(np.mean(oos_calmars)) if oos_calmars else 0.0,
        sortino_insample=float(np.mean(insample_sortinos)) if insample_sortinos else 0.0,
        max_drawdown=float(np.max(oos_max_drawdowns)) if oos_max_drawdowns else 0.0,
        total_trades=all_trades,
        turnover_pct=0.0,
        equity_curve_oos=None,  # populated by incubator when equity curve storage is needed
    )


def _run_window(
    genome: Genome,
    config: PortfolioConfig,
    dates: list,
    close: np.ndarray,
    conv_matrix: np.ndarray,
    rs_state: np.ndarray,
    rs_exit_state: np.ndarray,
    regime_state: np.ndarray,
    cts_stage: np.ndarray,
    ppc: np.ndarray,
    npc: np.ndarray,
    window_start: date,
    window_end: date,
    instruments: list,
) -> dict | None:
    """Simulate one walk-forward window. Returns None if window < 20 days."""
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

    n_stocks, n_days = w_close.shape
    entries = np.zeros((n_days, n_stocks), dtype=bool)
    exits = np.zeros((n_days, n_stocks), dtype=bool)

    # Track exit state for continuity (hysteresis)
    prev_rs = w_rs_exit[:, 0].copy()
    position_days = np.zeros(n_stocks, dtype=int)

    eff_heat = min(float(genome.layer1.genome_max_heat_pct), float(config.max_portfolio_heat_pct))
    eff_pos = min(float(genome.layer1.genome_max_position_pct), float(config.max_position_pct))

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
        entries[d, :] = new_entries
        # Increment holding days for all currently-held positions (including new entries today)
        held_before = position_days > 0
        position_days[held_before | new_entries] += 1
        prev_rs = w_rs_exit[:, d].copy()  # track exit state for next day's comparison

    price_df = pd.DataFrame(
        w_close.T,
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in w_dates]),
        columns=pd.Index([str(iid) for iid in instruments]),
    )
    entries_df = pd.DataFrame(entries, index=price_df.index, columns=price_df.columns)
    exits_df = pd.DataFrame(exits, index=price_df.index, columns=price_df.columns)

    try:
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
        max_dd = _scalar(pf.max_drawdown())
        trades = int(pf.trades.count() or 0)
        return {"sortino": sortino, "calmar": calmar, "max_drawdown": max_dd, "trades": trades}
    except Exception as e:
        log.warning("simulation_window_error", error=str(e))
        return None
