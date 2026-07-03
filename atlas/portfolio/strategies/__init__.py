"""Strategy registry — a new strategy is one new file here + one entry below."""

from __future__ import annotations

from .ema_cross import EmaCross

STRATEGIES: dict[str, type] = {EmaCross.key: EmaCross}


def get_strategy(key: str, params: dict):
    if key not in STRATEGIES:
        raise KeyError(f"unknown strategy_key {key!r}; known: {sorted(STRATEGIES)}")
    return STRATEGIES[key](**params)
