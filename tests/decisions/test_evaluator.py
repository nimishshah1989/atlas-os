"""Tests for ``atlas.decisions.evaluator`` — pure rule evaluator."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from atlas.decisions.evaluator import (
    REGIME_CONFIDENCE_GATE,
    _eval_predicate,
    _precompute_rank_pcts,
    evaluate_all_cells,
    evaluate_cell,
)
from atlas.decisions.rule_dsl import FeaturePredicate
from atlas.regime.classifier import RegimeState

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_cell(
    *,
    rule_type: str = "pullback",
    tier: str = "Mid",
    action: str = "POSITIVE",
    tenure: str = "6m",
    eligibility: list[dict[str, Any]] | None = None,
    entry: list[dict[str, Any]] | None = None,
    confidence_unconditional: Decimal | None = None,
    confidence_by_regime: dict[str, Decimal] | None = None,
    cell_id: object | None = None,
) -> dict[str, Any]:
    rule_dsl = {
        "rule_type": rule_type,
        "eligibility": eligibility or [],
        "entry": entry or [],
        "tier": tier,
        "action": action,
        "tenure": tenure,
        "methodology_lock_ref": "TEST_LOCK",
    }
    return {
        "cell_id": cell_id or uuid4(),
        "cap_tier": tier,
        "action": action,
        "tenure": tenure,
        "rule_dsl": rule_dsl,
        "confidence_unconditional": confidence_unconditional,
        "confidence_by_regime": confidence_by_regime,
    }


def _make_scorecard_row(
    instrument_id: str = "instr-001",
    **features: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "instrument_id": instrument_id,
        "scorecard_id": uuid4(),
        "cap_tier": "Mid",
        "rs_residual_6m": Decimal("0.10"),
        "log_med_tv_60d": Decimal("16.0"),
        "realized_vol_60d": Decimal("0.25"),
        "formation_max_dd": Decimal("0.15"),
        "listing_age_days": 1200,
        "log_price": Decimal("6.5"),
    }
    defaults.update(features)
    return defaults


# ---------------------------------------------------------------------------
# Predicate primitive — _eval_predicate
# ---------------------------------------------------------------------------


def test_eval_predicate_scalar_gt_passes() -> None:
    p = FeaturePredicate(feature="rs_residual_6m", cmp=">", value=Decimal("0.05"))
    row = _make_scorecard_row(rs_residual_6m=Decimal("0.10"))
    assert _eval_predicate(p, row) is True


def test_eval_predicate_scalar_gt_fails() -> None:
    p = FeaturePredicate(feature="rs_residual_6m", cmp=">", value=Decimal("0.20"))
    row = _make_scorecard_row(rs_residual_6m=Decimal("0.10"))
    assert _eval_predicate(p, row) is False


def test_eval_predicate_null_feature_fails_conservatively() -> None:
    """NULL feature → predicate fails (no silent True from missing data)."""
    p = FeaturePredicate(feature="rs_residual_6m", cmp=">", value=Decimal("0"))
    row = _make_scorecard_row(rs_residual_6m=None)
    assert _eval_predicate(p, row) is False


def test_eval_predicate_in_range_inside_passes() -> None:
    p = FeaturePredicate(
        feature="realized_vol_60d",
        cmp="in_range",
        value=(Decimal("0.10"), Decimal("0.40")),
    )
    row = _make_scorecard_row(realized_vol_60d=Decimal("0.25"))
    assert _eval_predicate(p, row) is True


def test_eval_predicate_in_range_outside_fails() -> None:
    p = FeaturePredicate(
        feature="realized_vol_60d",
        cmp="in_range",
        value=(Decimal("0.10"), Decimal("0.40")),
    )
    row = _make_scorecard_row(realized_vol_60d=Decimal("0.45"))
    assert _eval_predicate(p, row) is False


def test_eval_predicate_in_top_quantile_needs_precomputed_ranks() -> None:
    """Without rank pcts the predicate fails — no silent path."""
    p = FeaturePredicate(
        feature="rs_residual_6m",
        cmp="in_top_quantile",
        value=Decimal("1"),
        value_quantile_n=5,
    )
    row = _make_scorecard_row()
    assert _eval_predicate(p, row) is False


def test_eval_predicate_in_top_quantile_passes_when_in_top_quintile() -> None:
    p = FeaturePredicate(
        feature="rs_residual_6m",
        cmp="in_top_quantile",
        value=Decimal("1"),
        value_quantile_n=5,
    )
    row = _make_scorecard_row(instrument_id="iid-001")
    ranks = {"rs_residual_6m": {"iid-001": 0.95}}
    assert _eval_predicate(p, row, feature_rank_pcts=ranks, instrument_id="iid-001") is True


def test_eval_predicate_in_top_quantile_fails_when_below_top_quintile() -> None:
    p = FeaturePredicate(
        feature="rs_residual_6m",
        cmp="in_top_quantile",
        value=Decimal("1"),
        value_quantile_n=5,
    )
    row = _make_scorecard_row(instrument_id="iid-001")
    ranks = {"rs_residual_6m": {"iid-001": 0.50}}
    assert _eval_predicate(p, row, feature_rank_pcts=ranks, instrument_id="iid-001") is False


# ---------------------------------------------------------------------------
# evaluate_cell — hits, early returns, regime gating
# ---------------------------------------------------------------------------


def test_evaluate_cell_hit_when_all_predicates_satisfied() -> None:
    cell = _make_cell(
        eligibility=[{"feature": "log_med_tv_60d", "cmp": ">=", "value": Decimal("15")}],
        entry=[
            {"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")},
            {"feature": "formation_max_dd", "cmp": "<", "value": Decimal("0.25")},
        ],
        confidence_unconditional=Decimal("0.62"),
    )
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.hit is True
    assert res.failed_predicate is None
    assert res.veto_stage is None
    assert res.confidence_unconditional == Decimal("0.62")


def test_evaluate_cell_early_return_on_eligibility_failure() -> None:
    """Eligibility veto fires BEFORE entry predicates are evaluated."""
    cell = _make_cell(
        eligibility=[{"feature": "log_med_tv_60d", "cmp": ">=", "value": Decimal("20")}],
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
    )
    row = _make_scorecard_row(log_med_tv_60d=Decimal("16"))  # eligibility fails
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.hit is False
    assert res.veto_stage == "eligibility"
    assert res.failed_predicate is not None
    assert res.failed_predicate.feature == "log_med_tv_60d"


def test_evaluate_cell_early_return_on_entry_failure() -> None:
    cell = _make_cell(
        eligibility=[],
        entry=[
            {"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")},
            {"feature": "formation_max_dd", "cmp": "<", "value": Decimal("0.10")},
        ],
    )
    row = _make_scorecard_row(formation_max_dd=Decimal("0.20"))  # fails 2nd entry
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.hit is False
    assert res.veto_stage == "entry"
    assert res.failed_predicate is not None
    assert res.failed_predicate.feature == "formation_max_dd"


def test_evaluate_cell_no_predicates_hits() -> None:
    """Cell with empty eligibility and entry lists hits trivially."""
    cell = _make_cell(eligibility=[], entry=[])
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.hit is True


def test_evaluate_cell_regime_gating_active_above_55pct() -> None:
    """confidence_by_regime >= 0.55 → cell_active_in_regime=True."""
    cell = _make_cell(
        confidence_by_regime={"Risk-On": Decimal("0.62"), "Risk-Off": Decimal("0.30")},
    )
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.confidence_regime_conditional == Decimal("0.62")
    assert res.cell_active_in_regime is True


def test_evaluate_cell_regime_gating_inactive_below_55pct() -> None:
    """confidence_by_regime < 0.55 → cell_active_in_regime=False."""
    cell = _make_cell(
        confidence_by_regime={"Risk-On": Decimal("0.40")},
    )
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.confidence_regime_conditional == Decimal("0.40")
    assert res.cell_active_in_regime is False


def test_evaluate_cell_regime_gating_defaults_active_when_no_mapping() -> None:
    """No confidence_by_regime → treat as regime-neutral, active=True."""
    cell = _make_cell(confidence_by_regime=None)
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.confidence_regime_conditional is None
    assert res.cell_active_in_regime is True


def test_evaluate_cell_hit_recorded_even_when_regime_gated_off() -> None:
    """Regime gating does NOT veto the hit — it's surfaced separately."""
    cell = _make_cell(
        entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}],
        confidence_by_regime={"Risk-On": Decimal("0.30")},
    )
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.hit is True
    assert res.cell_active_in_regime is False


