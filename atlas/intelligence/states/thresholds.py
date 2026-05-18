"""Load active threshold values from atlas.atlas_state_thresholds.

The classifier never hardcodes thresholds. Every θ comes from the DB.
The threshold optimizer (Phase 2) writes new values; the classifier reads
the active row per (threshold_name, state_or_gate).

The partial unique index on (threshold_name, state_or_gate) WHERE active=TRUE
(from migration 074) guarantees at most one active row per key.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ThresholdValue:
    """One active threshold row, with its IC characteristics if tuned."""

    value: float
    ic_at_threshold: float | None
    ic_ir_at_threshold: float | None


def load_active_thresholds(engine: Engine) -> dict[tuple[str, str], ThresholdValue]:
    """Return {(threshold_name, state_or_gate): ThresholdValue} for all active rows."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT threshold_name, state_or_gate, threshold_value,
                       ic_at_threshold, ic_ir_at_threshold
                FROM atlas.atlas_state_thresholds
                WHERE active = TRUE
            """)
        ).fetchall()
    return {
        (r.threshold_name, r.state_or_gate): ThresholdValue(
            value=float(r.threshold_value),
            ic_at_threshold=(float(r.ic_at_threshold) if r.ic_at_threshold is not None else None),
            ic_ir_at_threshold=(
                float(r.ic_ir_at_threshold) if r.ic_ir_at_threshold is not None else None
            ),
        )
        for r in rows
    }


def get(
    thresholds: dict[tuple[str, str], ThresholdValue],
    name: str,
    state: str,
    default: float | None = None,
) -> float:
    """Lookup threshold value. Returns default if missing and default given; else KeyError."""
    key = (name, state)
    if key in thresholds:
        return thresholds[key].value
    if default is None:
        raise KeyError(f"missing threshold: {key}")
    return default
