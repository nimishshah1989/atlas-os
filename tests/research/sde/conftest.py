"""Shared fixtures for Signal Discovery Engine tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlcv_panel() -> pd.DataFrame:
    """Deterministic 3-instrument, 400-trading-day OHLCV long DataFrame.

    Columns: date, instrument_id, open, high, low, close, volume.
    """
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2022-01-03", periods=400)
    frames: list[pd.DataFrame] = []
    for i, iid in enumerate(["aaa", "bbb", "ccc"]):
        steps = rng.normal(0.0005, 0.015, size=len(dates))
        close = 100 * (1 + i * 0.1) * np.exp(np.cumsum(steps))
        high = close * (1 + rng.uniform(0, 0.02, len(dates)))
        low = close * (1 - rng.uniform(0, 0.02, len(dates)))
        open_ = close * (1 + rng.normal(0, 0.005, len(dates)))
        volume = rng.integers(500_000, 5_000_000, len(dates)).astype(float)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "instrument_id": iid,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
