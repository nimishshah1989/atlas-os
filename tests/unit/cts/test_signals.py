from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from atlas.compute.cts.signals import detect_signals

THRESHOLDS = {
    "cts_ppc_range_multiplier": Decimal("1.5"),
    "cts_ppc_close_pct": Decimal("0.60"),
    "cts_ppc_volume_multiplier": Decimal("1.5"),
    "cts_npc_range_multiplier": Decimal("1.5"),
    "cts_npc_close_pct": Decimal("0.40"),
    "cts_npc_volume_multiplier": Decimal("1.5"),
    "cts_trp_tradeable_min": Decimal("2.0"),
    "cts_contraction_bars": Decimal("5"),
    "cts_contraction_resistance_pct": Decimal("3.0"),
    "cts_stage2_sma_period": Decimal("150"),
    "cts_stage2_slope_min_days": Decimal("20"),
}


def _build_universe(n: int = 40, *, inject_ppc: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    base_close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    rows = []
    for i in range(n):
        c = base_close[i]
        rows.append(
            {
                "instrument_id": "INS1",
                "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                "open": c - 0.2,
                "high": c + 1.0,
                "low": c - 1.0,
                "close": c,
                "volume": 200_000.0,
                "rs_pctile_cross_sector": 0.60,
            }
        )
    if inject_ppc:
        last = rows[-1]
        last["high"] = last["close"] + 8.0
        last["low"] = last["close"] - 4.0
        last["close"] = last["close"] + 6.5
        last["open"] = last["close"] - 2.0  # green candle
        last["volume"] = 600_000.0
    return pd.DataFrame(rows)


def test_detect_signals_returns_required_columns() -> None:
    df = _build_universe()
    out = detect_signals(df, thresholds=THRESHOLDS)
    for col in [
        "is_ppc",
        "ppc_strength",
        "is_npc",
        "npc_strength",
        "is_contraction",
        "is_trigger_bar",
        "trigger_level",
    ]:
        assert col in out.columns, f"missing column {col}"


def test_no_ppc_on_flat_candles() -> None:
    df = _build_universe(inject_ppc=False)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert not out["is_ppc"].any(), "expected no PPC on flat candles"


def test_ppc_strength_in_unit_range() -> None:
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    ppc_rows = out[out["is_ppc"] == True]  # noqa: E712
    if not ppc_rows.empty:
        assert (ppc_rows["ppc_strength"].dropna() >= 0).all()
        assert (ppc_rows["ppc_strength"].dropna() <= 1).all()


def test_npc_not_fired_on_green_candle() -> None:
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    if last["is_ppc"]:
        assert not last["is_npc"]


def test_contraction_fires_on_tightening_setup() -> None:
    """Contraction: tightening range + close near 50-bar high."""
    n = 60
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, n))
    rows = []
    for i in range(n):
        c = closes[i]
        if i >= n - 7:
            spread = 2.0 - (i - (n - 7)) * 0.2
            h, lo = c + spread / 2, c - spread / 2
        else:
            h, lo = c + 2.0, c - 2.0
        rows.append(
            {
                "instrument_id": "INS1",
                "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                "open": c - 0.1,
                "high": h,
                "low": lo,
                "close": c,
                "volume": 200_000.0,
                "rs_pctile_cross_sector": 0.60,
            }
        )
    peak = max(closes)
    # Use 0.99 / 0.995 / 0.975 so close is ~1% below 50-bar high (within con_res=3%)
    # Using 0.98 puts close ~3.9% below which exceeds the 3.0% resistance threshold
    for row in rows[-5:]:
        row["close"] = peak * 0.99
        row["high"] = peak * 0.995
        row["low"] = peak * 0.975
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert out.tail(5)[
        "is_contraction"
    ].any(), "expected contraction to fire on tightening setup near 50-bar high"


def test_short_series_no_crash() -> None:
    """Under-14-bar series must return NaN/False signals, not crash."""
    rows = [
        {
            "instrument_id": "INS1",
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 100_000.0,
            "rs_pctile_cross_sector": 0.5,
        }
        for i in range(10)
    ]
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert "is_ppc" in out.columns
    assert not out["is_ppc"].any(), "no PPC on 10-bar history"
    assert not out["is_npc"].any(), "no NPC on 10-bar history"
    assert not out["is_contraction"].any(), "no contraction on 10-bar history"


def test_npc_fires_on_large_red_volume_candle() -> None:
    """NPC should fire when a large red candle closes in bottom 40% on heavy volume."""
    n = 40
    rng = np.random.default_rng(99)
    base_close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    rows = []
    for i in range(n):
        c = base_close[i]
        rows.append(
            {
                "instrument_id": "INS1",
                "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                "open": c + 0.2,
                "high": c + 1.0,
                "low": c - 1.0,
                "close": c,
                "volume": 200_000.0,
                "rs_pctile_cross_sector": 0.40,
            }
        )
    # Inject NPC: large range, close near the low, red, heavy volume
    last = rows[-1]
    last["open"] = last["close"] + 6.5  # was higher — red candle
    last["high"] = last["close"] + 8.0
    last["low"] = last["close"] - 0.5  # close near low
    last["volume"] = 600_000.0
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert out.iloc[-1][
        "is_npc"
    ], "expected NPC to fire on large red candle near low with heavy volume"
