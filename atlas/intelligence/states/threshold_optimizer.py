"""IC-validation threshold optimizer for state-engine θ values.

Single-threshold sensitivity sweep: for one threshold at a time, evaluate
the IC of "stock is in the would-be state under candidate θ" against
forward returns, and pick the θ that maximizes risk-adjusted predictive
power.

Reuses atlas/intelligence/validation/ic_engine.py.

Public API:
  tune_single_threshold(threshold_name, state, factor, returns_wide,
                         candidates, as_of) -> ThresholdTuningResult
  apply_tuned_threshold(engine, result) -> None  (persists to DB)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.validation.ic_engine import compute_ic_over_window

log = structlog.get_logger()

# Classification gates: a candidate passes if IR > 0.4 AND |q5_q1| > 0.005.
_IR_THRESHOLD = 0.4
_Q5_Q1_MIN_ABS = 0.005


@dataclass
class ThresholdTuningResult:
    """Outcome of tuning one threshold over a candidate grid."""

    threshold_name: str
    state: str
    as_of: date
    optimal_value: float | None
    per_candidate_ic: dict[float, dict[str, Any]] = field(default_factory=dict)
    passed_gates: bool = False
    notes: str = ""

    @property
    def ic_ir(self) -> float:
        """IC IR of the optimal candidate (0.0 if no optimal found)."""
        if self.optimal_value is None:
            return 0.0
        entry = self.per_candidate_ic.get(float(self.optimal_value), {})
        return float(entry.get("ic_ir", 0.0))


def _build_state_membership(factor: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    """For a continuous factor, return 1/0 indicator of 'factor >= cutoff'.

    Output DataFrame has same MultiIndex (date, instrument_id) as input +
    a 'factor' column suitable for compute_ic_over_window.
    """
    out = factor.copy()
    out["factor"] = (factor["factor"] >= cutoff).astype(float)
    return out


def _quantile_spread(factor: pd.DataFrame, returns_wide: pd.DataFrame) -> float:
    """Q5–Q1 spread when factor is binary (1 = in-state, 0 = out-of-state).

    Computes mean per-date return differential between factor==1 group
    and factor==0 group. Equivalent to Q2–Q1 spread for a binary factor.

    Returns NaN if insufficient data.
    """
    if factor.empty or returns_wide.empty:
        return float("nan")

    long_ret = returns_wide.stack()
    long_ret.name = "fwd_return"
    long_ret.index = long_ret.index.set_names(["date", "instrument_id"])
    joined = factor.join(long_ret, how="inner").dropna()

    if joined.empty or joined["factor"].nunique() < 2:
        return float("nan")

    diffs: list[float] = []
    for _dt, group in joined.groupby(level="date"):
        if group["factor"].nunique() < 2:
            continue
        top = group.loc[group["factor"] == 1.0, "fwd_return"].mean()
        bot = group.loc[group["factor"] == 0.0, "fwd_return"].mean()
        if pd.isna(top) or pd.isna(bot):
            continue
        diffs.append(float(top - bot))

    return float(np.mean(diffs)) if diffs else float("nan")


def _safe_float(val: float) -> float:
    """Convert a potentially NaN/inf float to a safe 0.0 for storage."""
    if np.isnan(val) or np.isinf(val):
        return 0.0
    return float(val)


def tune_single_threshold(
    threshold_name: str,
    state: str,
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
    candidates: list[float],
    as_of: date,
) -> ThresholdTuningResult:
    """Sweep candidate thresholds, return best.

    Args:
        threshold_name: e.g., 'theta_rs'
        state: e.g., 'stage_2a' (used only for bookkeeping)
        factor: MultiIndex (date, instrument_id), column 'factor' = the
                continuous metric being thresholded (e.g., rs_rank_12m).
        returns_wide: DataFrame indexed by date, columns=instrument_id,
                values = forward returns at the natural horizon.
        candidates: ordered list of candidate threshold values to evaluate.
        as_of: the date stamp to write to atlas_state_thresholds.

    Returns:
        ThresholdTuningResult with per-candidate IC metrics + optimal_value
        (selected by max Q5-Q1 spread among those passing IR+spread gates;
        falls back to max |IR| if no candidate passes).
    """
    if factor.empty or returns_wide.empty:
        return ThresholdTuningResult(
            threshold_name=threshold_name,
            state=state,
            as_of=as_of,
            optimal_value=None,
            notes="empty factor or returns",
        )

    per_candidate: dict[float, dict[str, Any]] = {}

    for cutoff in candidates:
        membership = _build_state_membership(factor, cutoff)
        ic = compute_ic_over_window(membership, returns_wide)

        mean_ic = _safe_float(ic.mean_ic)
        ic_std = _safe_float(ic.ic_std)
        ic_t_stat = _safe_float(ic.ic_t_stat)

        ir = (mean_ic / ic_std) if ic_std > 0 else 0.0
        q5_q1 = _quantile_spread(membership, returns_wide)

        per_candidate[float(cutoff)] = {
            "mean_ic": mean_ic,
            "ic_std": ic_std,
            "ic_t_stat": ic_t_stat,
            "ic_ir": float(ir),
            "q5_q1_spread": _safe_float(q5_q1),
            "n_observations": int(ic.n_observations),
        }

    log.debug(
        "tune_single_threshold_sweep_complete",
        threshold=threshold_name,
        state=state,
        n_candidates=len(candidates),
    )

    # Pick the candidate that passes gates AND has max Q5-Q1 spread.
    passing = {
        c: m
        for c, m in per_candidate.items()
        if abs(m["ic_ir"]) > _IR_THRESHOLD and abs(m["q5_q1_spread"]) > _Q5_Q1_MIN_ABS
    }

    if passing:
        optimal = max(passing, key=lambda c: abs(passing[c]["q5_q1_spread"]))
        passed = True
        notes = ""
    else:
        # Fallback: max |IR| among all candidates (informational; gates failed)
        if per_candidate:
            optimal = max(per_candidate, key=lambda c: abs(per_candidate[c]["ic_ir"]))
        else:
            optimal = None
        passed = False
        notes = "no candidate passed IR>0.4 + |q5_q1|>0.005 gates; optimal is max-IR fallback"

    log.info(
        "tune_single_threshold_done",
        threshold=threshold_name,
        state=state,
        optimal=optimal,
        passed_gates=passed,
        notes=notes or "gates passed",
    )

    return ThresholdTuningResult(
        threshold_name=threshold_name,
        state=state,
        as_of=as_of,
        optimal_value=optimal,
        per_candidate_ic=per_candidate,
        passed_gates=passed,
        notes=notes,
    )


def apply_tuned_threshold(engine: Engine, result: ThresholdTuningResult) -> None:
    """Persist a tuning result: deactivate prior active row, insert new active row.

    No-op if result.optimal_value is None. Uses ON CONFLICT DO UPDATE for
    idempotent reruns (same threshold_name + state + as_of_date).
    """
    if result.optimal_value is None:
        log.warning(
            "apply_tuned_threshold_skip_no_optimal",
            threshold=result.threshold_name,
            state=result.state,
        )
        return

    best = result.per_candidate_ic.get(float(result.optimal_value), {})

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE atlas.atlas_state_thresholds
                SET active = FALSE
                WHERE threshold_name = :tn
                  AND state_or_gate = :sg
                  AND active = TRUE
            """),
            {"tn": result.threshold_name, "sg": result.state},
        )
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_state_thresholds
                    (threshold_name, state_or_gate, threshold_value,
                     ic_at_threshold, ic_ir_at_threshold, q5_q1_spread,
                     as_of_date, active)
                VALUES (:tn, :sg, :v, :ic, :ir, :q, :d, TRUE)
                ON CONFLICT (threshold_name, state_or_gate, as_of_date)
                DO UPDATE SET
                    threshold_value     = EXCLUDED.threshold_value,
                    ic_at_threshold     = EXCLUDED.ic_at_threshold,
                    ic_ir_at_threshold  = EXCLUDED.ic_ir_at_threshold,
                    q5_q1_spread        = EXCLUDED.q5_q1_spread,
                    active              = TRUE
            """),
            {
                "tn": result.threshold_name,
                "sg": result.state,
                "v": float(result.optimal_value),
                "ic": float(best.get("mean_ic", 0.0)),
                "ir": float(best.get("ic_ir", 0.0)),
                "q": float(best.get("q5_q1_spread", 0.0)),
                "d": result.as_of,
            },
        )

    log.info(
        "apply_tuned_threshold",
        threshold=result.threshold_name,
        state=result.state,
        value=result.optimal_value,
        passed_gates=result.passed_gates,
    )
