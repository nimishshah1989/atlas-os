"""Paper trading state machine — sync, psycopg2-backed.

Pure functions (apply_strategy_filter, compute_trades) have no DB calls
and are the primary unit-test targets. DB functions (fetch_decisions,
write_trades, etc.) are called by runner.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from atlas.compute._session import bulk_upsert, open_compute_session

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

_RISK_OFF_SCALE = 0.4


@dataclass
class Holding:
    instrument_id: str
    instrument_type: str
    weight_pct: float
    entry_date: date
    entry_signal_type: str
    notional_value: float


@dataclass
class Trade:
    instrument_id: str
    instrument_type: str
    action: str  # enter | exit | rebalance
    signal_type: str
    weight_pct: float
    notional_value: float


class _PaperTraderConfig(Protocol):
    """Structural type for configs accepted by apply_strategy_filter / compute_trades.

    Both BacktestConfig (defined here) and StrategyConfig (from loader.py)
    satisfy this Protocol structurally — no import coupling needed.
    """

    state_filter: list[str]
    regime_stance: str
    max_positions: int


@dataclass
class BacktestConfig:
    """Minimal config for paper_trader pure functions in backtest contexts."""

    regime_stance: str = "pause_risk_off"
    max_positions: int = 20
    state_filter: list[str] = field(default_factory=lambda: ["leader"])


class MissingAtlasDecisionsError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Pure functions — testable without DB
# ---------------------------------------------------------------------------

_STATE_FILTER_MAP = {
    "leader": {"Leader"},
    "strong": {"Leader", "Strong"},
    "emerging": {"Leader", "Strong", "Emerging"},
    "investable": None,  # None = accept any rs_state when is_investable=TRUE
}

_EXIT_COLUMNS = [
    "exit_market_riskoff",
    "exit_rs_deteriorate",
    "exit_momentum_collapse",
    "exit_volume_distrib",
    "exit_sector_avoid",
    "exit_stop_loss",
]


def apply_strategy_filter(
    decisions: pd.DataFrame,
    config: _PaperTraderConfig,
    threshold_overrides: dict[str, float],
) -> tuple[set[str], set[str]]:
    """Pure function: decisions DataFrame + config -> (entry_set, exit_set).

    No DB calls. Applies state_filter and entry trigger logic in-memory.
    threshold_overrides are applied by runner.py before calling this function.
    """
    _ = threshold_overrides  # runner.py applies overrides before this call
    entry_set: set[str] = set()
    exit_set: set[str] = set()

    allowed_states: set[str] | None = set()
    for sf in config.state_filter:
        mapped = _STATE_FILTER_MAP.get(sf.lower())
        if mapped is None:
            allowed_states = None  # investable = any state
            break
        allowed_states |= mapped  # type: ignore[operator]

    for row in decisions.itertuples(index=False):
        instrument_id: str = row.instrument_id  # pyright: ignore[reportAttributeAccessIssue]

        # Check exits first (highest priority)
        for col in _EXIT_COLUMNS:
            if getattr(row, col, False):
                exit_set.add(instrument_id)
                break

        if instrument_id in exit_set:
            continue

        # Check entry conditions
        has_trigger = getattr(row, "transition_trigger", False) or getattr(
            row, "breakout_trigger", False
        )
        if not has_trigger:
            has_trigger = getattr(row, "entry_trigger", False)

        if not has_trigger:
            continue

        rs_state = getattr(row, "rs_state", "")
        if allowed_states is None or rs_state in allowed_states:
            entry_set.add(instrument_id)

    return entry_set, exit_set


def compute_trades(
    current_holdings: dict[str, Holding],
    entries: set[str],
    exits: set[str],
    regime: str,
    config: _PaperTraderConfig,
) -> list[Trade]:
    """Pure function: holdings + signals + regime -> trade list.

    Applies regime_stance logic:
    - pause_risk_off: block new entries in Risk-Off; allow exits
    - scale_risk_off: scale all holdings by 0.4x in Risk-Off; rebalance trades
    - hold_risk_off: no behavior change
    """
    trades: list[Trade] = []
    is_risk_off = regime == "Risk-Off"
    regime_stance = config.regime_stance
    max_positions = config.max_positions

    # 1. Exit trades
    for inst_id in exits:
        if inst_id in current_holdings:
            h = current_holdings[inst_id]
            trades.append(
                Trade(
                    instrument_id=inst_id,
                    instrument_type=h.instrument_type,
                    action="exit",
                    signal_type="exit_signal",
                    weight_pct=0.0,
                    notional_value=0.0,
                )
            )

    # 2. Rebalance for scale_risk_off
    if is_risk_off and regime_stance == "scale_risk_off":
        for inst_id, h in current_holdings.items():
            if inst_id in exits:
                continue
            scaled_weight = h.weight_pct * _RISK_OFF_SCALE
            if abs(scaled_weight - h.weight_pct) > 0.01:
                trades.append(
                    Trade(
                        instrument_id=inst_id,
                        instrument_type=h.instrument_type,
                        action="rebalance",
                        signal_type="regime_scale",
                        weight_pct=scaled_weight,
                        notional_value=h.notional_value * _RISK_OFF_SCALE,
                    )
                )

    # 3. New entry trades
    if is_risk_off and regime_stance == "pause_risk_off":
        return trades  # Block all new entries

    new_entries = entries - set(current_holdings.keys()) - exits
    if len(current_holdings) + len(new_entries) > max_positions:
        new_entries = set(list(new_entries)[: max_positions - len(current_holdings)])

    equal_weight = 100.0 / max(len(new_entries) + len(current_holdings), 1)
    for inst_id in new_entries:
        trades.append(
            Trade(
                instrument_id=inst_id,
                instrument_type="stock",
                action="enter",
                signal_type="entry_signal",
                weight_pct=equal_weight,
                notional_value=equal_weight * 100_000,
            )
        )

    return trades


# ---------------------------------------------------------------------------
# DB functions — called by runner.py
# ---------------------------------------------------------------------------


def fetch_decisions(conn: Connection, tier: str, today: date) -> pd.DataFrame:
    """Load full decision universe for one tier on today. One DB call.

    Args:
        tier: 'stocks' | 'etf' | 'fund'
        today: the date to load decisions for
    """
    table_map = {
        "stocks": "atlas_stock_decisions_daily",
        "etf": "atlas_etf_decisions_daily",
        "fund": "atlas_fund_decisions_daily",
    }
    if tier not in table_map:
        raise ValueError(f"Unknown tier: {tier}. Must be stocks | etf | fund")

    table = table_map[tier]

    if tier == "stocks":
        query = text(f"""
            SELECT d.instrument_id::text AS instrument_id, s.rs_state,
                   d.transition_trigger, d.breakout_trigger,
                   d.exit_market_riskoff, d.exit_rs_deteriorate,
                   d.exit_momentum_collapse, d.exit_volume_distrib,
                   d.exit_sector_avoid, d.exit_stop_loss
            FROM atlas.{table} d
            JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = d.instrument_id AND s.date = d.date
            WHERE d.date = :today
        """)
    elif tier == "etf":
        query = text("""
            SELECT d.ticker AS instrument_id, s.rs_state,
                   d.transition_trigger, d.breakout_trigger,
                   d.exit_market_riskoff, d.exit_rs_deteriorate,
                   d.exit_momentum_collapse, d.exit_sector_avoid, d.exit_stop_loss
            FROM atlas.atlas_etf_decisions_daily d
            JOIN atlas.atlas_etf_states_daily s
                ON s.ticker = d.ticker AND s.date = d.date
            WHERE d.date = :today
        """)
    else:
        query = text("""
            SELECT mstar_id AS instrument_id,
                   entry_trigger,
                   exit_market_riskoff, exit_composition_misaligned,
                   exit_holdings_weak, exit_nav_deteriorate
            FROM atlas.atlas_fund_decisions_daily
            WHERE date = :today
        """)

    return pd.read_sql(query, conn, params={"today": today})


def check_decisions_exist(engine: Engine, tier: str, today: date) -> None:
    """Raise MissingAtlasDecisionsError if no decisions for today."""
    table_map = {
        "stocks": "atlas_stock_decisions_daily",
        "etf": "atlas_etf_decisions_daily",
        "fund": "atlas_fund_decisions_daily",
    }
    table = table_map[tier]
    with open_compute_session(engine) as conn:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM atlas.{table} WHERE date = :d"),  # noqa: S608 -- table is an internal constant
            {"d": today},
        ).scalar()
    if count == 0:
        msg = f"No {tier} decisions found for {today} — Atlas compute may have failed."
        raise MissingAtlasDecisionsError(msg)


def load_current_holdings(conn: Connection, strategy_id: UUID) -> dict[str, Holding]:
    """Read current atlas.strategy_paper_portfolios for one strategy."""
    rows = conn.execute(
        text("""
            SELECT instrument_id, instrument_type, weight_pct,
                   entry_date, entry_signal_type, notional_value
            FROM atlas.strategy_paper_portfolios
            WHERE strategy_id = :sid
        """),
        {"sid": str(strategy_id)},
    ).fetchall()
    return {
        r.instrument_id: Holding(
            instrument_id=r.instrument_id,
            instrument_type=r.instrument_type,
            weight_pct=float(r.weight_pct),
            entry_date=r.entry_date,
            entry_signal_type=r.entry_signal_type,
            notional_value=float(r.notional_value),
        )
        for r in rows
    }


def write_trades(
    engine: Engine,
    trades: list[Trade],
    strategy_id: UUID,
    today: date,
    regime: str,
    prices: dict[str, float],
) -> None:
    """Bulk-insert trades to atlas.strategy_paper_trades."""
    if not trades:
        return
    rows = [
        (
            str(strategy_id),
            t.instrument_id,
            t.instrument_type,
            t.action,
            t.signal_type,
            prices.get(t.instrument_id, 0.0),
            t.weight_pct,
            t.notional_value,
            today,
            regime,
        )
        for t in trades
    ]
    bulk_upsert(
        engine=engine,
        table="atlas.strategy_paper_trades",
        columns=[
            "strategy_id",
            "instrument_id",
            "instrument_type",
            "action",
            "signal_type",
            "price",
            "weight_pct",
            "notional_value",
            "trade_date",
            "regime_at_trade",
        ],
        rows=rows,
        pk_columns=["strategy_id", "instrument_id", "trade_date", "action"],
    )


def update_holdings(
    engine: Engine,
    trades: list[Trade],
    strategy_id: UUID,
    today: date,
) -> None:
    """Apply trades to atlas.strategy_paper_portfolios."""
    with open_compute_session(engine) as conn:
        for t in trades:
            if t.action == "exit":
                conn.execute(
                    text("""
                        DELETE FROM atlas.strategy_paper_portfolios
                        WHERE strategy_id = :sid AND instrument_id = :iid
                    """),
                    {"sid": str(strategy_id), "iid": t.instrument_id},
                )
            elif t.action == "enter":
                conn.execute(
                    text("""
                        INSERT INTO atlas.strategy_paper_portfolios
                            (strategy_id, instrument_id, instrument_type,
                             weight_pct, entry_date, entry_signal_type, notional_value)
                        VALUES (:sid, :iid, :itype, :wpct, :edate, :esig, :nval)
                        ON CONFLICT (strategy_id, instrument_id) DO UPDATE SET
                            weight_pct = EXCLUDED.weight_pct,
                            notional_value = EXCLUDED.notional_value,
                            updated_at = now()
                    """),
                    {
                        "sid": str(strategy_id),
                        "iid": t.instrument_id,
                        "itype": t.instrument_type,
                        "wpct": t.weight_pct,
                        "edate": today,
                        "esig": t.signal_type,
                        "nval": t.notional_value,
                    },
                )
            elif t.action == "rebalance":
                conn.execute(
                    text("""
                        UPDATE atlas.strategy_paper_portfolios
                        SET weight_pct = :wpct, notional_value = :nval, updated_at = now()
                        WHERE strategy_id = :sid AND instrument_id = :iid
                    """),
                    {
                        "sid": str(strategy_id),
                        "iid": t.instrument_id,
                        "wpct": t.weight_pct,
                        "nval": t.notional_value,
                    },
                )
        conn.commit()


def record_daily_performance(
    engine: Engine,
    strategy_id: UUID,
    today: date,
    total_value: float,
    daily_return: float,
    regime: str,
    positions_count: int,
    benchmark_nifty500: float | None = None,
    benchmark_naive_atlas: float | None = None,
) -> None:
    """Write one row to atlas.strategy_paper_performance."""
    bulk_upsert(
        engine=engine,
        table="atlas.strategy_paper_performance",
        columns=[
            "strategy_id",
            "date",
            "total_value",
            "daily_return",
            "benchmark_nifty500_return",
            "benchmark_naive_atlas_return",
            "regime",
            "positions_count",
        ],
        rows=[
            (
                str(strategy_id),
                today,
                total_value,
                daily_return,
                benchmark_nifty500,
                benchmark_naive_atlas,
                regime,
                positions_count,
            )
        ],
        pk_columns=["strategy_id", "date"],
    )
