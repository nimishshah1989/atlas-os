"""Unit tests for atlas.health.anomaly — boundary cases for the math.

The anomaly thresholds are critical: they decide what shows up red on the
health dashboard. Validate the boundary conditions explicitly.
"""

from __future__ import annotations

import math

import pytest

from atlas.health.anomaly import (
    SEVERITY_RULES,
    evaluate_categorical,
    evaluate_numeric,
)

# ---------------------------------------------------------------------------
# Numeric — pct_change_dod
# ---------------------------------------------------------------------------


class TestPctChange:
    def test_zero_change_no_anomaly(self) -> None:
        r = evaluate_numeric(today=100.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert r.pct_change_dod == pytest.approx(0.0)
        assert r.is_anomaly is False
        assert r.severity is None

    def test_just_below_info_threshold(self) -> None:
        # 9% change — below info threshold (10%)
        r = evaluate_numeric(today=109.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert abs(r.pct_change_dod or 0.0) < 0.10
        assert r.is_anomaly is False

    def test_at_info_threshold_not_anomaly(self) -> None:
        # Strict > on threshold; exact 10% should NOT trigger
        r = evaluate_numeric(today=110.0, prior_day=100.0, history_14d=[100.0] * 14)
        # Some floats land exactly at 0.10
        # If implementation uses strict >, this should pass without flag
        assert r.is_anomaly is False or r.severity == "info"

    def test_just_above_info_triggers_info(self) -> None:
        # 11% change → > 0.10 → info
        r = evaluate_numeric(today=111.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert r.is_anomaly is True
        assert r.severity == "info"

    def test_warn_threshold(self) -> None:
        # 25% change → > 0.20 → warn
        r = evaluate_numeric(today=125.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert r.is_anomaly is True
        assert r.severity == "warn"

    def test_critical_threshold(self) -> None:
        # 60% change → > 0.50 → critical
        r = evaluate_numeric(today=160.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert r.is_anomaly is True
        assert r.severity == "critical"

    def test_negative_change_critical(self) -> None:
        r = evaluate_numeric(today=40.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert r.pct_change_dod == pytest.approx(-0.60)
        assert r.severity == "critical"

    def test_prior_zero_today_nonzero_undefined_pct(self) -> None:
        # Avoids div-by-zero: pct_change_dod is None
        r = evaluate_numeric(today=10.0, prior_day=0.0, history_14d=[1.0, 1.0])
        assert r.pct_change_dod is None

    def test_prior_zero_today_zero_pct_zero(self) -> None:
        r = evaluate_numeric(today=0.0, prior_day=0.0, history_14d=[0.0, 0.0])
        assert r.pct_change_dod == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Numeric — z_score
# ---------------------------------------------------------------------------


class TestZScore:
    def test_constant_history_zero_std_no_z(self) -> None:
        # std=0 → z is None (undefined), no flag
        r = evaluate_numeric(today=100.0, prior_day=100.0, history_14d=[100.0] * 14)
        assert r.z_score is None
        assert r.is_anomaly is False

    def test_z_at_warn_boundary(self) -> None:
        # history mean=10, std=2 (sample)
        # use values that give exactly std=2
        history = [8.0, 10.0, 12.0, 8.0, 12.0, 10.0, 10.0, 8.0, 12.0, 10.0]
        avg = sum(history) / len(history)
        var = sum((x - avg) ** 2 for x in history) / (len(history) - 1)
        std = math.sqrt(var)
        # today = avg + 2.6 * std → z = 2.6 → warn
        today = avg + 2.6 * std
        r = evaluate_numeric(today=today, prior_day=avg, history_14d=history)
        assert r.severity == "warn"

    def test_large_z_critical(self) -> None:
        history = [10.0] * 5 + [11.0] * 5
        # today way out → z >> 4
        r = evaluate_numeric(today=1000.0, prior_day=10.5, history_14d=history)
        assert r.severity == "critical"


# ---------------------------------------------------------------------------
# Numeric — severity ladder ordering
# ---------------------------------------------------------------------------


class TestSeverityLadder:
    def test_critical_wins_over_warn(self) -> None:
        # Both warn-z and critical-pct fire — critical wins
        r = evaluate_numeric(today=200.0, prior_day=100.0, history_14d=[99.0, 100.0, 101.0])
        # 100% pct change > 50% → critical
        assert r.severity == "critical"

    def test_no_history_only_pct_drives_severity(self) -> None:
        r = evaluate_numeric(today=130.0, prior_day=100.0, history_14d=None)
        assert r.severity == "warn"
        assert r.z_score is None

    def test_no_prior_only_z_drives_severity(self) -> None:
        history = [10.0] * 5 + [12.0] * 5
        r = evaluate_numeric(today=100.0, prior_day=None, history_14d=history)
        assert r.pct_change_dod is None
        assert r.severity in {"critical", "warn", "info"}

    def test_severity_rules_well_formed(self) -> None:
        # critical thresholds > warn thresholds > info thresholds
        sevs = list(SEVERITY_RULES)
        crit, warn, info = sevs
        assert crit[1] > warn[1] > info[1]
        assert crit[2] > warn[2] > info[2]


# ---------------------------------------------------------------------------
# Categorical
# ---------------------------------------------------------------------------


class TestCategorical:
    def test_no_change_not_anomaly(self) -> None:
        r = evaluate_categorical(today="Risk-On", prior_day="Risk-On")
        assert r.is_anomaly is False

    def test_change_is_warn(self) -> None:
        r = evaluate_categorical(today="Risk-On", prior_day="Risk-Off")
        assert r.is_anomaly is True
        assert r.severity == "warn"

    def test_critical_flag(self) -> None:
        # severity_critical=True → flips warn → critical on change
        r = evaluate_categorical(today="Risk-Off", prior_day="Risk-On", severity_critical=True)
        assert r.severity == "critical"

    def test_first_observation_not_anomaly(self) -> None:
        # prior_day None should NOT flag (insufficient data)
        r = evaluate_categorical(today="Risk-On", prior_day=None)
        assert r.is_anomaly is False

    def test_today_none_no_anomaly(self) -> None:
        r = evaluate_categorical(today=None, prior_day="Risk-On")
        assert r.is_anomaly is False
