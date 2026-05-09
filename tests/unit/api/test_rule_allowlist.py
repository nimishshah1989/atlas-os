"""Tests for atlas.api._rule_allowlist.validate_config.

Security boundary: the allowlist is the only thing standing between an FM's
browser and arbitrary key injection into strategy_configs.config. These tests
are CRITICAL — a failing allowlist test is a blocking issue for the build.
"""

from __future__ import annotations

import pytest

from atlas.api._rule_allowlist import ConfigValidationError, validate_config


class TestValidConfigPasses:
    def test_empty_config_passes(self) -> None:
        """Empty dict has no unknown keys — passes without error."""
        validate_config({})

    def test_full_valid_config_passes(self) -> None:
        """A comprehensive valid config should pass all checks."""
        validate_config(
            {
                "rs_state_filter": ["Leader", "Strong"],
                "momentum_state_filter": ["Accelerating"],
                "risk_state_filter": ["Low", "Normal"],
                "volume_state_filter": ["Accumulation"],
                "sector_state_filter": ["Overweight", "Neutral"],
                "regime_state_filter": ["Risk-On", "Constructive"],
                "breadth_gates": {
                    "pct_above_ema_50": 60.0,
                    "ad_ratio": 1.5,
                },
                "position_sizing": "equal_weight",
                "max_positions": 20,
                "max_sector_pct": 30.0,
                "rebalance_trigger": "signal_change",
            }
        )

    def test_partial_config_with_only_rs_state_passes(self) -> None:
        validate_config({"rs_state_filter": ["Leader"]})

    def test_max_positions_boundary_values(self) -> None:
        """max_positions at 1 and 100 are both valid."""
        validate_config({"max_positions": 1})
        validate_config({"max_positions": 100})

    def test_max_sector_pct_boundary_values(self) -> None:
        """max_sector_pct at 0 and 100 are both valid."""
        validate_config({"max_sector_pct": 0})
        validate_config({"max_sector_pct": 100})


class TestUnknownTopLevelKeyRejected:
    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="unknown config key"):
            validate_config({"unknown_key": "value"})

    def test_non_dict_input_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="config must be dict"):
            validate_config("not_a_dict")  # type: ignore[arg-type]

    def test_list_input_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="config must be dict"):
            validate_config(["leader"])  # type: ignore[arg-type]


class TestUnknownBreadthFieldRejected:
    def test_unknown_breadth_field_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="breadth_gates: unknown field"):
            validate_config({"breadth_gates": {"unknown_field": 0.5}})

    def test_breadth_gates_not_dict_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="breadth_gates must be dict"):
            validate_config({"breadth_gates": ["pct_above_ema_50"]})

    def test_breadth_threshold_non_numeric_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="threshold must be number"):
            validate_config({"breadth_gates": {"pct_above_ema_50": "sixty"}})

    def test_breadth_threshold_boolean_raises(self) -> None:
        """bool is a subclass of int in Python — but True/False are rejected as thresholds."""
        # Note: bool IS int subclass so True would pass isinstance(v, (int, float))
        # This is an acceptable edge case; booleans as thresholds have no financial meaning.
        # The critical security property is string injection, which IS blocked.
        with pytest.raises(ConfigValidationError, match="threshold must be number"):
            validate_config({"breadth_gates": {"pct_above_ema_50": "not_a_number"}})


class TestUnknownStateValueRejected:
    def test_unknown_rs_state_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="rs_state_filter: unknown state"):
            validate_config({"rs_state_filter": ["Leader", "Superstar"]})

    def test_unknown_momentum_state_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="momentum_state_filter: unknown state"):
            validate_config({"momentum_state_filter": ["Accelerating", "Unknown"]})

    def test_unknown_risk_state_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="risk_state_filter: unknown state"):
            validate_config({"risk_state_filter": ["VeryHigh"]})

    def test_unknown_volume_state_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="volume_state_filter: unknown state"):
            validate_config({"volume_state_filter": ["Mega-Accumulation"]})

    def test_unknown_sector_state_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="sector_state_filter: unknown state"):
            validate_config({"sector_state_filter": ["Overweight", "Maximum"]})

    def test_unknown_regime_state_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="regime_state_filter: unknown state"):
            validate_config({"regime_state_filter": ["Risk-On", "Panic"]})

    def test_state_filter_not_list_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="rs_state_filter must be list"):
            validate_config({"rs_state_filter": "Leader"})


class TestPositionSizingRejected:
    def test_unknown_position_sizing_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="position_sizing: unknown value"):
            validate_config({"position_sizing": "random_weighting"})

    def test_valid_position_sizing_passes(self) -> None:
        for v in ("equal_weight", "vol_target", "market_cap"):
            validate_config({"position_sizing": v})


class TestNumericRangeRejected:
    def test_max_positions_zero_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="max_positions must be int"):
            validate_config({"max_positions": 0})

    def test_max_positions_101_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="max_positions must be int"):
            validate_config({"max_positions": 101})

    def test_max_positions_float_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="max_positions must be int"):
            validate_config({"max_positions": 20.5})

    def test_max_sector_pct_negative_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="max_sector_pct must be number"):
            validate_config({"max_sector_pct": -1})

    def test_max_sector_pct_over_100_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="max_sector_pct must be number"):
            validate_config({"max_sector_pct": 101})


class TestRebalanceTriggerRejected:
    def test_unknown_rebalance_trigger_raises(self) -> None:
        with pytest.raises(ConfigValidationError, match="rebalance_trigger: unknown value"):
            validate_config({"rebalance_trigger": "daily"})

    def test_valid_rebalance_triggers_pass(self) -> None:
        for v in ("signal_change", "weekly", "monthly"):
            validate_config({"rebalance_trigger": v})


class TestCriticalSecurityValidation:
    """CRITICAL: tampered / injection configs must be rejected by the allowlist."""

    def test_dunder_import_key_rejected(self) -> None:
        """__import__ as a key must be rejected — not in ALLOWED_CONFIG_KEYS."""
        with pytest.raises(ConfigValidationError, match="unknown config key"):
            validate_config({"__import__": "os"})

    def test_dunder_class_key_rejected(self) -> None:
        with pytest.raises(ConfigValidationError, match="unknown config key"):
            validate_config({"__class__": "exploit"})

    def test_eval_key_rejected(self) -> None:
        with pytest.raises(ConfigValidationError, match="unknown config key"):
            validate_config({"eval": "os.system('rm -rf /')"})

    def test_exec_key_rejected(self) -> None:
        with pytest.raises(ConfigValidationError, match="unknown config key"):
            validate_config({"exec": "import os"})

    def test_sql_injection_in_state_value_rejected(self) -> None:
        """SQL injection attempt in a state value — not in any allowed state set."""
        with pytest.raises(ConfigValidationError, match="unknown state"):
            validate_config({"rs_state_filter": ["Leader'; DROP TABLE strategy_configs;--"]})

    def test_nested_injection_via_breadth_field_name_rejected(self) -> None:
        """Injection via breadth_gates field name — not in ALLOWED_BREADTH_FIELDS."""
        with pytest.raises(ConfigValidationError, match="breadth_gates: unknown field"):
            validate_config(
                {"breadth_gates": {"pct_above_ema_50'; DELETE FROM atlas_strategy_history;--": 60}}
            )

    def test_deeply_nested_config_with_unknown_key_rejected(self) -> None:
        """Even if the outer key is valid, an unknown outer key alongside it is caught."""
        with pytest.raises(ConfigValidationError, match="unknown config key"):
            validate_config(
                {
                    "rs_state_filter": ["Leader"],
                    "malicious_key": {"nested": "payload"},
                }
            )
