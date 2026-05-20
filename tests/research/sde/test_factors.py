"""Tests for SDE Phase 0 factor generation and liquidity mask."""

from __future__ import annotations

import pandas as pd

from atlas.research.sde.factors import (
    FACTOR_CATALOG,
    generate_factors,
    liquidity_mask,
)


def test_generate_factors_returns_every_catalog_key(ohlcv_panel: pd.DataFrame) -> None:
    factors = generate_factors(ohlcv_panel)
    assert set(factors.keys()) == set(FACTOR_CATALOG.keys())


def test_factor_frame_has_multiindex_and_factor_column(
    ohlcv_panel: pd.DataFrame,
) -> None:
    factors = generate_factors(ohlcv_panel)
    frame = factors["roc_63"]
    assert list(frame.index.names) == ["date", "instrument_id"]
    assert list(frame.columns) == ["factor"]
    assert len(frame) > 0


def test_liquidity_mask_flags_low_traded_value(ohlcv_panel: pd.DataFrame) -> None:
    # Force instrument "ccc" to near-zero volume -> illiquid.
    panel = ohlcv_panel.copy()
    panel.loc[panel["instrument_id"] == "ccc", "volume"] = 1.0
    mask = liquidity_mask(panel, floor_inr=5e7, window=60)
    ccc = mask.xs("ccc", level="instrument_id")
    aaa = mask.xs("aaa", level="instrument_id")
    assert not ccc.any()  # ccc never clears the floor
    assert aaa.tail(100).any()  # aaa does, once the rolling window fills
