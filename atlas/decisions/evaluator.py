"""Pure cell-rule evaluator.

Takes a scorecard row + regime state + parsed cell definition; returns a
structured :class:`EvaluationResult` indicating whether the cell *triggers*
on that row, and (if not) which predicate vetoed.

Two functions:

* :func:`evaluate_cell` — single (row, cell, regime) → :class:`EvaluationResult`.
  Eligibility predicates evaluated first (early-return on first failure),
  then entry predicates (early-return on first failure). Cross-section
  ``in_top_quantile`` predicates require precomputed per-feature ranks
  (passed in via ``feature_rank_pcts``); without them a quantile predicate
  returns hit=False with a clear reason.

* :func:`evaluate_all_cells` — full cross-product (rows × cells) at one
  date. Pre-computes per-feature percentile ranks ONCE per date and
  threads them through ``evaluate_cell`` so the cross-section quantile
  comparisons are vectorised at the date level (not per cell).

Hit semantics
-------------
A cell *hits* on a row when ALL eligibility predicates AND all entry
predicates evaluate true. Regime gating (``cell_active_in_regime``) is
RECORDED on the result but does NOT veto the hit — the cron uses both
``hit=True`` AND ``cell_active_in_regime=True`` to decide whether to
write a row. Per CONTEXT.md the cell can still be "in the call" while
regime-gated; the gating is surfaced for transparency.

Confidence values
-----------------
``confidence_unconditional`` is read from ``cell.confidence_unconditional``
(set by the walk-forward run). ``confidence_regime_conditional`` is read
from ``cell.confidence_by_regime[regime_state]`` when that mapping exists.
A regime-conditional confidence below the **55% gate** flips
``cell_active_in_regime`` to ``False`` (per /grill-with-docs Q5 + the v6
methodology lock §"Per-regime confidence floor").

NULL handling
-------------
A scorecard row with a NULL feature value fails any predicate that
references that feature — the missing data is conservative. Quantile
predicates with insufficient cross-section data (< quantile_n eligible
rows) also fail conservatively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate, validate_rule_dsl
from atlas.regime.classifier import RegimeState

# 55% gate for cell_active_in_regime (per /grill-with-docs Q5 +
# methodology lock §"Per-regime confidence floor").
REGIME_CONFIDENCE_GATE = Decimal("0.55")


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome of evaluating one cell against one scorecard row.

    Attributes:
        cell_id: the cell's UUID (from ``atlas_cell_definitions.cell_id``).
        instrument_id: the instrument's UUID-as-string (matches the
            scorecard row's ``instrument_id``).
        hit: ``True`` iff every eligibility AND entry predicate passed.
        failed_predicate: when ``hit=False``, the predicate that vetoed.
            ``None`` when ``hit=True`` or when the cell had no predicates
            but failed for a different reason (e.g. missing required field).
        veto_stage: ``"eligibility"`` / ``"entry"`` / ``None`` — which
            predicate list the veto came from.
        confidence_unconditional: from ``cell.confidence_unconditional``.
            ``None`` when the walk-forward hasn't populated it (placeholder
            cells from migration 089).
        confidence_regime_conditional: from
            ``cell.confidence_by_regime[regime_state]``. ``None`` when no
            per-regime conditional confidence is recorded.
        cell_active_in_regime: ``True`` unless ``confidence_regime_conditional``
            is below :data:`REGIME_CONFIDENCE_GATE` (55%).
    """

    cell_id: UUID
    instrument_id: str
    hit: bool
    failed_predicate: FeaturePredicate | None
    veto_stage: str | None
    confidence_unconditional: Decimal | None
    confidence_regime_conditional: Decimal | None
    cell_active_in_regime: bool


# ---------------------------------------------------------------------------
# Predicate evaluation primitives
# ---------------------------------------------------------------------------


