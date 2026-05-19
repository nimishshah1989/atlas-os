"""Tests for atlas/intelligence/states/ic_harness.py.

Seven unit tests covering classify_ic_status thresholds, LegacySignal
dataclass shape, and LEGACY_SIGNAL_CATALOG completeness.
No I/O — all pure-function tests.
"""

from atlas.intelligence.states.ic_harness import (
    LEGACY_SIGNAL_CATALOG,
    LegacySignal,
    classify_ic_status,
)

# --------------------------------------------------------------------------- #
# classify_ic_status                                                          #
# --------------------------------------------------------------------------- #


def test_classify_ic_status_validated_when_ir_above_pt4_and_spread_above_threshold() -> None:
    # IR > 0.4 AND |spread| > 0.005 -> validated
    assert classify_ic_status(ic_ir=0.55, q5_q1_spread=0.04) == "validated"


def test_classify_ic_status_validated_inverse_when_negative_ir_above_pt4() -> None:
    # IR < -0.4 AND |spread| > 0.005 -> validated_inverse
    assert classify_ic_status(ic_ir=-0.48, q5_q1_spread=-0.03) == "validated_inverse"


def test_classify_ic_status_weak_when_ir_between_pt2_and_pt4() -> None:
    # 0.2 <= |IR| <= 0.4 -> weak (spread condition met)
    assert classify_ic_status(ic_ir=0.25, q5_q1_spread=0.01) == "weak"


def test_classify_ic_status_decorative_when_ir_below_pt2() -> None:
    # |IR| < 0.2 -> decorative regardless of spread
    assert classify_ic_status(ic_ir=0.10, q5_q1_spread=0.001) == "decorative"


def test_classify_ic_status_decorative_when_spread_below_threshold() -> None:
    # |spread| < 0.005 -> decorative even if IR is high
    assert classify_ic_status(ic_ir=0.60, q5_q1_spread=0.003) == "decorative"


def test_classify_ic_status_weak_negative_ir_in_band() -> None:
    # IR = -0.30, spread = -0.01 -> |spread| >= 0.005 and 0.2 <= |IR| <= 0.4 -> weak
    assert classify_ic_status(ic_ir=-0.30, q5_q1_spread=-0.01) == "weak"


# --------------------------------------------------------------------------- #
# LegacySignal + LEGACY_SIGNAL_CATALOG                                       #
# --------------------------------------------------------------------------- #


def test_legacy_signal_catalog_includes_all_expected_names() -> None:
    names = {sig.name for sig in LEGACY_SIGNAL_CATALOG}
    assert "cts_ppc_continuous" in names
    assert "cts_npc_continuous" in names
    assert "cts_contraction_continuous" in names
    assert "nav_state" in names
    assert "transition_trigger" in names
    assert "breakout_trigger" in names


def test_legacy_signal_dataclass_has_loader_and_horizon() -> None:
    sig = LEGACY_SIGNAL_CATALOG[0]
    assert isinstance(sig, LegacySignal)
    assert sig.horizon_days in (21, 63)
    assert callable(sig.loader)


def test_legacy_signal_nav_state_loader_returns_empty_dataframe() -> None:
    """nav_state loader must return empty DF (fund-level harness deferred)."""
    nav = next(s for s in LEGACY_SIGNAL_CATALOG if s.name == "nav_state")
    result = nav.loader(None, None, None)  # type: ignore[arg-type]
    assert result.empty


def test_legacy_signal_catalog_has_six_entries() -> None:
    assert len(LEGACY_SIGNAL_CATALOG) == 6


def test_classify_ic_status_exact_pt4_boundary_treated_as_weak() -> None:
    # ic_ir = 0.4 is NOT > 0.4, so should be weak (|IR| >= 0.2, spread OK)
    assert classify_ic_status(ic_ir=0.40, q5_q1_spread=0.01) == "weak"
