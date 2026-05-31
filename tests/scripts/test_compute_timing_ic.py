"""Tests for scripts.compute_timing_ic v2."""

from __future__ import annotations

from scripts.compute_timing_ic import LOOKBACK_DAYS, MIN_OBS, SIGNAL_CONFIGS


def test_signal_configs_has_expected_length() -> None:
    assert len(SIGNAL_CONFIGS) == 7


def test_signal_configs_primary_horizon_is_5d() -> None:
    """First config must be ppc_strength vs fwd_ret_5d (primary)."""
    signal_col, fwd_col, stage_filter = SIGNAL_CONFIGS[0]
    assert signal_col == "ppc_strength"
    assert fwd_col == "fwd_ret_5d"
    assert stage_filter is None


def test_signal_configs_includes_stage2_segment() -> None:
    """At least one config must have stage_filter=2."""
    stage2_configs = [c for c in SIGNAL_CONFIGS if c[2] == 2]
    assert len(stage2_configs) >= 1


def test_signal_configs_includes_conviction_score() -> None:
    """cts_conviction_score must appear in configs."""
    conviction_signals = [c for c in SIGNAL_CONFIGS if c[0] == "cts_conviction_score"]
    assert len(conviction_signals) >= 1


def test_lookback_days_is_365() -> None:
    assert LOOKBACK_DAYS == 365


def test_min_obs_at_least_30() -> None:
    assert MIN_OBS >= 30


def test_all_configs_are_3_tuples() -> None:
    for cfg in SIGNAL_CONFIGS:
        assert len(cfg) == 3, f"Config {cfg!r} must be a 3-tuple"


def test_stage_filter_is_int_or_none() -> None:
    for signal_col, fwd_col, stage_filter in SIGNAL_CONFIGS:
        assert stage_filter is None or isinstance(stage_filter, int), (
            f"stage_filter must be int or None, got {stage_filter!r} for {signal_col}/{fwd_col}"
        )


def test_fwd_col_format_parseable() -> None:
    """Every fwd_col must match fwd_ret_Nd pattern so horizon extraction works."""
    for _signal_col, fwd_col, _ in SIGNAL_CONFIGS:
        parts = fwd_col.split("_")
        assert parts[-1].endswith("d"), f"fwd_col {fwd_col!r} does not end in 'd'"
        horizon = int(parts[-1].replace("d", ""))
        assert horizon > 0, f"horizon must be positive for {fwd_col!r}"
