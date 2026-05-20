"""Tests for SDE Phase 0 data loaders."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.research.sde.data import adjust_ohlc, mask_extreme_moves


def test_adjust_ohlc_rescales_ohlc_by_adjustment_ratio() -> None:
    long_df = pd.DataFrame(
        {
            "date": ["2024-01-01"],
            "instrument_id": ["aaa"],
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [100.0],
            "close_adj": [50.0],
            "volume": [1000.0],
        }
    )
    out = adjust_ohlc(long_df)
    # ratio = close_adj / close = 0.5 — open/high/low halved, close = close_adj
    assert out.loc[0, "open"] == 50.0
    assert out.loc[0, "high"] == 55.0
    assert out.loc[0, "low"] == 45.0
    assert out.loc[0, "close"] == 50.0


def test_adjust_ohlc_falls_back_when_close_adj_null() -> None:
    long_df = pd.DataFrame(
        {
            "date": ["2024-01-01"],
            "instrument_id": ["aaa"],
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [100.0],
            "close_adj": [None],
            "volume": [1000.0],
        }
    )
    out = adjust_ohlc(long_df)
    # close_adj null -> ratio 1.0, OHLC unchanged, close = raw close
    assert out.loc[0, "open"] == 100.0
    assert out.loc[0, "close"] == 100.0


def test_mask_extreme_moves_nulls_split_like_rows() -> None:
    # Instrument "aaa": a clean series with one -50% jump (unadjusted split).
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=4).tolist(),
            "instrument_id": ["aaa"] * 4,
            "open": [100.0, 101.0, 50.0, 51.0],
            "high": [100.0, 101.0, 50.0, 51.0],
            "low": [100.0, 101.0, 50.0, 51.0],
            "close": [100.0, 102.0, 51.0, 52.0],  # +2%, -50%, +2%
            "volume": [1000.0, 1000.0, 1000.0, 1000.0],
        }
    )
    out = mask_extreme_moves(panel, max_daily_move=0.40)
    out = out.sort_values("date").reset_index(drop=True)
    # The -50% row (index 2) has its price columns nulled; volume kept.
    assert np.isnan(out.loc[2, "close"])
    assert np.isnan(out.loc[2, "open"])
    assert out.loc[2, "volume"] == 1000.0
    # Non-extreme rows are untouched.
    assert out.loc[0, "close"] == 100.0
    assert out.loc[1, "close"] == 102.0
