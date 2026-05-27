"""Tests for atlas.inference.conviction_tape.

Synthetic-fixture tests (no live DB). Covers:
* verdict logic across the 4 cases (POSITIVE-only, NEGATIVE-only, both, neither)
* conflict-flag set when both directions fire
* ELI5 propagation from the firing rule
* SQL UPSERT emission shape
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate
from atlas.inference.conviction_tape import (
    CandidateRow,
    _decide_verdict,
    compute_conviction_for_snapshot,
    emit_upsert_sql,
)


def _candidate(
    candidate_id: str,
    action: str,
    fric_adj: float,
    tenure: str = "3m",
    cap_tier: str = "Large",
    archetype: str = "quality_momentum",
    eligibility_pred: tuple[str, str, float] | None = None,
    entry_pred: tuple[str, str, float] | None = None,
) -> CandidateRow:
    """Build a synthetic CandidateRow with one entry + one eligibility predicate."""
    eligibility: list[FeaturePredicate] = []
    if eligibility_pred is not None:
        f, c, v = eligibility_pred
        eligibility.append(
            FeaturePredicate(feature=f, cmp=c, value=Decimal(str(v)))  # type: ignore[arg-type]
        )
    entry: list[FeaturePredicate] = []
    if entry_pred is not None:
        f, c, v = entry_pred
        entry.append(
            FeaturePredicate(feature=f, cmp=c, value=Decimal(str(v)))  # type: ignore[arg-type]
        )
    rule = CellRule(
        rule_type="placeholder",
        eligibility=eligibility,
        entry=entry,
        tier=cap_tier,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        tenure=tenure,  # type: ignore[arg-type]
        rule_version=1,
        methodology_lock_ref="TEST",
        notes=f"name=X | archetype={archetype} | rank=1",
    )
    return CandidateRow(
        candidate_id=candidate_id,
        cell_definition_id=f"cell-{candidate_id}",
        cap_tier=cap_tier,
        action=action,
        tenure=tenure,  # type: ignore[arg-type]
        rule=rule,
        ic=Decimal("0.10"),
        friction_adjusted_excess=Decimal(str(fric_adj)),
        archetype=archetype,
    )


# ---------------------------------------------------------------------------
# _decide_verdict
# ---------------------------------------------------------------------------


def test_decide_positive_only() -> None:
    a = _candidate("a", "POSITIVE", 0.2)
    b = _candidate("b", "POSITIVE", 0.5)
    verdict, best, conflict = _decide_verdict([a, b], [])
    assert verdict == "POSITIVE"
    assert best is not None and best.candidate_id == "b"  # higher fric-adj wins
    assert conflict is False


def test_decide_negative_only() -> None:
    a = _candidate("a", "NEGATIVE", -0.1)
    b = _candidate("b", "NEGATIVE", -0.3)
    verdict, best, conflict = _decide_verdict([], [a, b])
    assert verdict == "NEGATIVE"
    assert best is not None and best.candidate_id == "b"  # most negative wins
    assert conflict is False


def test_decide_both_positive_wins_when_magnitude_higher() -> None:
    pos = _candidate("p", "POSITIVE", 0.5)
    neg = _candidate("n", "NEGATIVE", -0.3)
    verdict, best, conflict = _decide_verdict([pos], [neg])
    assert verdict == "POSITIVE"
    assert best is not None and best.candidate_id == "p"
    assert conflict is True


def test_decide_both_negative_wins_when_magnitude_higher() -> None:
    pos = _candidate("p", "POSITIVE", 0.2)
    neg = _candidate("n", "NEGATIVE", -0.4)
    verdict, best, conflict = _decide_verdict([pos], [neg])
    assert verdict == "NEGATIVE"
    assert best is not None and best.candidate_id == "n"
    assert conflict is True


def test_decide_tie_resolves_to_neutral() -> None:
    pos = _candidate("p", "POSITIVE", 0.3)
    neg = _candidate("n", "NEGATIVE", -0.3)
    verdict, best, conflict = _decide_verdict([pos], [neg])
    assert verdict == "NEUTRAL"
    assert best is None
    assert conflict is True


def test_decide_neither_fires_neutral() -> None:
    verdict, best, conflict = _decide_verdict([], [])
    assert verdict == "NEUTRAL"
    assert best is None
    assert conflict is False


# ---------------------------------------------------------------------------
# compute_conviction_for_snapshot
# ---------------------------------------------------------------------------


@pytest.fixture
def candidates_by_key() -> dict[tuple[str, str, str], list[CandidateRow]]:
    """3 candidates: a POSITIVE, a NEGATIVE for Large @ 3m + Large @ 12m positive."""
    return {
        ("Large", "POSITIVE", "3m"): [
            _candidate(
                "pos-3m",
                "POSITIVE",
                0.30,
                tenure="3m",
                entry_pred=("rs_residual_6m", ">", 0.0),
            )
        ],
        ("Large", "NEGATIVE", "3m"): [
            _candidate(
                "neg-3m",
                "NEGATIVE",
                -0.25,
                tenure="3m",
                entry_pred=("rs_residual_6m", "<", 0.0),
            )
        ],
        ("Large", "POSITIVE", "12m"): [
            _candidate(
                "pos-12m",
                "POSITIVE",
                0.40,
                tenure="12m",
                entry_pred=("realized_vol_60d", "<", 0.05),
            )
        ],
    }


def test_three_instruments_full_tenure_sweep(
    candidates_by_key: dict[tuple[str, str, str], list[CandidateRow]],
) -> None:
    """3 instruments × 4 tenures = 12 conviction rows."""
    scorecard_rows: list[dict[str, Any]] = [
        # Instrument 1: positive RS + low vol → POS at 3m AND POS at 12m
        {
            "instrument_id": "iid-1",
            "cap_tier": "Large",
            "rs_residual_6m": Decimal("0.10"),
            "realized_vol_60d": Decimal("0.03"),
        },
        # Instrument 2: negative RS + high vol → NEG at 3m, no signal at 12m
        {
            "instrument_id": "iid-2",
            "cap_tier": "Large",
            "rs_residual_6m": Decimal("-0.10"),
            "realized_vol_60d": Decimal("0.20"),
        },
        # Instrument 3: flat RS → NEUTRAL everywhere
        {
            "instrument_id": "iid-3",
            "cap_tier": "Large",
            "rs_residual_6m": Decimal("0.00"),
            "realized_vol_60d": Decimal("0.20"),
        },
    ]
    rows = compute_conviction_for_snapshot(
        date(2026, 5, 22),
        scorecard_rows=scorecard_rows,
        candidates_by_key=candidates_by_key,
    )
    assert len(rows) == 12  # 3 × 4
    by_iid_tenure = {(r.instrument_id, r.tenure): r for r in rows}

    # Instrument 1
    assert by_iid_tenure[("iid-1", "3m")].verdict == "POSITIVE"
    assert by_iid_tenure[("iid-1", "12m")].verdict == "POSITIVE"
    # 1m / 6m have no candidates → NEUTRAL
    assert by_iid_tenure[("iid-1", "1m")].verdict == "NEUTRAL"
    assert by_iid_tenure[("iid-1", "6m")].verdict == "NEUTRAL"

    # Instrument 2 — neg RS triggers NEGATIVE @ 3m, no candidates fire @ 12m
    assert by_iid_tenure[("iid-2", "3m")].verdict == "NEGATIVE"
    assert by_iid_tenure[("iid-2", "12m")].verdict == "NEUTRAL"

    # Instrument 3 — flat RS, no candidate fires.
    for tenure_t in ("1m", "3m", "6m", "12m"):
        assert by_iid_tenure[("iid-3", tenure_t)].verdict == "NEUTRAL"  # type: ignore[index]


def test_eli5_propagated_from_firing_rule(
    candidates_by_key: dict[tuple[str, str, str], list[CandidateRow]],
) -> None:
    """The eli5 text should reflect the firing rule's archetype."""
    scorecard_rows: list[dict[str, Any]] = [
        {
            "instrument_id": "iid-1",
            "cap_tier": "Large",
            "rs_residual_6m": Decimal("0.10"),
            "realized_vol_60d": Decimal("0.03"),
        }
    ]
    rows = compute_conviction_for_snapshot(
        date(2026, 5, 22),
        scorecard_rows=scorecard_rows,
        candidates_by_key=candidates_by_key,
    )
    pos_3m = next(r for r in rows if r.tenure == "3m")
    # quality_momentum template carries "Consistent {cap_tier}-cap leaders..."
    assert "Consistent" in pos_3m.eli5 or "Large" in pos_3m.eli5
    # Neutral row carries the neutral marker
    neutral = next(r for r in rows if r.tenure == "1m")
    assert neutral.eli5 == "No active signal at this tenure."


# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------


def test_emit_upsert_sql_shape() -> None:
    from atlas.inference.conviction_tape import ConvictionRow

    rows = [
        ConvictionRow(
            snapshot_date=date(2026, 5, 22),
            instrument_id="aaaa-bbbb",
            tenure="3m",
            verdict="POSITIVE",
            best_rule_id="rule-id",
            cell_definition_id="cell-id",
            ic=Decimal("0.15"),
            friction_adjusted_excess=Decimal("0.10"),
            fired_predicates=[{"feature": "rs_residual_6m", "cmp": ">", "value": "0"}],
            eli5="Test rule fires",
            conflict=False,
        )
    ]
    sql = emit_upsert_sql(rows)
    assert "INSERT INTO atlas.atlas_conviction_daily" in sql
    assert "ON CONFLICT (snapshot_date, instrument_id, tenure)" in sql
    assert "'2026-05-22'" in sql
    assert "'aaaa-bbbb'" in sql
    assert "'POSITIVE'" in sql
    assert "::jsonb" in sql  # fired_predicates JSONB cast


def test_emit_upsert_sql_handles_nulls() -> None:
    from atlas.inference.conviction_tape import ConvictionRow

    rows = [
        ConvictionRow(
            snapshot_date=date(2026, 5, 22),
            instrument_id="iid",
            tenure="1m",
            verdict="NEUTRAL",
            best_rule_id=None,
            cell_definition_id=None,
            ic=None,
            friction_adjusted_excess=None,
            fired_predicates=None,
            eli5="No active signal at this tenure.",
            conflict=False,
        )
    ]
    sql = emit_upsert_sql(rows)
    assert "NULL" in sql
    # NULL fired_predicates should NOT have ::jsonb cast (defensive)
    assert "NULL::jsonb" not in sql
