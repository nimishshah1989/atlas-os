"""EMA fast/slow crossover — the parametrized strategy behind the three rule-based
portfolios (50/200 golden cross, 21/50, 10/21).

Pure event detection over a preloaded technicals panel; no I/O. Entry when the
fast EMA crosses above the slow between consecutive stored rows, exit when it
crosses back below. Transition machinery lives in StateStrategy.
"""

from __future__ import annotations

import pandas as pd

from .base import StateStrategy


class EmaCross(StateStrategy):
    key = "ema_cross"

    def __init__(self, fast: int, slow: int):
        if int(fast) >= int(slow):
            raise ValueError(f"fast EMA ({fast}) must be shorter than slow ({slow})")
        self.fast, self.slow = int(fast), int(slow)

    def required_columns(self) -> tuple[str, ...]:
        return (f"ema_{self.fast}", f"ema_{self.slow}")

    def _state(self, tech: pd.DataFrame) -> pd.Series:
        """fast>slow per row; NaN where either EMA is missing."""
        f = tech[f"ema_{self.fast}"].astype(float)
        s = tech[f"ema_{self.slow}"].astype(float)
        return (f > s).where(f.notna() & s.notna())
