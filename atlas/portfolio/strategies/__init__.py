"""Strategy registry — a new strategy is one new file here + one entry below."""

from __future__ import annotations

from .atlas_policy import AtlasPolicy
from .ema_cross import EmaCross
from .rank_policy import RankPolicy

STRATEGIES: dict[str, type] = {
    EmaCross.key: EmaCross,
    AtlasPolicy.key: AtlasPolicy,
    RankPolicy.key: RankPolicy,
}


def get_strategy(key: str, params: dict):
    if key not in STRATEGIES:
        raise KeyError(f"unknown strategy_key {key!r}; known: {sorted(STRATEGIES)}")
    return STRATEGIES[key](**params)
