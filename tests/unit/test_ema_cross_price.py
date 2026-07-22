"""Unit tests for ``atlas.primitives.ema_cross_price``.

Anchored on REAL records (rule #0): MRPL's confirmed EMA13/EMA34 at
2026-07-15 (atlas_foundation.technical_daily). Above the returned price the
provisional fast EMA sits above the slow (golden); below it, death.
"""

from __future__ import annotations

import pytest

from atlas.primitives import ema_cross_price


def _provisional(ema_prev: float, price: float, n: int) -> float:
    """One EMA step: yesterday's EMA + today's price as the forming bar."""
    alpha = 2 / (n + 1)
    return ema_prev + alpha * (price - ema_prev)


def test_cross_price_is_where_provisional_emas_meet() -> None:
    # Real MRPL confirmed EMAs at 2026-07-15.
    ema_fast, ema_slow = 154.459081, 155.315088
    p = ema_cross_price(ema_fast, ema_slow, fast=13, slow=34)
    assert _provisional(ema_fast, p, 13) == pytest.approx(
        _provisional(ema_slow, p, 34), abs=1e-9
    )


def test_cross_price_matches_mrpl_16th_threshold() -> None:
    # The golden cross flashed intraday on 2026-07-16 when MRPL breached this.
    p = ema_cross_price(154.459081, 155.315088, fast=13, slow=34)
    assert p == pytest.approx(163.875, abs=0.005)
