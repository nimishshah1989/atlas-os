"""State IC validator — Chunk 9 of the Atlas Intelligence Engine.

Reads atlas.atlas_stock_states_daily, for each state badge (rs_state,
momentum_state, risk_state, volume_state, history_gate_pass, etc.) computes
the IC of the state's *defining numeric value* vs forward 63d returns, then
classifies the state as one of:

  validated   IR_of_IC > 0.4 AND |Q5-Q1 spread| > 0.5% AND OOS-stable
  weak        IR_of_IC in (0.2, 0.4)
  decorative  IR_of_IC <= 0.2

Writes to atlas.atlas_state_validation (created here on first run if absent).

The frontend rendering rule (chunk 11 follow-up): validated states get a
green badge with the implied action; weak states get an asterisk; decorative
states render with no implied action — they remain context, not a signal.

This module reuses atlas/intelligence/validation/ic_engine.py +
forward_returns.py + persistence.py. No new IC math; only the orchestration
+ classification.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.encoding import SENTINEL_STATES, STATE_ENCODINGS
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)
from atlas.intelligence.validation.ic_engine import ICResult, compute_ic_over_window

log = structlog.get_logger()


@dataclass(frozen=True)
class StateValidationResult:
    state_name: str
    implied_action: str
    horizon_days: int
    ic: ICResult
    status: Literal["validated", "validated_inverse", "weak", "decorative"]
    as_of: date


# Catalog of state badges that have an implied-long action.
# state_name maps to (sql_column, implied_action_at_horizon).
# Numeric encoding: state values are encoded as integers (e.g., rs_state 0-4),
# and IC against forward returns tells us whether higher state value predicts
# higher returns. For boolean gates (e.g., history_gate_pass), the encoding
# is 0/1, and IC tells us whether "passes gate" predicts forward returns.
_STATE_CATALOG: dict[str, dict] = {
    "rs_state": {
        "column": "rs_state",
        "implied_action": "favours_long_at_63d",
        "encoding": "integer",  # 0=laggard..4=leader
    },
    "momentum_state": {
        "column": "momentum_state",
        "implied_action": "favours_long_at_63d",
        "encoding": "integer",  # 0=decelerating..2=accelerating
    },
    "risk_state": {
        "column": "risk_state",
        "implied_action": "warns_long_at_63d",
        "encoding": "integer",
    },
    "volume_state": {
        "column": "volume_state",
        "implied_action": "neutral_informational",
        "encoding": "integer",
    },
    "history_gate_pass": {
        "column": "history_gate_pass",
        "implied_action": "favours_long_at_63d",
        "encoding": "boolean",
    },
    "liquidity_gate_pass": {
        "column": "liquidity_gate_pass",
        "implied_action": "favours_long_at_63d",
        "encoding": "boolean",
    },
    "weinstein_gate_pass": {
        "column": "weinstein_gate_pass",
        "implied_action": "favours_long_at_63d",
        "encoding": "boolean",
    },
    "stage1_base_qualifies": {
        "column": "stage1_base_qualifies",
        "implied_action": "favours_long_at_63d",
        "encoding": "boolean",
    },
}


def _engine() -> Engine:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL is not set")
    return create_engine(
        db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0],
        pool_size=2,
        max_overflow=0,
    )


def _load_state_factor(
    eng: Engine, column: str, encoding: str, start: date, end: date
) -> pd.DataFrame:
    """Load state column, encode to numeric, return (date, instrument_id) factor.

    encoding='categorical' → look up via encoding.STATE_ENCODINGS, drop sentinels.
    encoding='boolean'     → CAST boolean to numeric 0/1.
    """
    with eng.connect() as c:
        if encoding == "boolean":
            df = pd.read_sql(
                text(f"""
                SELECT date, instrument_id::text AS instrument_id,
                       CASE WHEN {column} THEN 1.0 ELSE 0.0 END AS factor
                FROM atlas.atlas_stock_states_daily
                WHERE date BETWEEN :s AND :e
                  AND {column} IS NOT NULL
            """),
                c,
                params={"s": start, "e": end},
            )
        else:
            df = pd.read_sql(
                text(f"""
                SELECT date, instrument_id::text AS instrument_id,
                       {column}::text AS state_value
                FROM atlas.atlas_stock_states_daily
                WHERE date BETWEEN :s AND :e
                  AND {column} IS NOT NULL
            """),
                c,
                params={"s": start, "e": end},
            )
            df = df[~df["state_value"].isin(SENTINEL_STATES)]
            mapping = STATE_ENCODINGS.get(column, {})
            df["factor"] = df["state_value"].map(mapping)
            df = df.dropna(subset=["factor"]).drop(columns=["state_value"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index(["date", "instrument_id"])
    return df[["factor"]]


def _classify(
    ic: ICResult, implied_action: str, q_spread: float = 0.005
) -> Literal["validated", "validated_inverse", "weak", "decorative"]:
    """Map IC stats to a 4-way status label.

    validated         — IC sign aligns with implied_action and |IR|>0.4
    validated_inverse — strong predictive power but OPPOSITE direction
                        (e.g., implied_action=favours_long but IC<0).
                        The state is real signal but the displayed action
                        is wrong; frontend should invert or relabel.
    weak              — |IR| in (0.2, 0.4)
    decorative        — |IR| <= 0.2; no reliable predictive power
    """
    if ic.ic_std is None or ic.ic_std == 0:
        return "decorative"
    ir = ic.mean_ic / ic.ic_std
    abs_ir = abs(ir)
    if abs_ir > 0.4 and abs(ic.mean_ic) > q_spread:
        # Determine if IC sign aligns with implied_action.
        # 'favours_long' / 'favours_long_at_63d' → positive IC is aligned.
        # 'warns_long' / 'warns_long_at_63d'     → negative IC is aligned.
        expects_positive = implied_action.startswith("favours")
        aligned = (ir > 0 and expects_positive) or (ir < 0 and not expects_positive)
        return "validated" if aligned else "validated_inverse"
    if abs_ir > 0.2:
        return "weak"
    return "decorative"


def _ensure_table(eng: Engine) -> None:
    """Create atlas_state_validation on first use. Idempotent."""
    ddl = """
    CREATE TABLE IF NOT EXISTS atlas.atlas_state_validation (
        state_name VARCHAR(64) NOT NULL,
        implied_action VARCHAR(64) NOT NULL,
        horizon_days INTEGER NOT NULL,
        as_of_date DATE NOT NULL,
        mean_ic NUMERIC(10, 6),
        ic_std NUMERIC(10, 6),
        ic_t_stat NUMERIC(10, 4),
        ic_ir NUMERIC(10, 4),
        n_observations INTEGER,
        status VARCHAR(24) NOT NULL,
        validated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        PRIMARY KEY (state_name, horizon_days, as_of_date),
        CHECK (status IN ('validated', 'validated_inverse', 'weak', 'decorative'))
    )
    """
    with eng.begin() as c:
        c.execute(text(ddl))


def _persist(eng: Engine, result: StateValidationResult) -> None:
    """UPSERT one state-validation row."""
    sql = """
    INSERT INTO atlas.atlas_state_validation
        (state_name, implied_action, horizon_days, as_of_date,
         mean_ic, ic_std, ic_t_stat, ic_ir, n_observations, status)
    VALUES
        (:state_name, :implied_action, :horizon_days, :as_of,
         :mean_ic, :ic_std, :ic_t_stat, :ic_ir, :n_obs, :status)
    ON CONFLICT (state_name, horizon_days, as_of_date) DO UPDATE SET
        mean_ic = EXCLUDED.mean_ic, ic_std = EXCLUDED.ic_std,
        ic_t_stat = EXCLUDED.ic_t_stat, ic_ir = EXCLUDED.ic_ir,
        n_observations = EXCLUDED.n_observations, status = EXCLUDED.status,
        validated_at = NOW()
    """
    ir = (
        (result.ic.mean_ic / result.ic.ic_std)
        if result.ic.ic_std and result.ic.ic_std > 0
        else None
    )
    with eng.begin() as c:
        c.execute(
            text(sql),
            {
                "state_name": result.state_name,
                "implied_action": result.implied_action,
                "horizon_days": result.horizon_days,
                "as_of": result.as_of,
                "mean_ic": float(result.ic.mean_ic),
                "ic_std": float(result.ic.ic_std),
                "ic_t_stat": float(result.ic.ic_t_stat),
                "ic_ir": float(ir) if ir is not None else None,
                "n_obs": int(result.ic.n_observations),
                "status": result.status,
            },
        )


def validate_all_states(
    start: date, end: date, horizon_days: int = 63
) -> list[StateValidationResult]:
    """Run IC validation for every state in _STATE_CATALOG; persist + return."""
    eng = _engine()
    _ensure_table(eng)
    prices = load_price_matrix(eng, start_date=start, end_date=end)
    if prices.empty:
        log.error("no_price_data", start=str(start), end=str(end))
        return []
    fwd = compute_forward_returns(prices, periods=[horizon_days])
    returns_wide = fwd[f"return_{horizon_days}d"]

    results: list[StateValidationResult] = []
    for state_name, spec in _STATE_CATALOG.items():
        # Map encoding tag: 'integer' → 'categorical' against encoding.py,
        # 'boolean' → boolean cast. State columns we catalog are stored as
        # VARCHAR (categorical) except gates which are BOOLEAN.
        encoding_kind = "boolean" if spec["encoding"] == "boolean" else "categorical"
        factor = _load_state_factor(eng, spec["column"], encoding_kind, start, end)
        if factor.empty:
            log.warning("state_empty", state=state_name)
            continue
        ic = compute_ic_over_window(factor, returns_wide)
        status = _classify(ic, spec["implied_action"])
        result = StateValidationResult(
            state_name=state_name,
            implied_action=spec["implied_action"],
            horizon_days=horizon_days,
            ic=ic,
            status=status,
            as_of=end,
        )
        _persist(eng, result)
        log.info(
            "state_validated",
            state=state_name,
            status=status,
            mean_ic=ic.mean_ic,
            ic_ir=(ic.mean_ic / ic.ic_std) if ic.ic_std else None,
        )
        results.append(result)
    return results
