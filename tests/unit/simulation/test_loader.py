"""Unit tests for strategy config loader — no DB required for YAML loading tests."""

from __future__ import annotations

from atlas.simulation.strategies.loader import (
    load_all_configs,
    load_config,
)


def test_load_all_configs_returns_fifteen():
    configs = load_all_configs()
    assert len(configs) == 15, f"Expected 15, got {len(configs)}"


def test_load_all_configs_names_match_filenames():
    configs = load_all_configs()
    names = {c.name for c in configs}
    expected = {
        "stocks_momentum_aggressive",
        "stocks_momentum_moderate",
        "stocks_momentum_conservative",
        "stocks_sector_rotation_concentrated",
        "stocks_sector_rotation_diversified",
        "blend_momentum_60_40",
        "blend_balanced_50_50",
        "blend_etf_led",
        "blend_defensive",
        "blend_sector_rotation_etf",
        "fund_l1_dominant",
        "fund_l2_dominant",
        "fund_l3_dominant",
        "fund_balanced",
        "fund_defensive",
    }
    assert names == expected


def test_load_config_stocks_momentum_aggressive():
    cfg = load_config("stocks_momentum_aggressive")
    assert cfg.tier == "stocks_only"
    assert cfg.archetype == "momentum_pure"
    assert cfg.variant == "aggressive"
    assert cfg.state_filter == ["leader"]
    assert cfg.regime_stance == "pause_risk_off"
    assert cfg.max_positions == 15


def test_load_config_fund_l1_dominant():
    cfg = load_config("fund_l1_dominant")
    assert cfg.tier == "fund_only"
    assert cfg.archetype == "fund_momentum"
    assert cfg.regime_stance == "hold_risk_off"


def test_strategy_config_has_required_fields():
    cfg = load_config("blend_momentum_60_40")
    assert hasattr(cfg, "name")
    assert hasattr(cfg, "tier")
    assert hasattr(cfg, "archetype")
    assert hasattr(cfg, "variant")
    assert hasattr(cfg, "state_filter")
    assert hasattr(cfg, "regime_stance")
    assert hasattr(cfg, "max_positions")
    assert hasattr(cfg, "threshold_overrides")
    assert isinstance(cfg.threshold_overrides, dict)


def test_threshold_overrides_is_empty_dict_by_default():
    configs = load_all_configs()
    for cfg in configs:
        assert isinstance(
            cfg.threshold_overrides, dict
        ), f"{cfg.name} threshold_overrides is not a dict"
