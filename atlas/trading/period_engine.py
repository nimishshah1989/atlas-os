"""Per-window vectorbt simulation engine.

One function: run_window. Given prepared signal matrices and a date range,
build entry/exit masks via Layer 2 decision rules, run vbt.Portfolio,
extract per-window stats. Returns None when the window is too short to
simulate meaningfully (< 20 days).

Extracted from atlas/trading/simulator.py as part of Chunk 1.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import structlog

from atlas.trading.config import PortfolioConfig
from atlas.trading.decision import apply_entry_rules, apply_exit_rules
from atlas.trading.genome import Genome
from atlas.trading.perception import REGIME_RISK_OFF

log = structlog.get_logger()


def run_window(
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

    prev_rs = w_rs_exit[:, 0].copy()
    position_days = np.zeros(n_stocks, dtype=int)

    eff_heat = min(float(genome.layer1.genome_max_heat_pct), float(config.max_portfolio_heat_pct))
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
            curr_rs_state=w_rs_exit[:, d],
            holding_days=position_days,
            min_hold_days=playbook.min_hold_days,
            exit_rs_drop_tiers=playbook.exit_rs_drop_tiers,
            npc=w_npc[:, d],
            npc_overrides_min_hold=genome.layer1.npc_overrides_min_hold,
        )
        exits[d, :] = exit_mask
        position_days[exit_mask] = 0

        n_held = int((position_days > 0).sum())
        portfolio_heat = n_held * eff_pos

        entry_mask = apply_entry_rules(
            conviction=w_conv[:, d],
            regime=regime,
            portfolio_heat=portfolio_heat,
            genome=genome,
            max_portfolio_heat_pct=eff_heat,
            stage=w_stage[:, d],
        )
        new_entries = entry_mask & ~exit_mask

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
        held_before = position_days > 0
        position_days[held_before | new_entries] += 1
        daily_held_counts.append(int((position_days > 0).sum()))
        prev_rs = w_rs_exit[:, d].copy()

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
            sl_stop=stop_loss_frac,
            freq="D",
            group_by=True,
            cash_sharing=True,
        )

        def _scalar(v: object) -> float:
            if v is None:
                return 0.0
            try:
                f = float(v)  # type: ignore[arg-type]
                return 0.0 if (f != f) else f
            except (TypeError, ValueError):
                return 0.0

        sortino = _scalar(pf.sortino_ratio())
        calmar = _scalar(pf.calmar_ratio())
        max_dd = abs(_scalar(pf.max_drawdown()))
        trades = int(pf.trades.count() or 0)
        portfolio_return = _scalar(pf.total_return())

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
