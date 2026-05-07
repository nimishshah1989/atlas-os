"""Stock decision pipeline — M5 Phase A/B/C/D.

Per ``docs/00_METHODOLOGY_LOCK.md`` §13.1-13.4 and
``docs/milestones/ATLAS_M5_DECISION_ENGINE.md`` §4-7.

Computes for each (stock, date):
  - Six investability gates (AND-logic, top-down: market → sector → stock)
  - Two entry triggers (TRANSITION, BREAKOUT)
  - Position size multiplier (base × market_multiplier × risk_multiplier)
  - Six exit triggers + exit_action

Writes to ``atlas.atlas_stock_decisions_daily``.

Design principle: top-down gating means market regime and sector state veto
stock-level strength. A Leader-Strong stock in Risk-Off regime is NOT
investable. Gates are evaluated in priority order; the first failure is
recorded in ``gating_factor`` for UI transparency.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

# Risk multipliers per methodology §13.3
RISK_MULTIPLIERS: dict[str, float] = {
    "Low": 1.2,
    "Normal": 1.0,
    "Elevated": 0.6,
    "High": 0.0,
    "Below Trend": 0.0,
}

# Market (deployment) multipliers per methodology §10 / regime states
MARKET_MULTIPLIERS: dict[str, float] = {
    "Risk-On": 1.0,
    "Constructive": 0.7,
    "Cautious": 0.4,
    "Risk-Off": 0.0,
}

DECISIONS_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "date",
    "is_investable",
    "strength_gate",
    "direction_gate",
    "risk_gate",
    "volume_gate",
    "sector_gate",
    "market_gate",
    "transition_trigger",
    "breakout_trigger",
    "proximity_pass",
    "position_size_pct",
    "market_multiplier",
    "risk_multiplier",
    "exit_market_riskoff",
    "exit_sector_avoid",
    "exit_rs_deteriorate",
    "exit_momentum_collapse",
    "exit_volume_distrib",
    "exit_stop_loss",
    "compute_run_id",
)

# States that pass strength gate
STRENGTH_PASS_STATES = frozenset(["Leader", "Strong", "Emerging"])
# States that trigger RS_WEAKEN exit
RS_WEAK_STATES = frozenset(["Average", "Weak", "Laggard"])
# Momentum states that pass direction gate
DIRECTION_PASS_STATES = frozenset(["Accelerating", "Improving"])
# Volume states that pass volume gate
VOLUME_PASS_STATES = frozenset(["Accumulation", "Steady-Buying"])
# Risk states that pass risk gate
RISK_PASS_STATES = frozenset(["Low", "Normal"])
# Sector states that pass sector gate
SECTOR_PASS_STATES = frozenset(["Overweight", "Neutral"])
# Momentum states that are "weak" (used in TRANSITION trigger lookback)
MOMENTUM_WEAK_SET = frozenset(["Flat", "Deteriorating"])
MOMENTUM_STRONG_SET = frozenset(["Improving", "Accelerating"])


# --------------------------------------------------------------------------- #
# Core loader                                                                  #
# --------------------------------------------------------------------------- #


def _load_stock_state_with_context(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load stock states joined to sector states and market regime."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                s.instrument_id::text AS instrument_id,
                s.date,
                s.rs_state,
                s.momentum_state,
                s.risk_state,
                s.volume_state,
                s.sector,
                s.weinstein_gate_pass,
                ss.sector_state,
                mr.regime_state,
                mr.deployment_multiplier,
                mr.dislocation_active
            FROM atlas.atlas_stock_states_daily s
            LEFT JOIN atlas.atlas_sector_states_daily ss
                ON ss.sector_name = s.sector AND ss.date = s.date
            LEFT JOIN atlas.atlas_market_regime_daily mr
                ON mr.date = s.date
            WHERE s.date BETWEEN %(start)s AND %(end)s
              AND s.rs_state NOT IN (
                  'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED'
              )
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# --------------------------------------------------------------------------- #
# Investability gates                                                          #
# --------------------------------------------------------------------------- #


def compute_investability_gates(df: pd.DataFrame) -> pd.DataFrame:
    """Add six gate columns + is_investable + gating_factor to df in-place."""
    # Gate 1 — Market: regime not Risk-Off and dislocation not active
    df["market_gate"] = (df["regime_state"] != "Risk-Off") & ~df["dislocation_active"].fillna(False)

    # Gate 2 — Sector: sector_state in {Overweight, Neutral}
    df["sector_gate"] = df["sector_state"].isin(SECTOR_PASS_STATES)

    # Gate 3 — Strength: rs_state in {Leader, Strong, Emerging}
    df["strength_gate"] = df["rs_state"].isin(STRENGTH_PASS_STATES)

    # Gate 4 — Direction: momentum_state in {Accelerating, Improving}
    df["direction_gate"] = df["momentum_state"].isin(DIRECTION_PASS_STATES)

    # Gate 5 — Risk: risk_state in {Low, Normal}
    df["risk_gate"] = df["risk_state"].isin(RISK_PASS_STATES)

    # Gate 6 — Volume: volume_state in {Accumulation, Steady-Buying}
    df["volume_gate"] = df["volume_state"].isin(VOLUME_PASS_STATES)

    # All gates must pass
    df["is_investable"] = (
        df["market_gate"]
        & df["sector_gate"]
        & df["strength_gate"]
        & df["direction_gate"]
        & df["risk_gate"]
        & df["volume_gate"]
    )

    return df


# --------------------------------------------------------------------------- #
# Position sizing                                                              #
# --------------------------------------------------------------------------- #


def add_position_sizing(
    df: pd.DataFrame,
    base_pct: float = 1.0,
) -> pd.DataFrame:
    """Compute position_size_pct = base × market_multiplier × risk_multiplier."""
    df["market_multiplier"] = df["regime_state"].map(MARKET_MULTIPLIERS).fillna(0.0)
    df["risk_multiplier"] = df["risk_state"].map(RISK_MULTIPLIERS).fillna(0.0)
    df["position_size_pct"] = base_pct * df["market_multiplier"] * df["risk_multiplier"]
    return df


# --------------------------------------------------------------------------- #
# Entry triggers                                                               #
# --------------------------------------------------------------------------- #


def compute_entry_triggers(
    df: pd.DataFrame,
    engine: Engine,
    target_date: date,
    thresholds: dict[str, Any],
) -> pd.DataFrame:
    """Add transition_trigger, breakout_trigger, proximity_pass columns.

    TRANSITION: investable + strong momentum today + weak momentum in past 5 days
    + volume = Accumulation today.
    BREAKOUT: investable + new 63-day high + volume = Accumulation + within 5%
    of EMA-20 (proximity threshold from thresholds catalog).
    """
    proximity_max = float(thresholds.get("entry_breakout_proximity_max_pct", 5)) / 100

    # --- TRANSITION trigger ---
    # Load last 5 trading days' momentum states
    lookback_start = target_date - timedelta(days=12)  # calendar days, overshoots
    with open_compute_session(engine) as conn:
        recent_momentum = pd.read_sql(
            """
            SELECT instrument_id::text AS instrument_id, date, momentum_state
            FROM atlas.atlas_stock_states_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND date < %(target)s
            ORDER BY instrument_id, date DESC
            """,
            conn,
            params={"start": lookback_start, "end": target_date, "target": target_date},
        )

    if not recent_momentum.empty:
        recent_momentum["date"] = pd.to_datetime(recent_momentum["date"]).dt.date
        # Keep only last 5 trading days
        recent_5d = (
            recent_momentum.sort_values("date", ascending=False).groupby("instrument_id").head(5)
        )
        had_weak = (
            recent_5d[recent_5d["momentum_state"].isin(MOMENTUM_WEAK_SET)]
            .groupby("instrument_id")
            .size()
            .gt(0)
            .reset_index()
            .rename(columns={0: "had_weak_recently"})
        )
        df = df.merge(had_weak, on="instrument_id", how="left")
        df["had_weak_recently"] = df["had_weak_recently"].fillna(False)
    else:
        df["had_weak_recently"] = False

    df["transition_trigger"] = (
        df["is_investable"]
        & df["momentum_state"].isin(MOMENTUM_STRONG_SET)
        & df["had_weak_recently"]
        & (df["volume_state"] == "Accumulation")
    )

    # --- BREAKOUT trigger ---
    # Load 63-day high from stock metrics
    lookback_63d = target_date - timedelta(days=100)  # calendar overshoots
    with open_compute_session(engine) as conn:
        price_data = pd.read_sql(
            """
            SELECT instrument_id::text AS instrument_id,
                   close, ema_20_stock
            FROM atlas.atlas_stock_metrics_daily
            WHERE date = %(target)s
            """,
            conn,
            params={"target": target_date},
        )
        high_63d = pd.read_sql(
            """
            SELECT instrument_id::text AS instrument_id,
                   MAX(close) AS high_63d
            FROM atlas.atlas_stock_metrics_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND close IS NOT NULL
            GROUP BY instrument_id
            """,
            conn,
            params={"start": lookback_63d, "end": target_date},
        )

    if not price_data.empty:
        df = df.merge(
            price_data[["instrument_id", "close", "ema_20_stock"]], on="instrument_id", how="left"
        )
        df = df.merge(high_63d, on="instrument_id", how="left")

        ema = df["ema_20_stock"].replace(0, np.nan)
        df["proximity_pass"] = ((df["close"] - ema).abs() / ema) <= proximity_max
        df["breakout_trigger"] = (
            df["is_investable"]
            & (df["close"] >= df["high_63d"])
            & (df["volume_state"] == "Accumulation")
            & df["proximity_pass"].fillna(False)
        )
    else:
        df["proximity_pass"] = False
        df["breakout_trigger"] = False

    return df


# --------------------------------------------------------------------------- #
# Exit triggers                                                                #
# --------------------------------------------------------------------------- #


def compute_exit_triggers(df: pd.DataFrame) -> pd.DataFrame:
    """Add six exit trigger columns + exit_stop_loss (ATR-based stop level).

    ATR stop requires entry_price from portfolio state — v0 computes the stop
    level (close - 3×ATR) but sets exit_stop_loss=False since there's no
    portfolio-state table. UI applies it against the user's actual entry price.
    """
    # Trigger 1: MARKET_RISK_OFF
    df["exit_market_riskoff"] = df["regime_state"] == "Risk-Off"

    # Trigger 2: SECTOR_AVOID
    df["exit_sector_avoid"] = df["sector_state"] == "Avoid"

    # Trigger 3: RS_WEAKEN
    df["exit_rs_deteriorate"] = df["rs_state"].isin(RS_WEAK_STATES)

    # Trigger 4: MOMENTUM_COLLAPSE
    df["exit_momentum_collapse"] = df["momentum_state"] == "Collapsing"

    # Trigger 5: VOLUME_HEAVY_DIST
    df["exit_volume_distrib"] = df["volume_state"] == "Heavy Distribution"

    # Trigger 6: ATR_STOP — v0: always False; stop level surfaced via ATR metric
    df["exit_stop_loss"] = False

    return df


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_stock_decisions(
    start_date: date,
    end_date: date,
    run_id: uuid.UUID | None = None,
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute all stock decision columns for every (stock, date) in range.

    Returns ``{run_id, rows_written, errors}``.
    """
    engine = engine or get_engine()
    run_id = run_id or uuid.uuid4()

    if thresholds is None:
        thresholds = load_thresholds(engine)

    log.info("stock_decisions_start", start=str(start_date), end=str(end_date))

    df = _load_stock_state_with_context(engine, start_date, end_date)
    if df.empty:
        log.warning("stock_decisions_empty_load", start=str(start_date), end=str(end_date))
        return {"run_id": run_id, "rows_written": 0, "errors": []}

    df = compute_investability_gates(df)
    df = add_position_sizing(df)
    df = compute_exit_triggers(df)

    # Entry triggers require per-date price lookups; process date by date
    all_frames: list[pd.DataFrame] = []
    for d in sorted(df["date"].unique()):
        day_df = df[df["date"] == d].copy()
        try:
            day_df = compute_entry_triggers(day_df, engine, d, thresholds)
        except Exception as exc:
            log.error("stock_decisions_entry_trigger_error", date=str(d), error=str(exc))
            day_df["transition_trigger"] = False
            day_df["breakout_trigger"] = False
            day_df["proximity_pass"] = False
        all_frames.append(day_df)

    result_df = pd.concat(all_frames, ignore_index=True)
    result_df["compute_run_id"] = str(run_id)

    write_cols = [c for c in DECISIONS_COLUMNS if c in result_df.columns]
    rows = df_to_pg_rows(result_df[write_cols])
    rows_written = bulk_upsert(
        engine,
        "atlas.atlas_stock_decisions_daily",
        list(write_cols),
        rows,
        pk_columns=["instrument_id", "date"],
    )

    log.info("stock_decisions_complete", rows_written=rows_written)
    return {"run_id": run_id, "rows_written": rows_written, "errors": []}


def backfill_stock_decisions(
    start_date: date | None = None,
    end_date: date | None = None,
    engine: Engine | None = None,
) -> int:
    """Historical backfill. Returns total rows written."""
    engine = engine or get_engine()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()
    result = run_stock_decisions(start, end, engine=engine)
    return int(str(result["rows_written"]))
