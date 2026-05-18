import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def trending_up_ohlcv() -> pd.DataFrame:
    """500 trading days of a steadily uptrending stock."""
    rng = np.random.default_rng(42)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="B").date
    drift = 0.0012  # ~30% annual
    shocks = rng.normal(0, 0.012, n)
    close = 100.0 * np.cumprod(1 + drift + shocks)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.998,
            "high": close * 1.012,
            "low": close * 0.988,
            "close": close,
            "volume": rng.integers(50_000, 200_000, n),
        }
    )


@pytest.fixture
def benchmark_ohlcv() -> pd.DataFrame:
    """500 trading days of benchmark (gentle uptrend)."""
    rng = np.random.default_rng(7)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="B").date
    close = 10_000.0 * np.cumprod(1 + 0.0004 + rng.normal(0, 0.008, n))
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.zeros(n, dtype=int),
        }
    )
