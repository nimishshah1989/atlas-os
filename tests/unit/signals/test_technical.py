from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from atlas.signals.technical import (
    TechnicalSnapshot,
    _classify_ema_alignment,
    _classify_hh_hl,
    _classify_macd,
    compute_technical_snapshot,
)


def make_ohlcv(n: int = 300, trend: str = "up") -> pd.DataFrame:
    np.random.seed(42)
    base = 1000.0
    if trend == "up":
        prices = base + np.cumsum(np.abs(np.random.randn(n)) * 2)
    else:
        prices = base + np.cumsum(-np.abs(np.random.randn(n)) * 2)
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=n),
            "open": prices * 0.99,
            "high": prices * 1.01,
            "low": prices * 0.98,
            "close": prices,
            "volume": np.random.randint(1_000_000, 5_000_000, n),
        }
    )


def test_compute_technical_snapshot_returns_snapshot():
    df = make_ohlcv(300, "up")
    with patch("atlas.signals.technical._fetch_ohlcv", return_value=df):
        snap = compute_technical_snapshot("HDFCBANK", conn=MagicMock())
    assert isinstance(snap, TechnicalSnapshot)
    assert 0 <= float(snap.rsi_14) <= 100
    valid_macd = ("bullish_cross", "bearish_cross", "above_zero", "below_zero", "neutral")
    assert snap.macd_signal in valid_macd
    assert snap.ema_alignment in ("all_bullish", "above_200", "mixed", "all_bearish")
    assert snap.hh_hl_state in ("confirmed_uptrend", "hh_only", "hl_only", "downtrend", "neutral")


def test_compute_technical_snapshot_uptrend_has_bullish_ema():
    df = make_ohlcv(300, "up")
    with patch("atlas.signals.technical._fetch_ohlcv", return_value=df):
        snap = compute_technical_snapshot("FAKE", conn=MagicMock())
    assert snap.ema_alignment in ("all_bullish", "above_200")


def test_classify_ema_alignment_all_bullish():
    result = _classify_ema_alignment(close=110.0, ema20=108.0, ema50=105.0, ema200=100.0)
    assert result == "all_bullish"


def test_classify_ema_alignment_all_bearish():
    result = _classify_ema_alignment(close=90.0, ema20=92.0, ema50=95.0, ema200=100.0)
    assert result == "all_bearish"


def test_classify_macd_bullish_cross():
    result = _classify_macd(macd=0.5, signal=0.2, prev_macd=0.1, prev_signal=0.3)
    assert result == "bullish_cross"


def test_classify_macd_bearish_cross():
    result = _classify_macd(macd=0.1, signal=0.3, prev_macd=0.4, prev_signal=0.2)
    assert result == "bearish_cross"


def test_classify_macd_above_zero():
    result = _classify_macd(macd=0.3, signal=0.1, prev_macd=0.2, prev_signal=0.1)
    assert result == "above_zero"


def test_classify_macd_below_zero():
    result = _classify_macd(macd=-0.3, signal=-0.1, prev_macd=-0.2, prev_signal=-0.1)
    assert result == "below_zero"


def test_classify_hh_hl_confirmed_uptrend():
    result = _classify_hh_hl(hh=True, hl=True)
    assert result == "confirmed_uptrend"


def test_classify_hh_hl_downtrend():
    result = _classify_hh_hl(hh=False, hl=False)
    assert result == "downtrend"
