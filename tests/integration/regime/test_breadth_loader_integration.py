"""Integration test for the regime stock-data loader's breadth inputs.

Regression (2026-05-31): ``_load_stock_data_for_regime`` SELECTed
``ema_50_stock``/``ema_200_stock`` but omitted ``ema_20_stock`` — even though
``atlas_stock_metrics_daily.ema_20_stock`` is populated. ``compute_ma_breadth``
then NA-filled the missing column, so ``pct_above_ema_20`` came out all-NaN and
the India Pulse "% above 20 EMA" breadth row stayed ``data_gap:true``.

Read-only against the live DB.
"""

from __future__ import annotations

from datetime import date

import pytest

from atlas.compute.regime import _load_stock_data_for_regime
from atlas.db import get_engine


@pytest.mark.integration
def test_loader_supplies_populated_ema_20_stock() -> None:
    """The loader must return a populated ``ema_20_stock`` column so 20-EMA
    breadth is computable (not silently NA-filled downstream)."""
    sd = _load_stock_data_for_regime(get_engine(), date(2026, 5, 1), date(2026, 5, 29))

    assert not sd.empty, "expected stock data for a recent window"
    assert "ema_20_stock" in sd.columns, "loader must SELECT ema_20_stock for 20-EMA breadth"
    assert sd["ema_20_stock"].notna().any(), "ema_20_stock must be populated, not all-NaN"
