"""Shared types and helpers for bottom-up state aggregations."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Threshold above which we call one state "dominant"; below = mixed.
DOMINANT_THRESHOLD = 0.50

# Order matters for tie-breaking — earlier states are more bullish.
STATE_ORDER = (
    "stage_2a",
    "stage_2b",
    "stage_2c",
    "stage_1",
    "stage_3",
    "stage_4",
    "uninvestable",
)


def weighted_state_distribution(df: pd.DataFrame) -> dict[str, float]:
    """Compute weighted share of each state.

    Required columns: ``state`` (str), ``weight`` (Decimal or float).
    Weights are normalized to sum to 1; states with zero total weight
    return an empty dict.
    """
    if df.empty:
        return {}
    df = df.copy()
    df["weight"] = df["weight"].astype(float)
    total = df["weight"].sum()
    if total <= 0:
        return {}
    grouped = df.groupby("state")["weight"].sum() / total
    return grouped.to_dict()


@dataclass(frozen=True)
class AggregateState:
    """Result of aggregating constituent stock states."""

    dominant_state: str
    dominant_share: float
    distribution: dict[str, float]
    n_constituents: int

    @property
    def is_mixed(self) -> bool:
        return self.dominant_share < DOMINANT_THRESHOLD

    @classmethod
    def from_distribution(cls, distribution: dict[str, float]) -> AggregateState:
        if not distribution:
            return cls("uninvestable", 0.0, {}, 0)
        # Pick the state with max share; break ties by STATE_ORDER index.
        dominant = max(
            distribution.items(),
            key=lambda kv: (kv[1], -STATE_ORDER.index(kv[0]) if kv[0] in STATE_ORDER else -99),
        )
        return cls(
            dominant_state=dominant[0],
            dominant_share=dominant[1],
            distribution=distribution,
            n_constituents=len(distribution),
        )