def _to_decimal(value: object) -> Decimal | None:
    """Coerce a scorecard cell to ``Decimal`` for predicate comparison.

    Returns ``None`` for NULL / NaN / Inf (which the caller treats as a
    failed predicate — missing data is conservative).
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    # Anything else (str from JSONB, numpy scalar, etc.) — best effort.
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _eval_scalar_cmp(
    feature_value: Decimal,
    cmp: str,
    target: Decimal,
) -> bool:
    """Evaluate ``feature_value <cmp> target`` for the 5 scalar operators."""
    if cmp == ">":
        return feature_value > target
    if cmp == ">=":
        return feature_value >= target
    if cmp == "<":
        return feature_value < target
    if cmp == "<=":
        return feature_value <= target
    if cmp == "==":
        return feature_value == target
    raise ValueError(f"_eval_scalar_cmp: unsupported cmp {cmp!r}")


def _eval_predicate(
    predicate: FeaturePredicate,
    row: Mapping[str, Any],
    *,
    feature_rank_pcts: Mapping[str, Mapping[str, float]] | None = None,
    instrument_id: str | None = None,
) -> bool:
    """Evaluate one :class:`FeaturePredicate` against one scorecard row.

    Args:
        predicate: the predicate to evaluate.
        row: the scorecard row as a mapping (e.g. dict or pd.Series).
        feature_rank_pcts: per-date precomputed percentile-ranks, keyed
            ``feature → instrument_id → rank_pct``. Required for
            ``in_top_quantile``; ignored otherwise.
        instrument_id: the row's ``instrument_id`` — required when the
            predicate uses ``in_top_quantile`` so the rank lookup
            ties back to the right instrument.

    Returns:
        ``True`` if the predicate passes, ``False`` otherwise (incl. NULL
        feature, missing rank map, or out-of-range quantile).
    """
    feature = predicate.feature
    cmp = predicate.cmp

    raw = row.get(feature)
    feature_value = _to_decimal(raw)

    if cmp == "in_top_quantile":
        # Requires precomputed cross-section ranks. Without them, fail
        # conservatively — caller signalled they need quantile eval but
        # didn't supply the ranks (test / unit-test ergonomics).
        if feature_rank_pcts is None or instrument_id is None:
            return False
        rank_map = feature_rank_pcts.get(feature)
        if rank_map is None:
            return False
        rank_pct = rank_map.get(instrument_id)
        if rank_pct is None or np.isnan(rank_pct):
            return False
        n = predicate.value_quantile_n
        if n is None or n < 2:
            return False
        # "Top quantile" — within the highest 1/N fraction by rank.
        # rank_pct is in (0, 1]; rank_pct > 1 - 1/N is the top 1/N.
        return rank_pct > (1.0 - 1.0 / float(n))

    if cmp == "in_range":
        if not isinstance(predicate.value, tuple):
            return False
        low, high = predicate.value
        if feature_value is None:
            return False
        return (feature_value >= low) and (feature_value <= high)

    # Scalar comparisons
    if feature_value is None:
        return False
    target = predicate.value
    if isinstance(target, tuple):
        # Schema validator should have prevented this, but be defensive.
        return False
    return _eval_scalar_cmp(feature_value, cmp, target)


# ---------------------------------------------------------------------------
# Cell-level evaluation
# ---------------------------------------------------------------------------


def _parse_cell_rule(cell: Mapping[str, Any]) -> CellRule:
    """Pull the ``rule_dsl`` out of a cell row and validate.

    Accepts either a pre-parsed dict (``rule_dsl`` already JSON-decoded —
    typical when the row came from a JSONB column via psycopg2) or a raw
    :class:`CellRule` instance (cache-friendly).
    """
    rule = cell.get("rule_dsl")
    if isinstance(rule, CellRule):
        return rule
    if isinstance(rule, Mapping):
        return validate_rule_dsl(dict(rule))
    raise ValueError(f"cell.rule_dsl must be a dict or CellRule; got {type(rule).__name__}")


def _compute_active_in_regime(
    cell: Mapping[str, Any],
    regime_state: RegimeState | str,
) -> tuple[Decimal | None, bool]:
    """Compute ``(confidence_regime_conditional, cell_active_in_regime)``.

    ``cell.confidence_by_regime`` is a JSONB mapping from regime name
    (e.g. ``"Risk-On"``) to a confidence value (Decimal or float). When
    that mapping is present AND has an entry for the active regime, the
    confidence is returned and gated against :data:`REGIME_CONFIDENCE_GATE`.

    When the mapping is missing / regime absent / value malformed:
    ``cell_active_in_regime`` defaults to ``True`` (the cell is treated
    as regime-neutral — the walk-forward has not characterised it per
    regime). This matches the placeholder rows from migration 089 where
    ``confidence_by_regime`` is NULL.
    """
    raw = cell.get("confidence_by_regime")
    if not isinstance(raw, Mapping):
        return None, True

    regime_key = regime_state.value if isinstance(regime_state, RegimeState) else str(regime_state)
    value = raw.get(regime_key)
    if value is None:
        return None, True

    conf = _to_decimal(value)
    if conf is None:
        return None, True

    return conf, conf >= REGIME_CONFIDENCE_GATE


def evaluate_cell(
    scorecard_row: Mapping[str, Any],
    regime_state: RegimeState | str,
    cell: Mapping[str, Any],
    *,
    feature_rank_pcts: Mapping[str, Mapping[str, float]] | None = None,
) -> EvaluationResult:
    """Evaluate one cell against one scorecard row.

    Args:
        scorecard_row: row from ``atlas_scorecard_daily`` as a mapping
            (must include ``instrument_id`` and every feature referenced
            by the cell's predicates).
        regime_state: the active :class:`atlas.regime.RegimeState` (or its
            string value).
        cell: row from ``atlas_cell_definitions`` as a mapping. ``rule_dsl``
            may be a dict or a pre-parsed :class:`CellRule`.
        feature_rank_pcts: pre-computed cross-section ranks per feature
            (required for any ``in_top_quantile`` predicate). See
            :func:`evaluate_all_cells` for the production caller that
            computes these.

    Returns:
        :class:`EvaluationResult`.
    """
    rule = _parse_cell_rule(cell)
    instrument_id = str(scorecard_row.get("instrument_id"))
    cell_id_raw = cell.get("cell_id")
    cell_id = cell_id_raw if isinstance(cell_id_raw, UUID) else UUID(str(cell_id_raw))

    confidence_unconditional = _to_decimal(cell.get("confidence_unconditional"))
    confidence_regime, cell_active_in_regime = _compute_active_in_regime(cell, regime_state)

    # Eligibility — first-failure early return.
    for predicate in rule.eligibility:
        if not _eval_predicate(
            predicate,
            scorecard_row,
            feature_rank_pcts=feature_rank_pcts,
            instrument_id=instrument_id,
        ):
            return EvaluationResult(
                cell_id=cell_id,
                instrument_id=instrument_id,
                hit=False,
                failed_predicate=predicate,
                veto_stage="eligibility",
                confidence_unconditional=confidence_unconditional,
                confidence_regime_conditional=confidence_regime,
                cell_active_in_regime=cell_active_in_regime,
            )

    # Entry — first-failure early return.
    for predicate in rule.entry:
        if not _eval_predicate(
            predicate,
            scorecard_row,
            feature_rank_pcts=feature_rank_pcts,
            instrument_id=instrument_id,
        ):
            return EvaluationResult(
                cell_id=cell_id,
                instrument_id=instrument_id,
                hit=False,
                failed_predicate=predicate,
                veto_stage="entry",
                confidence_unconditional=confidence_unconditional,
                confidence_regime_conditional=confidence_regime,
                cell_active_in_regime=cell_active_in_regime,
            )

    return EvaluationResult(
        cell_id=cell_id,
        instrument_id=instrument_id,
        hit=True,
        failed_predicate=None,
        veto_stage=None,
        confidence_unconditional=confidence_unconditional,
        confidence_regime_conditional=confidence_regime,
        cell_active_in_regime=cell_active_in_regime,
    )


# ---------------------------------------------------------------------------
# Cross-product evaluation (vectorised cross-section)
# ---------------------------------------------------------------------------


def _precompute_rank_pcts(
    scorecard_rows: Sequence[Mapping[str, Any]],
    features: set[str],
) -> dict[str, dict[str, float]]:
    """Precompute per-feature cross-section percentile rank.

    Each feature in ``features`` gets a mapping ``instrument_id → rank_pct``,
    where ``rank_pct`` is ``pandas.rank(pct=True, method="average")``. NaN
    feature values produce NaN ranks (which the evaluator treats as
    "no rank — predicate fails").

    Computed ONCE per date — not once per cell — which is the load-bearing
    perf characteristic of the cross-product evaluator.
    """
    if not features or not scorecard_rows:
        return {}

    df = pd.DataFrame(list(scorecard_rows))
    if "instrument_id" not in df.columns:
        return {}
    df["instrument_id"] = df["instrument_id"].astype(str)

    out: dict[str, dict[str, float]] = {}
    for feat in features:
        if feat not in df.columns:
            out[feat] = {}
            continue
        series = pd.Series(pd.to_numeric(df[feat], errors="coerce"))
        ranks = series.rank(pct=True, method="average")
        out[feat] = {str(iid): float(r) for iid, r in zip(df["instrument_id"], ranks, strict=True)}
    return out


def _quantile_features_in_cells(cells: Sequence[Mapping[str, Any]]) -> set[str]:
    """Collect the set of features used in any ``in_top_quantile`` predicate."""
    out: set[str] = set()
    for cell in cells:
        try:
            rule = _parse_cell_rule(cell)
        except (ValueError, TypeError):
            # Malformed cell — skipped by caller; safe to ignore here.
            continue
        for predicate in (*rule.eligibility, *rule.entry):
            if predicate.cmp == "in_top_quantile":
                out.add(predicate.feature)
    return out


def evaluate_all_cells(
    scorecard_rows: Sequence[Mapping[str, Any]],
    cells: Sequence[Mapping[str, Any]],
    regime: RegimeState | str,
) -> list[EvaluationResult]:
    """Evaluate every cell against every scorecard row (cross-product).

    Pre-computes per-feature percentile ranks once at the date level, then
    threads them through ``evaluate_cell``. Output is the flat list of all
    ``(row × cell)`` evaluation results — caller filters by ``hit=True``.

    Args:
        scorecard_rows: rows from ``atlas_scorecard_daily`` at one date.
        cells: rows from ``atlas_cell_definitions`` (already filtered by
            ``deprecated_at IS NULL`` upstream).
        regime: the active regime at the same date.

    Returns:
        Flat list of :class:`EvaluationResult`. Order is
        ``[(row_0, cell_0), (row_0, cell_1), …, (row_n, cell_m)]``.
    """
    if not scorecard_rows or not cells:
        return []

    quantile_features = _quantile_features_in_cells(cells)
    rank_pcts = _precompute_rank_pcts(scorecard_rows, quantile_features)

    out: list[EvaluationResult] = []
    for row in scorecard_rows:
        for cell in cells:
            out.append(
                evaluate_cell(
                    row,
                    regime,
                    cell,
                    feature_rank_pcts=rank_pcts,
                )
            )
    return out


__all__ = [
    "REGIME_CONFIDENCE_GATE",
    "EvaluationResult",
    "evaluate_all_cells",
    "evaluate_cell",
]
