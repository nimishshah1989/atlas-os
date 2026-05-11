"""Tests for markdown report generation."""

from datetime import date

from atlas.intelligence.validation.ic_engine import ICResult
from atlas.intelligence.validation.report import build_tearsheet_markdown


def test_tearsheet_includes_signal_name():
    results_by_period = {
        5: (ICResult(mean_ic=0.03, ic_std=0.10, ic_t_stat=1.5, n_observations=126), 0.04, 0.32),
        21: (ICResult(mean_ic=0.07, ic_std=0.12, ic_t_stat=2.4, n_observations=126), 0.09, 0.28),
        63: (ICResult(mean_ic=0.05, ic_std=0.11, ic_t_stat=1.9, n_observations=126), 0.06, 0.22),
    }
    md = build_tearsheet_markdown(
        signal_name="decision_state",
        rolling_window="6M",
        as_of=date(2026, 5, 11),
        results_by_period=results_by_period,
    )
    assert "decision_state" in md
    assert "6M" in md
    assert "2026-05-11" in md


def test_tearsheet_flags_success_criteria():
    results_by_period = {
        21: (ICResult(mean_ic=0.07, ic_std=0.12, ic_t_stat=2.4, n_observations=126), 0.09, 0.28),
    }
    md = build_tearsheet_markdown(
        signal_name="decision_state",
        rolling_window="6M",
        as_of=date(2026, 5, 11),
        results_by_period=results_by_period,
    )
    # Should flag pass on the 21d row (IC > 0.05, t > 2.0, spread > 8%, turnover < 30%)
    assert "PASS" in md or "✓" in md


def test_tearsheet_flags_failures():
    results_by_period = {
        21: (ICResult(mean_ic=0.01, ic_std=0.20, ic_t_stat=0.5, n_observations=50), 0.02, 0.45),
    }
    md = build_tearsheet_markdown(
        signal_name="decision_state",
        rolling_window="6M",
        as_of=date(2026, 5, 11),
        results_by_period=results_by_period,
    )
    assert "FAIL" in md or "✗" in md
