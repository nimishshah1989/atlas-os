"""M15 rule-config allowlist module.

The POST /api/portfolios/rule-based endpoint accepts JSON config from FM.
Without strict validation, an attacker could inject arbitrary keys that
runner.py / paper_trader.py might process as eval-equivalent logic. This
module is the security boundary.
"""

from __future__ import annotations

# Allowed top-level keys in strategy_configs.config
ALLOWED_CONFIG_KEYS = frozenset(
    {
        "rs_state_filter",
        "momentum_state_filter",
        "risk_state_filter",
        "volume_state_filter",
        "sector_state_filter",
        "regime_state_filter",
        "breadth_gates",
        "position_sizing",
        "max_positions",
        "max_sector_pct",
        "rebalance_trigger",
        "stock_allocation_pct",
        "etf_allocation_pct",
        "fund_tier_filter",
        "threshold_overrides",
        "exit_rules",
    }
)

ALLOWED_BREADTH_FIELDS = frozenset(
    {
        "pct_above_ema_50",
        "ad_ratio",
        "new_high_low_ratio",
        "pct_in_strong_states",
        "pct_weinstein_pass",
    }
)

# State-value catalogs (per asset/dimension)
ALLOWED_RS_STATES = frozenset(
    {"Leader", "Strong", "Consolidating", "Emerging", "Average", "Weak", "Laggard"}
)
ALLOWED_MOMENTUM_STATES = frozenset(
    {"Accelerating", "Improving", "Flat", "Deteriorating", "Collapsing"}
)
ALLOWED_RISK_STATES = frozenset({"Low", "Normal", "Elevated", "High", "Below Trend"})
ALLOWED_VOLUME_STATES = frozenset(
    {"Accumulation", "Steady-Buying", "Neutral", "Distribution", "Heavy Distribution"}
)
ALLOWED_SECTOR_STATES = frozenset({"Overweight", "Neutral", "Underweight", "Avoid"})
ALLOWED_REGIME_STATES = frozenset({"Risk-On", "Constructive", "Cautious", "Risk-Off"})

ALLOWED_POSITION_SIZING = frozenset({"equal_weight", "vol_target", "market_cap"})
ALLOWED_REBALANCE = frozenset({"signal_change", "weekly", "monthly"})


class ConfigValidationError(ValueError):
    """Raised when an FM-authored config has disallowed keys or values."""


def validate_config(config: dict) -> None:  # type: ignore[type-arg]
    """Raise ConfigValidationError if config has disallowed keys or values."""
    if not isinstance(config, dict):
        raise ConfigValidationError(f"config must be dict, got {type(config).__name__}")

    for key in config:
        if key not in ALLOWED_CONFIG_KEYS:
            raise ConfigValidationError(f"unknown config key '{key}'")

    # Validate state filters
    state_check_pairs = [
        ("rs_state_filter", ALLOWED_RS_STATES),
        ("momentum_state_filter", ALLOWED_MOMENTUM_STATES),
        ("risk_state_filter", ALLOWED_RISK_STATES),
        ("volume_state_filter", ALLOWED_VOLUME_STATES),
        ("sector_state_filter", ALLOWED_SECTOR_STATES),
        ("regime_state_filter", ALLOWED_REGIME_STATES),
    ]
    for key, allowed in state_check_pairs:
        if key in config:
            if not isinstance(config[key], list):
                raise ConfigValidationError(f"{key} must be list")
            for v in config[key]:
                if v not in allowed:
                    raise ConfigValidationError(f"{key}: unknown state '{v}'")

    # Validate breadth gates
    if "breadth_gates" in config:
        gates = config["breadth_gates"]
        if not isinstance(gates, dict):
            raise ConfigValidationError("breadth_gates must be dict")
        for field, threshold in gates.items():
            if field not in ALLOWED_BREADTH_FIELDS:
                raise ConfigValidationError(f"breadth_gates: unknown field '{field}'")
            if not isinstance(threshold, int | float):
                raise ConfigValidationError(f"breadth_gates.{field}: threshold must be number")

    # Validate position_sizing
    if "position_sizing" in config:
        if config["position_sizing"] not in ALLOWED_POSITION_SIZING:
            raise ConfigValidationError(
                f"position_sizing: unknown value '{config['position_sizing']}'"
            )

    # Validate rebalance_trigger
    if "rebalance_trigger" in config:
        if config["rebalance_trigger"] not in ALLOWED_REBALANCE:
            raise ConfigValidationError(
                f"rebalance_trigger: unknown value '{config['rebalance_trigger']}'"
            )

    # Validate numeric ranges
    if "max_positions" in config:
        v = config["max_positions"]
        if not isinstance(v, int) or v < 1 or v > 100:
            raise ConfigValidationError("max_positions must be int 1..100")
    if "max_sector_pct" in config:
        v = config["max_sector_pct"]
        if not isinstance(v, int | float) or v < 0 or v > 100:
            raise ConfigValidationError("max_sector_pct must be number 0..100")
