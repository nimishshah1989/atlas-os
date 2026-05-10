"""Loads 15 strategy YAML configs into StrategyConfig dataclasses.

Also provides populate_strategy_configs() — idempotent DB seeder that mirrors
atlas/universe/thresholds.py:populate_thresholds().
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

_CONFIGS_DIR = Path(__file__).parent / "configs"


@dataclass
class StrategyConfig:
    name: str
    tier: str
    archetype: str
    variant: str
    state_filter: list[str]
    regime_stance: str
    position_sizing: str
    max_positions: int
    max_sector_pct: float
    rebalance_trigger: str
    threshold_overrides: dict[str, float] = field(default_factory=dict)
    # Optional blend-tier fields
    stock_allocation_pct: float | None = None
    etf_allocation_pct: float | None = None
    # Optional fund-tier fields
    fund_tier_filter: list[str] | None = None
    # Human-readable description (shown on strategy detail page)
    description: str = ""


def load_config(name: str) -> StrategyConfig:
    """Load a single strategy config by name (matches YAML filename stem)."""
    path = _CONFIGS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Strategy config not found: {path}")
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    return StrategyConfig(
        name=raw["name"],
        tier=raw["tier"],
        archetype=raw["archetype"],
        variant=raw["variant"],
        state_filter=raw["state_filter"],
        regime_stance=raw["regime_stance"],
        position_sizing=raw.get("position_sizing", "equal_weight"),
        max_positions=raw["max_positions"],
        max_sector_pct=raw["max_sector_pct"],
        rebalance_trigger=raw.get("rebalance_trigger", "signal_change"),
        # dict.get() returns None when key missing, but YAML `{}` returns empty dict.
        # The `or {}` handles both None (missing key) and edge case where value is None.
        threshold_overrides=raw.get("threshold_overrides") or {},
        stock_allocation_pct=raw.get("stock_allocation_pct"),
        etf_allocation_pct=raw.get("etf_allocation_pct"),
        fund_tier_filter=raw.get("fund_tier_filter"),
        description=raw.get("description", ""),
    )


def load_all_configs() -> list[StrategyConfig]:
    """Load all strategy configs from the configs/ directory.

    Sorted alphabetically by filename stem for deterministic ordering.
    """
    paths = sorted(_CONFIGS_DIR.glob("*.yaml"))
    return [load_config(p.stem) for p in paths]


# NOTE: CAST(:config AS jsonb) is used instead of :config::jsonb.
# The ::type cast syntax collides with SQLAlchemy's :param binding parser —
# see wiki bug-pattern "SQLAlchemy Param-Cast Collision".
_UPSERT_SQL = text("""
    INSERT INTO atlas.strategy_configs
        (name, tier, archetype, variant, config, is_active)
    VALUES
        (:name, :tier, :archetype, :variant, CAST(:config AS jsonb), TRUE)
    ON CONFLICT (name) DO UPDATE SET
        tier       = EXCLUDED.tier,
        archetype  = EXCLUDED.archetype,
        variant    = EXCLUDED.variant,
        config     = EXCLUDED.config,
        updated_at = now()
""")


def populate_strategy_configs(engine: Engine | None = None) -> int:
    """Idempotent seeder: load all 15 YAMLs and upsert into atlas.strategy_configs.

    Safe to re-run. ON CONFLICT DO UPDATE preserves row identity while refreshing
    all non-key columns. Mirrors atlas/universe/thresholds.py:populate_thresholds().

    Returns:
        Count of configs upserted (always 15 on success).

    Raises:
        AssertionError: if fewer or more than 15 configs are found on disk.
    """
    eng = engine or get_engine()
    configs = load_all_configs()
    if len(configs) != 15:
        raise AssertionError(
            f"Expected 15 strategy configs, found {len(configs)}. "
            "Check atlas/simulation/strategies/configs/ directory."
        )

    with eng.begin() as conn:
        for cfg in configs:
            config_json = json.dumps(
                {
                    "state_filter": cfg.state_filter,
                    "regime_stance": cfg.regime_stance,
                    "position_sizing": cfg.position_sizing,
                    "max_positions": cfg.max_positions,
                    "max_sector_pct": cfg.max_sector_pct,
                    "rebalance_trigger": cfg.rebalance_trigger,
                    "threshold_overrides": cfg.threshold_overrides,
                    "stock_allocation_pct": cfg.stock_allocation_pct,
                    "etf_allocation_pct": cfg.etf_allocation_pct,
                    "fund_tier_filter": cfg.fund_tier_filter,
                    "description": cfg.description,
                }
            )
            conn.execute(
                _UPSERT_SQL,
                {
                    "name": cfg.name,
                    "tier": cfg.tier,
                    "archetype": cfg.archetype,
                    "variant": cfg.variant,
                    "config": config_json,
                },
            )

    return len(configs)
