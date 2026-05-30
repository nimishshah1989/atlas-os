"""Tests for atlas.decisions.cron row construction.

Regression guard for A1: the signal_calls writer must populate predicted_excess
from the cell's friction_adjusted_excess — without it the frontend "Expected"
column renders em-dashes for every call.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from atlas.decisions.cron import SIGNAL_CALL_COLUMNS, _build_signal_row
from atlas.decisions.evaluator import EvaluationResult
from atlas.regime.classifier import RegimeState


def _result(cell_id) -> EvaluationResult:
    return EvaluationResult(
        cell_id=cell_id,
        instrument_id=str(uuid4()),
        hit=True,
        failed_predicate=None,
        veto_stage=None,
        confidence_unconditional=Decimal("0.71"),
        confidence_regime_conditional=None,
        cell_active_in_regime=True,
    )


def _scorecard() -> dict:
    return {"scorecard_id": str(uuid4()), "instrument_id": str(uuid4()), "cap_tier": "Mid"}


def test_predicted_excess_set_from_cell() -> None:
    cell_id = uuid4()
    cell = {
        "cell_id": cell_id,
        "tenure": "12m",
        "action": "POSITIVE",
        "friction_adjusted_excess": Decimal("0.9357"),
    }
    row = _build_signal_row(
        _result(cell_id),
        scorecard_row=_scorecard(),
        cell=cell,
        regime=RegimeState.ELEVATED,
        target_date=date(2026, 5, 29),
    )
    idx = SIGNAL_CALL_COLUMNS.index("predicted_excess")
    assert row[idx] == Decimal("0.9357")  # cell's friction-adjusted excess


def test_predicted_excess_null_when_cell_lacks_it() -> None:
    cell_id = uuid4()
    cell = {"cell_id": cell_id, "tenure": "6m", "action": "POSITIVE"}  # no excess
    row = _build_signal_row(
        _result(cell_id),
        scorecard_row=_scorecard(),
        cell=cell,
        regime=RegimeState.ELEVATED,
        target_date=date(2026, 5, 29),
    )
    idx = SIGNAL_CALL_COLUMNS.index("predicted_excess")
    assert row[idx] is None  # nullable — no fabricated value
