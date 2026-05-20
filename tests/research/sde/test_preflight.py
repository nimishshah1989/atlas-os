"""Tests for the SDE pre-flight report formatter."""

from __future__ import annotations

from scripts.sde_preflight_checks import PreflightResult, format_preflight


def test_format_preflight_pass_on_good_data() -> None:
    result = PreflightResult(adj_total=1000, adj_with=950, delisted=100, delisted_with_history=95)
    text = format_preflight(result)
    assert "Check 1 PASS" in text
    assert "Check 2 PASS" in text


def test_format_preflight_warn_on_low_coverage() -> None:
    result = PreflightResult(adj_total=1000, adj_with=200, delisted=100, delisted_with_history=10)
    text = format_preflight(result)
    assert "Check 1 WARN" in text
    assert "Check 2 WARN" in text
