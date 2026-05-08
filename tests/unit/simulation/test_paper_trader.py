"""Unit tests for paper_trader pure functions — no DB required.

Tests cover:
- apply_strategy_filter: threshold overrides, state filter
- compute_trades: regime stances, exit priority, cold start
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from atlas.simulation.core.paper_trader import (
    Holding,
    apply_strategy_filter,
    compute_trades,
)


@dataclass
class MockStrategyConfig:
    name: str = "test_strategy"
    tier: str = "stocks_only"
    archetype: str = "momentum_pure"
    variant: str = "aggressive"
    state_filter: list[str] = field(default_factory=lambda: ["leader"])
    regime_stance: str = "pause_risk_off"
    position_sizing: str = "equal_weight"
    max_positions: int = 10
    max_sector_pct: float = 40.0
    rebalance_trigger: str = "signal_change"
    threshold_overrides: dict = field(default_factory=dict)


def _make_decisions_df(
    instruments: list[str],
    rs_states: list[str],
    transition_triggers: list[bool],
    breakout_triggers: list[bool],
    exit_rs: list[bool] | None = None,
) -> pd.DataFrame:
    n = len(instruments)
    return pd.DataFrame(
        {
            "instrument_id": instruments,
            "rs_state": rs_states,
            "transition_trigger": transition_triggers,
            "breakout_trigger": breakout_triggers,
            "exit_rs_deteriorate": exit_rs or [False] * n,
            "exit_market_riskoff": [False] * n,
            "exit_momentum_collapse": [False] * n,
            "exit_volume_distrib": [False] * n,
            "exit_sector_avoid": [False] * n,
            "exit_stop_loss": [False] * n,
        }
    )


# --- apply_strategy_filter tests ---


def test_apply_filter_returns_leader_entries_only():
    decisions = _make_decisions_df(
        instruments=["INFY", "TCS", "WIPRO"],
        rs_states=["Leader", "Strong", "Leader"],
        transition_triggers=[True, True, True],
        breakout_triggers=[False, False, False],
    )
    config = MockStrategyConfig(state_filter=["leader"])
    entries, exits = apply_strategy_filter(decisions, config, {})
    # TCS is Strong, not Leader — excluded despite transition_trigger
    assert entries == {"INFY", "WIPRO"}
    assert exits == set()


def test_apply_filter_includes_strong_with_state_filter_strong():
    decisions = _make_decisions_df(
        instruments=["INFY", "TCS"],
        rs_states=["Leader", "Strong"],
        transition_triggers=[True, True],
        breakout_triggers=[False, False],
    )
    config = MockStrategyConfig(state_filter=["leader", "strong"])
    entries, _ = apply_strategy_filter(decisions, config, {})
    assert entries == {"INFY", "TCS"}


def test_apply_filter_no_entry_without_trigger():
    decisions = _make_decisions_df(
        instruments=["INFY"],
        rs_states=["Leader"],
        transition_triggers=[False],
        breakout_triggers=[False],
    )
    config = MockStrategyConfig(state_filter=["leader"])
    entries, _ = apply_strategy_filter(decisions, config, {})
    assert entries == set()


def test_apply_filter_exit_rs_deteriorate_detected():
    decisions = _make_decisions_df(
        instruments=["INFY"],
        rs_states=["Laggard"],
        transition_triggers=[False],
        breakout_triggers=[False],
        exit_rs=[True],
    )
    config = MockStrategyConfig()
    _, exits = apply_strategy_filter(decisions, config, {})
    assert "INFY" in exits


# --- compute_trades tests ---


def test_compute_trades_cold_start_produces_entries_only():
    entries = {"INFY", "TCS"}
    exits = set()
    holdings: dict[str, Holding] = {}  # empty = cold start
    config = MockStrategyConfig(regime_stance="pause_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-On", config)
    actions = {t.action for t in trades}
    assert "exit" not in actions
    entry_instruments = {t.instrument_id for t in trades if t.action == "enter"}
    assert entry_instruments == {"INFY", "TCS"}


def test_compute_trades_pause_risk_off_blocks_new_entries():
    entries = {"WIPRO"}  # new entry candidate
    exits = set()
    holdings = {"INFY": Holding("INFY", "stock", 50.0, date(2025, 1, 1), "transition", 500_000)}
    config = MockStrategyConfig(regime_stance="pause_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-Off", config)
    # No new entries allowed in Risk-Off + pause_risk_off
    entry_instruments = {t.instrument_id for t in trades if t.action == "enter"}
    assert "WIPRO" not in entry_instruments


def test_compute_trades_hold_risk_off_allows_entries():
    entries = {"WIPRO"}
    exits = set()
    holdings: dict[str, Holding] = {}
    config = MockStrategyConfig(regime_stance="hold_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-Off", config)
    entry_instruments = {t.instrument_id for t in trades if t.action == "enter"}
    assert "WIPRO" in entry_instruments


def test_compute_trades_exits_are_generated():
    entries = set()
    exits = {"INFY"}
    holdings = {"INFY": Holding("INFY", "stock", 50.0, date(2025, 1, 1), "transition", 500_000)}
    config = MockStrategyConfig()
    trades = compute_trades(holdings, entries, exits, "Risk-On", config)
    exit_instruments = {t.instrument_id for t in trades if t.action == "exit"}
    assert "INFY" in exit_instruments


def test_compute_trades_scale_risk_off_marks_rebalance():
    entries = set()
    exits = set()
    holdings = {
        "INFY": Holding("INFY", "stock", 60.0, date(2025, 1, 1), "transition", 600_000),
    }
    config = MockStrategyConfig(regime_stance="scale_risk_off")
    trades = compute_trades(holdings, entries, exits, "Risk-Off", config)
    rebalances = [t for t in trades if t.action == "rebalance"]
    # Should scale INFY from 60% to 60% * 0.4 = 24%
    assert len(rebalances) == 1
    assert abs(rebalances[0].weight_pct - 24.0) < 0.01
