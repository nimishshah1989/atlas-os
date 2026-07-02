"""Tests for forward returns matrix.

3 unit tests (no DB), 2 integration tests (real DB).

Schema note: plan referenced atlas_stock_metrics_daily.close_approx which does
not exist. Actual price source is public.de_equity_ohlcv.close_adj (adjusted
close), keyed by (date, instrument_id) as UUID.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from atlas.intelligence.validation.forward_returns import (
    compute_forward_returns,
    load_price_matrix,
)

from atlas.db import get_engine


@pytest.mark.integration
class TestLoadPriceMatrix:
    def test_returns_wide_matrix(self) -> None:
        eng = get_engine()
        df = load_price_matrix(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )
        # Wide format: dates as index, instruments as columns
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.shape[1] > 0  # at least one instrument
        assert df.shape[0] > 30  # at least 30 trading days in 3 months

    def test_prices_are_positive(self) -> None:
        eng = get_engine()
        df = load_price_matrix(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        # Allow NaN (instruments not trading) but no zero/negative
        non_null = df.stack()
        assert (non_null > 0).all()


class TestComputeForwardReturns:
    def test_simple_5_day_return(self) -> None:
        """If price doubles in 5 days, forward return is 1.0."""
        dates = pd.date_range("2025-01-01", periods=10, freq="B")
        prices = pd.Series([100, 100, 100, 100, 100, 200, 200, 200, 200, 200], index=dates)
        df = pd.DataFrame({"A": prices})
        fwd = compute_forward_returns(df, periods=[5])
        # On day 0, price[0]=100 and price[5]=200 → return = 1.0
        assert fwd.loc[dates[0], ("return_5d", "A")] == pytest.approx(1.0, abs=1e-9)

    def test_nan_for_insufficient_lookahead(self) -> None:
        """Last N rows have NaN because the lookahead window extends past data."""
        dates = pd.date_range("2025-01-01", periods=10, freq="B")
        prices = pd.Series(range(100, 110), index=dates)
        df = pd.DataFrame({"A": prices})
        fwd = compute_forward_returns(df, periods=[5])
        # Last 5 rows should be NaN for return_5d
        assert fwd.loc[dates[-5:], ("return_5d", "A")].isna().all()

    def test_multi_period_columns(self) -> None:
        dates = pd.date_range("2025-01-01", periods=70, freq="B")
        df = pd.DataFrame({"A": np.linspace(100, 200, 70)}, index=dates)
        fwd = compute_forward_returns(df, periods=[5, 21, 63])
        # MultiIndex columns: (period_label, instrument)
        assert ("return_5d", "A") in fwd.columns
        assert ("return_21d", "A") in fwd.columns
        assert ("return_63d", "A") in fwd.columns