def test_evaluate_cell_string_regime_state_accepted() -> None:
    """Caller may pass the regime as a string instead of the enum."""
    cell = _make_cell(confidence_by_regime={"Risk-On": Decimal("0.70")})
    row = _make_scorecard_row()
    res = evaluate_cell(row, "Risk-On", cell)
    assert res.cell_active_in_regime is True


def test_evaluate_cell_placeholder_rule_from_migration_089_hits() -> None:
    """The seeded placeholder cells (no predicates) hit on every row."""
    cell = _make_cell(rule_type="placeholder", eligibility=[], entry=[])
    row = _make_scorecard_row()
    res = evaluate_cell(row, RegimeState.RISK_ON, cell)
    assert res.hit is True


def test_regime_confidence_gate_is_55pct() -> None:
    """The gate value is explicitly 0.55 (anchor against accidental drift)."""
    assert REGIME_CONFIDENCE_GATE == Decimal("0.55")


# ---------------------------------------------------------------------------
# evaluate_all_cells — cross-product, rank pre-compute
# ---------------------------------------------------------------------------


def test_evaluate_all_cells_returns_full_cross_product() -> None:
    rows = [
        _make_scorecard_row(instrument_id=f"iid-{i:03d}", rs_residual_6m=Decimal(str(v)))
        for i, v in enumerate([0.10, 0.05, -0.02])
    ]
    cells = [
        _make_cell(entry=[{"feature": "rs_residual_6m", "cmp": ">", "value": Decimal("0.05")}]),
        _make_cell(entry=[{"feature": "rs_residual_6m", "cmp": "<", "value": Decimal("0")}]),
    ]
    results = evaluate_all_cells(rows, cells, RegimeState.RISK_ON)
    assert len(results) == 6  # 3 rows × 2 cells
    hits = [r for r in results if r.hit]
    # iid-000 hits cell-0 (0.10>0.05); iid-002 hits cell-1 (-0.02<0). 2 hits total.
    assert len(hits) == 2


