"""State-to-numeric encoding for the Atlas decision_state composite.

Pure functions. No I/O. No external deps beyond pandas.

The encoding is the V1 hand-set quality scoring. SP04 (Signal Intelligence)
will replace these weights with IC-derived weights from the atlas_signal_ic
table that THIS module populates. Treat these weights as a measurable
starting point, not a permanent choice.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

# Sentinel state values — rows containing any of these are dropped from
# IC measurement. They represent "we couldn't classify this row" not
# "the row should score zero."
SENTINEL_STATES: Final[frozenset[str]] = frozenset(
    {
        "INSUFFICIENT_HISTORY",
        "ILLIQUID",
        "DISLOCATION_SUSPENDED",
    }
)

# Per-dimension state → quality score in [0, 1].
STATE_ENCODINGS: Final[dict[str, dict[str, float]]] = {
    "rs_state": {
        "Leader": 1.0,
        "Strong": 0.85,
        "Consolidating": 0.6,
        "Emerging": 0.55,
        "Average": 0.4,
        "Weak": 0.15,
        "Laggard": 0.0,
    },
    "momentum_state": {
        "Accelerating": 1.0,
        "Improving": 0.75,
        "Flat": 0.5,
        "Deteriorating": 0.25,
        "Collapsing": 0.0,
    },
    "risk_state": {
        "Low": 1.0,
        "Normal": 0.75,
        "Below Trend": 0.5,
        "Elevated": 0.25,
        "High": 0.0,
    },
    "volume_state": {
        "Accumulation": 1.0,
        "Steady-Buying": 0.75,
        "Neutral": 0.5,
        "Distribution": 0.25,
        "Heavy Distribution": 0.0,
    },
    "sector_state": {
        "Overweight": 1.0,
        "Neutral": 0.5,
        "Underweight": 0.25,
        "Avoid": 0.0,
    },
    "regime_state": {
        "Risk-On": 1.0,
        "Constructive": 0.7,
        "Cautious": 0.4,
        "Risk-Off": 0.0,
    },
}

# Dimension weights in the composite. Sum to 1.0.
DIMENSION_WEIGHTS: Final[dict[str, float]] = {
    "rs_state": 0.35,
    "momentum_state": 0.25,
    "risk_state": 0.15,
    "volume_state": 0.10,
    "sector_state": 0.10,
    "regime_state": 0.05,
}


def encode_state(dimension: str, value: str) -> float | None:
    """Encode a categorical state value to its [0,1] quality score.

    Returns None for sentinel states (the row should be dropped).
    Raises KeyError for unknown dimensions.
    Raises ValueError for unknown state values within a known dimension.
    """
    if value in SENTINEL_STATES:
        return None
    encoding = STATE_ENCODINGS[dimension]  # KeyError on unknown dimension
    if value not in encoding:
        raise ValueError(f"unknown {dimension} value: {value!r}")
    return encoding[value]


def compute_decision_state_score(row: pd.Series) -> float | None:  # type: ignore[type-arg]
    """Compute the composite decision_state score for one (instrument, date) row.

    Returns None if any required dimension is a sentinel state.
    Returns float in [0, 1] otherwise.
    """
    total = 0.0
    for dimension, weight in DIMENSION_WEIGHTS.items():
        value: str = str(row[dimension])
        encoded = encode_state(dimension, value)
        if encoded is None:
            return None
        total += weight * encoded
    return total
