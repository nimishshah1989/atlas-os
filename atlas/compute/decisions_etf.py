"""ETF decision pipeline — M5 Phase E.

Per ``docs/00_METHODOLOGY_LOCK.md`` §13.5 and
``docs/milestones/ATLAS_M5_DECISION_ENGINE.md`` §8.

Adapts the stock decision engine for ETFs:
  - 5 investability gates (no volume gate — ETF volume is NAV-creation
    activity, not buyer/seller imbalance)
  - Theme-conditional sector gating:
      Broad ETFs → sector gate auto-passes
      Sectoral ETFs → gated by linked sector_state
      Thematic ETFs → gated by dominant underlying sector_state
  - Entry triggers identical to stocks (TRANSITION + BREAKOUT)
  - 5 exit triggers (no VOLUME_HEAVY_DIST)
  - Position sizing: same formula

Writes to ``atlas.atlas_etf_decisions_daily``.
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
from atlas.compute.decisions_stock import (
    MOMENTUM_STRONG_SET,
    MOMENTUM_WEAK_SET,
    add_position_sizing,
)
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

DECISIONS_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "is_investable",
    "strength_gate",
    "direction_gate",
    "risk_gate",
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
    "exit_stop_loss",
    "compute_run_id",
)

ETF_STRENGTH_PASS = frozenset(["Leader", "Strong", "Consolidating", "Emerging"])
ETF_DIRECTION_PASS = frozenset(["Accelerating", "Improving"])
ETF_RS_WEAK = frozenset(["Average", "Weak", "Laggard"])


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #


def _load_etf_state_with_context(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load ETF states joined to universe (theme/linked_sector), sector states, regime."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                es.ticker,
                es.date,
                es.rs_state,
                es.momentum_state,
                es.risk_state,
                es.volume_state,
                u.theme,
                u.linked_sector,
                ss.sector_state AS linked_sector_state,
                mr.regime_state,
                mr.deployment_multiplier,
                mr.dislocation_active
            FROM atlas.atlas_etf_states_daily es
            JOIN atlas.atlas_universe_etfs u
                ON u.ticker = es.ticker AND u.effective_to IS NULL
            LEFT JOIN atlas.atlas_sector_states_daily ss
                ON ss.sector_name = u.linked_sector AND ss.date = es.date
            LEFT JOIN atlas.atlas_market_regime_daily mr
                ON mr.date = es.date
            WHERE es.date BETWEEN %(start)s AND %(end)s
              AND es.rs_state NOT IN (
                  'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED'
              )
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _load_dominant_sector_for_thematic_etfs(
    engine: Engine,
    target_date: date,
) -> pd.DataFrame:
    """Compute dominant sector for thematic ETFs from holdings on or before target_date."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            WITH latest_holdings AS (
                SELECT ticker, MAX(as_of_date) AS as_of_date
                FROM public.de_etf_holdings
                WHERE as_of_date <= %(date)s
                GROUP BY ticker
            ),
            holdings_with_sector AS (
                SELECT h.ticker, h.weight, u.sector
                FROM public.de_etf_holdings h
                JOIN latest_holdings lh ON lh.ticker = h.ticker AND lh.as_of_date = h.as_of_date
                LEFT JOIN atlas.atlas_universe_stocks u
                    ON u.instrument_id = h.instrument_id AND u.effective_to IS NULL
                WHERE u.sector IS NOT NULL
            ),
            sector_weights AS (
                SELECT ticker, sector, SUM(weight) AS sector_weight
                FROM holdings_with_sector
                GROUP BY ticker, sector
            ),
            ranked AS (
                SELECT ticker, sector, sector_weight,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY sector_weight DESC) AS rn
                FROM sector_weights
            )
            SELECT r.ticker, r.sector AS dominant_sector, ss.sector_state AS dominant_sector_state
            FROM ranked r
            LEFT JOIN atlas.atlas_sector_states_daily ss
                ON ss.sector_name = r.sector
               AND ss.date = (
                   SELECT MAX(date) FROM atlas.atlas_sector_states_daily WHERE date <= %(date)s
               )
            WHERE r.rn = 1
            """,
            conn,
            params={"date": target_date},
        )


# --------------------------------------------------------------------------- #
# ETF investability gates (5 — no volume)                                     #
# --------------------------------------------------------------------------- #


def _sector_gate_value(theme: str, linked_state: Any, dominant_state: Any) -> bool:
    if theme == "Broad":
        return True
    if theme == "Sectoral":
        return linked_state not in [None, "Avoid"] and not pd.isna(linked_state or "")
    # Thematic: use dominant sector state; fallback auto-pass if unknown
    if pd.isna(dominant_state or ""):
        return True
    return str(dominant_state) not in ["Avoid"]


def compute_etf_gates(
    df: pd.DataFrame,
    dominant_sector: pd.DataFrame | None = None,
    *,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """Apply 5 ETF gates + is_investable.

    If engine is provided, gate-policy is loaded from atlas.atlas_decision_policy
    (with code-default fallback). If engine is None, uses module-level constants
    (preserves backward compat for tests that don't need DB).
    """
    if dominant_sector is not None and not dominant_sector.empty:
        df = df.merge(
            dominant_sector[["ticker", "dominant_sector_state"]],
            on="ticker",
            how="left",
        )
    else:
        df["dominant_sector_state"] = None

    if engine is not None:
        from atlas.compute._policy import load_gate_policy

        strength_pass = load_gate_policy("strength_gate_etf", engine)
        direction_pass = load_gate_policy("direction_gate_etf", engine)
        market_pass = load_gate_policy("market_gate", engine)
    else:
        strength_pass = ETF_STRENGTH_PASS
        direction_pass = ETF_DIRECTION_PASS
        market_pass = frozenset({"Risk-On", "Constructive", "Cautious"})

    df["market_gate"] = df["regime_state"].isin(market_pass) & ~df["dislocation_active"].fillna(
        False
    )

    df["sector_gate"] = df.apply(
        lambda r: _sector_gate_value(
            r.get("theme", "Broad"),
            r.get("linked_sector_state"),
            r.get("dominant_sector_state"),
        ),
        axis=1,
    )

    df["strength_gate"] = df["rs_state"].isin(strength_pass)
    df["direction_gate"] = df["momentum_state"].isin(direction_pass)
    # Risk gate: Elevated is allowed for ETFs (broader diversification reduces single-stock risk)
    df["risk_gate"] = ~df["risk_state"].isin(["High", "Below Trend"])

    df["is_investable"] = (
        df["market_gate"]
        & df["sector_gate"]
        & df["strength_gate"]
        & df["direction_gate"]
        & df["risk_gate"]
    )
    return df


# --------------------------------------------------------------------------- #
# ETF exit triggers (5 — no volume heavy distribution)                        #
# --------------------------------------------------------------------------- #


def compute_etf_exit_triggers(df: pd.DataFrame) -> pd.DataFrame:
    df["exit_market_riskoff"] = df["regime_state"] == "Risk-Off"
    df["exit_sector_avoid"] = df.apply(
        lambda r: str(r.get("linked_sector_state", "")) == "Avoid"
        or str(r.get("dominant_sector_state", "")) == "Avoid",
        axis=1,
    )
    df["exit_rs_deteriorate"] = df["rs_state"].isin(ETF_RS_WEAK)
    df["exit_momentum_collapse"] = df["momentum_state"] == "Collapsing"
    df["exit_stop_loss"] = False  # v0: not implemented (no portfolio table)
    return df


# --------------------------------------------------------------------------- #
# Entry triggers (same logic as stocks, adapted for ETF columns)              #
# --------------------------------------------------------------------------- #


def compute_etf_entry_triggers(
    df: pd.DataFrame,
    engine: Engine,
    target_date: date,
    thresholds: dict[str, Any],
) -> pd.DataFrame:
    proximity_max = float(thresholds.get("entry_breakout_proximity_max_pct", 5)) / 100
    lookback_start = target_date - timedelta(days=12)

    # Transition trigger: weak→strong momentum in past 5 days
    with open_compute_session(engine) as conn:
        recent = pd.read_sql(
            """
            SELECT ticker, date, momentum_state
            FROM atlas.atlas_etf_states_daily
            WHERE date BETWEEN %(start)s AND %(end)s AND date < %(target)s
            ORDER BY ticker, date DESC
            """,
            conn,
            params={"start": lookback_start, "end": target_date, "target": target_date},
        )
    if not recent.empty:
        recent["date"] = pd.to_datetime(recent["date"]).dt.date
        recent_5d = recent.sort_values("date", ascending=False).groupby("ticker").head(5)
        had_weak = (
            recent_5d[recent_5d["momentum_state"].isin(MOMENTUM_WEAK_SET)]
            .groupby("ticker")
            .size()
            .gt(0)
            .reset_index()
            .rename(columns={0: "had_weak_recently"})
        )
        df = df.merge(had_weak, on="ticker", how="left")
        df["had_weak_recently"] = df["had_weak_recently"].fillna(False)
    else:
        df["had_weak_recently"] = False

    df["transition_trigger"] = (
        df["is_investable"]
        & df["momentum_state"].isin(MOMENTUM_STRONG_SET)
        & df["had_weak_recently"]
        & (df["volume_state"] == "Accumulation")
    )

    # Breakout trigger — close prices live in public.de_etf_ohlcv,
    # ema_20_etf lives in atlas_etf_metrics_daily.
    lookback_63d = target_date - timedelta(days=100)
    with open_compute_session(engine) as conn:
        price_data = pd.read_sql(
            """
            SELECT
                m.ticker,
                p.close,
                m.ema_20_etf
            FROM atlas.atlas_etf_metrics_daily m
            LEFT JOIN public.de_etf_ohlcv p
                ON p.ticker = m.ticker AND p.date = m.date
            WHERE m.date = %(target)s
            """,
            conn,
            params={"target": target_date},
        )
        high_63d = pd.read_sql(
            """
            SELECT ticker, MAX(close) AS high_63d
            FROM public.de_etf_ohlcv
            WHERE date BETWEEN %(start)s AND %(end)s AND close IS NOT NULL
            GROUP BY ticker
            """,
            conn,
            params={"start": lookback_63d, "end": target_date},
        )

    if not price_data.empty:
        df = df.merge(price_data[["ticker", "close", "ema_20_etf"]], on="ticker", how="left")
        df = df.merge(high_63d, on="ticker", how="left")
        ema = df["ema_20_etf"].replace(0, np.nan)
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
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_etf_decisions(
    start_date: date,
    end_date: date,
    run_id: uuid.UUID | None = None,
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute ETF decision columns for every (ticker, date) in range."""
    engine = engine or get_engine()
    run_id = run_id or uuid.uuid4()
    if thresholds is None:
        thresholds = load_thresholds(engine)

    log.info("etf_decisions_start", start=str(start_date), end=str(end_date))

    df = _load_etf_state_with_context(engine, start_date, end_date)
    if df.empty:
        return {"run_id": run_id, "rows_written": 0, "errors": []}

    all_frames: list[pd.DataFrame] = []
    for d in sorted(df["date"].unique()):
        day_df = df[df["date"] == d].copy()
        try:
            dom_sector = _load_dominant_sector_for_thematic_etfs(engine, d)
            day_df = compute_etf_gates(day_df, dom_sector, engine=engine)
            day_df = add_position_sizing(day_df, engine=engine)
            day_df = compute_etf_exit_triggers(day_df)
            day_df = compute_etf_entry_triggers(day_df, engine, d, thresholds)
        except Exception as exc:
            log.error("etf_decisions_date_error", date=str(d), error=str(exc))
            day_df["is_investable"] = False
            for col in (
                "transition_trigger",
                "breakout_trigger",
                "exit_market_riskoff",
                "exit_sector_avoid",
                "exit_rs_deteriorate",
                "exit_momentum_collapse",
                "exit_stop_loss",
            ):
                day_df[col] = False
        all_frames.append(day_df)

    result_df = pd.concat(all_frames, ignore_index=True)
    result_df["compute_run_id"] = str(run_id)

    write_cols = [c for c in DECISIONS_COLUMNS if c in result_df.columns]
    rows = df_to_pg_rows(result_df[write_cols])
    rows_written = bulk_upsert(
        engine,
        "atlas.atlas_etf_decisions_daily",
        list(write_cols),
        rows,
        pk_columns=["ticker", "date"],
    )
    log.info("etf_decisions_complete", rows_written=rows_written)
    return {"run_id": run_id, "rows_written": rows_written, "errors": []}


def backfill_etf_decisions(
    start_date: date | None = None,
    end_date: date | None = None,
    engine: Engine | None = None,
) -> int:
    engine = engine or get_engine()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()
    result = run_etf_decisions(start, end, engine=engine)
    return int(str(result["rows_written"]))
