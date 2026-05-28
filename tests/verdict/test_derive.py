"""Unit tests for atlas.verdict.derive — precedence ladder per spec §4.

Source of truth: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §4.
Spec locks enforced here:
- Q1: Stage 3 → WATCH/HOLD ("Stage 3 topping"), never WAIT
- Q5: Micro cap_tier exempts from Weinstein veto entirely
"""

from atlas.verdict.derive import VerdictInput, derive_verdict

_ALL_GATES_PASS = {
    "strength": True,
    "direction": True,
    "risk": True,
    "sector": True,
    "market": True,
}


def test_positive_cell_stage2_all_gates_pass_not_owned_returns_BUY():
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=2,
            user_owns=False,
            gates=_ALL_GATES_PASS,
        )
    )
    assert v.verdict == "BUY" and v.reason is None


def test_positive_cell_stage2_all_gates_pass_owned_returns_ACCUMULATE():
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=2,
            user_owns=True,
            gates=_ALL_GATES_PASS,
        )
    )
    assert v.verdict == "ACCUMULATE"


def test_positive_cell_stage4_returns_WAIT():
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=4,
            user_owns=False,
            gates=_ALL_GATES_PASS,
        )
    )
    assert v.verdict == "WAIT"
    assert v.reason == "Stage 4 vetoes positive cell"


def test_positive_cell_risk_gate_fail_returns_WAIT():
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=2,
            user_owns=False,
            gates={
                "strength": True,
                "direction": True,
                "risk": False,
                "sector": True,
                "market": True,
            },
        )
    )
    assert v.verdict == "WAIT"
    assert "risk gate" in v.reason.lower()


def test_positive_cell_stage3_not_owned_returns_WATCH():
    # Q1 spec lock: Stage 3 downgrades to WATCH/HOLD, NOT WAIT
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=3,
            user_owns=False,
            gates=_ALL_GATES_PASS,
        )
    )
    assert v.verdict == "WATCH"
    assert v.reason == "Stage 3 topping"


def test_positive_cell_stage3_owned_returns_HOLD():
    # Q1 spec lock: Stage 3 owned → HOLD with reason, not WAIT
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=3,
            user_owns=True,
            gates=_ALL_GATES_PASS,
        )
    )
    assert v.verdict == "HOLD"


def test_neutral_cell_not_owned_returns_WATCH():
    v = derive_verdict(
        VerdictInput(cell_state="NEUTRAL", weinstein_stage=2, user_owns=False, gates={})
    )
    assert v.verdict == "WATCH" and v.reason is None


def test_neutral_cell_owned_returns_HOLD():
    v = derive_verdict(
        VerdictInput(cell_state="NEUTRAL", weinstein_stage=2, user_owns=True, gates={})
    )
    assert v.verdict == "HOLD"


def test_negative_cell_not_owned_returns_AVOID():
    v = derive_verdict(
        VerdictInput(cell_state="NEGATIVE", weinstein_stage=4, user_owns=False, gates={})
    )
    assert v.verdict == "AVOID"


def test_negative_cell_owned_returns_SELL():
    v = derive_verdict(
        VerdictInput(cell_state="NEGATIVE", weinstein_stage=4, user_owns=True, gates={})
    )
    assert v.verdict == "SELL"


def test_micro_cap_no_weinstein_veto():
    # Q5 spec lock: Micro defaults to no Weinstein veto regardless of stage
    v = derive_verdict(
        VerdictInput(
            cell_state="POSITIVE",
            weinstein_stage=4,
            user_owns=False,
            cap_tier="Micro",
            gates=_ALL_GATES_PASS,
        )
    )
    assert v.verdict == "BUY"  # Stage 4 ignored for Micro