def test_evaluate_all_cells_empty_inputs_short_circuit() -> None:
    assert evaluate_all_cells([], [], RegimeState.RISK_ON) == []
    assert evaluate_all_cells([], [_make_cell()], RegimeState.RISK_ON) == []
    assert evaluate_all_cells([_make_scorecard_row()], [], RegimeState.RISK_ON) == []


def test_evaluate_all_cells_top_quantile_uses_cross_section() -> None:
    """in_top_quantile reads the cross-section computed once at date level."""
    rows = [
        _make_scorecard_row(
            instrument_id=f"iid-{i:03d}",
            rs_residual_6m=Decimal(str(v)),
        )
        for i, v in enumerate([0.30, 0.20, 0.10, 0.05, 0.00, -0.05, -0.10, -0.20, -0.30, -0.40])
    ]
    cells = [
        _make_cell(
            entry=[
                {
                    "feature": "rs_residual_6m",
                    "cmp": "in_top_quantile",
                    "value": Decimal("1"),
                    "value_quantile_n": 5,
                }
            ]
        )
    ]
    results = evaluate_all_cells(rows, cells, RegimeState.RISK_ON)
    hits = [r for r in results if r.hit]
    # 10 instruments, top quintile = top 2 (rank_pct > 0.8). iid-000 (0.30) and
    # iid-001 (0.20) should be in the top quintile.
    hit_ids = {r.instrument_id for r in hits}
    assert "iid-000" in hit_ids
    assert "iid-001" in hit_ids
    # iid-004 (median) must not hit.
    assert "iid-004" not in hit_ids


def test_precompute_rank_pcts_handles_nan_values() -> None:
    """NaN feature values produce NaN ranks (which fail the predicate)."""
    rows = [
        _make_scorecard_row(instrument_id="iid-000", rs_residual_6m=Decimal("0.5")),
        _make_scorecard_row(instrument_id="iid-001", rs_residual_6m=None),
        _make_scorecard_row(instrument_id="iid-002", rs_residual_6m=Decimal("-0.3")),
    ]
    ranks = _precompute_rank_pcts(rows, {"rs_residual_6m"})
    iid001_rank = ranks["rs_residual_6m"]["iid-001"]
    assert iid001_rank != iid001_rank  # NaN != NaN


def test_evaluate_all_cells_ranks_computed_once_no_per_cell_call() -> None:
    """Two cells with in_top_quantile share one cross-section computation.

    Verified indirectly: passing the same rows to two cells with identical
    in_top_quantile predicates yields identical pass/fail status per
    instrument across both cells.
    """
    rows = [
        _make_scorecard_row(
            instrument_id=f"iid-{i:03d}",
            rs_residual_6m=Decimal(str(v)),
        )
        for i, v in enumerate([0.30, 0.20, 0.10, 0.05, 0.00])
    ]
    cells = [
        _make_cell(
            entry=[
                {
                    "feature": "rs_residual_6m",
                    "cmp": "in_top_quantile",
                    "value": Decimal("1"),
                    "value_quantile_n": 5,
                }
            ]
        )
        for _ in range(2)
    ]
    results = evaluate_all_cells(rows, cells, RegimeState.RISK_ON)
    # 5 rows × 2 cells = 10 results, exactly the same hit pattern across cells.
    by_iid_cell: dict[str, list[bool]] = {}
    for r in results:
        by_iid_cell.setdefault(r.instrument_id, []).append(r.hit)
    for iid, hits in by_iid_cell.items():
        assert hits[0] == hits[1], f"iid {iid}: cell hits diverge {hits}"


# ---------------------------------------------------------------------------
# Invalid input handling
# ---------------------------------------------------------------------------


def test_evaluate_cell_raises_on_malformed_rule_dsl_type() -> None:
    cell = _make_cell()
    cell["rule_dsl"] = 42  # not a dict / CellRule
    with pytest.raises(ValueError):
        evaluate_cell(_make_scorecard_row(), RegimeState.RISK_ON, cell)
