from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.conviction.optimization.smoothing import DEFAULT_LAMBDA
from atlas.intelligence.cts.hit_rate import compute_hit_rate

log = structlog.get_logger()

MATERIAL_LIFT_DELTA = Decimal("0.05")
SMOOTHING_ALPHA = DEFAULT_LAMBDA  # Decimal("0.15") — same 15% blend rate

CALIBRATABLE_PARAMS: dict[str, dict[str, Any]] = {
    "cts_ppc_range_multiplier": {"step": 0.1, "min": 1.2, "max": 2.5},
    "cts_ppc_volume_multiplier": {"step": 0.1, "min": 1.2, "max": 3.0},
    "cts_ppc_close_pct": {"step": 0.05, "min": 0.50, "max": 0.80},
    "cts_npc_range_multiplier": {"step": 0.1, "min": 1.2, "max": 2.5},
    "cts_npc_volume_multiplier": {"step": 0.1, "min": 1.2, "max": 3.0},
    "cts_contraction_resistance_pct": {"step": 0.5, "min": 1.0, "max": 8.0},
}

MIN_SIGNAL_COUNT = 30


def generate_proposals(
    engine: Engine,
    as_of_date: date,
    thresholds: Mapping[str, Decimal],
) -> list[dict[str, Any]]:
    """Return list of proposal dicts ready for persistence.insert_proposals."""
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        df = pd.read_sql(
            """
            SELECT date, instrument_id, is_ppc, is_npc, is_contraction,
                   stage, trp_ratio, vol_ratio, atr_slope,
                   fwd_ret_20d
            FROM atlas.atlas_cts_signals_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND fwd_ret_20d IS NOT NULL
            """,
            conn,
            params={
                "start": as_of_date - pd.Timedelta(days=90),
                "end": as_of_date,
            },
        )

    if df.empty:
        return []

    proposals = []
    for param_key, spec in CALIBRATABLE_PARAMS.items():
        current_val = float(thresholds.get(param_key, Decimal("0")))
        step = spec["step"]

        current_metrics = compute_hit_rate(
            df,
            signal_col="is_ppc",
            stage_filter=2,
            forward_col="fwd_ret_20d",
            return_threshold=0.05,
        )
        current_lift = float(current_metrics.get("lift_ratio") or 0)

        for direction, candidate_val in [
            ("increase", current_val + step),
            ("decrease", current_val - step),
        ]:
            if not (spec["min"] <= candidate_val <= spec["max"]):
                continue

            df_refiltered = _apply_threshold(df, param_key, candidate_val)
            metrics = compute_hit_rate(
                df_refiltered,
                signal_col="is_ppc",
                stage_filter=2,
                forward_col="fwd_ret_20d",
                return_threshold=0.05,
            )
            if metrics["total_signals"] < MIN_SIGNAL_COUNT:
                continue
            if metrics["lift_ratio"] is None:
                continue

            delta = Decimal(str(metrics["lift_ratio"])) - Decimal(str(current_lift))
            if delta < MATERIAL_LIFT_DELTA:
                continue

            proposed = Decimal(str(candidate_val))
            current = Decimal(str(current_val))
            smoothed = current * (1 - SMOOTHING_ALPHA) + proposed * SMOOTHING_ALPHA

            proposals.append(
                {
                    "as_of_date": as_of_date,
                    "param_key": param_key,
                    "current_value": current,
                    "proposed_value": proposed,
                    "smoothed_value": smoothed,
                    "direction": direction,
                    "expected_lift_delta": delta,
                    "rationale": (
                        f"Lift {direction}s from {current_lift:.3f} to "
                        f"{metrics['lift_ratio']:.3f} (+{float(delta):.3f}) "
                        f"with {metrics['total_signals']} PPC signals on Stage 2."
                    ),
                }
            )
            break  # Only one direction can win per param per day

    return proposals


def _apply_threshold(df: pd.DataFrame, param_key: str, value: float) -> pd.DataFrame:
    """Re-apply a single threshold to re-classify signals in the existing DataFrame."""
    out = df.copy()
    if param_key == "cts_ppc_range_multiplier":
        out["is_ppc"] = out["is_ppc"] & (out["trp_ratio"] >= value)
    elif param_key == "cts_ppc_volume_multiplier":
        out["is_ppc"] = out["is_ppc"] & (out["vol_ratio"] >= value)
    elif param_key == "cts_ppc_close_pct":
        # close_pct not stored in atlas_cts_signals_daily — cannot re-filter; skip silently
        pass
    elif param_key == "cts_npc_range_multiplier":
        out["is_npc"] = out["is_npc"] & (out["trp_ratio"] >= value)
    elif param_key == "cts_npc_volume_multiplier":
        out["is_npc"] = out["is_npc"] & (out["vol_ratio"] >= value)
    elif param_key == "cts_contraction_resistance_pct":
        highest = out["high"].rolling(50, min_periods=50).max() if "high" in out.columns else None
        if highest is not None:
            dist = (highest - out["close"]) / highest.replace(0, pd.NA) * 100
            out["is_contraction"] = out["is_contraction"] & (dist.fillna(999) <= value)
    return out
