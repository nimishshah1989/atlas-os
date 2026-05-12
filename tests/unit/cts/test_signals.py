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
    "cts_stage1b_proximity_pct": Decimal("0.03"),
    "cts_contraction_highest_high_bars": Decimal("50"),
    # New quality filter thresholds
    "cts_ppc_stage_min": Decimal("2"),
    "cts_npc_stage_max": Decimal("3"),
    "cts_ppc_rs_min": Decimal("0.60"),
    "cts_npc_rs_max": Decimal("0.40"),
    "cts_ppc_pp_vol_window": Decimal("10"),
    "cts_ppc_high_proximity_pct": Decimal("15.0"),
}


def _build_universe(n: int = 200, *, inject_ppc: bool = False) -> pd.DataFrame:
    """200-bar steady uptrend → price above rising SMA_150 → Stage 2 at the end."""
    rng = np.random.default_rng(7)
    # Clean uptrend: ensures SMA_150 is computable (needs 150 bars) and price stays above it
    base_close = 100 + np.linspace(0, 30, n) + np.cumsum(rng.normal(0, 0.3, n))
    rows = []
    for i in range(n):
        c = float(base_close[i])
        # Every 3rd bar is slightly lower (creates down-close days for Morales threshold)
        vol = 150_000.0 if i % 3 == 0 else 200_000.0
        rows.append(
            {
                "instrument_id": "INS1",
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                "open": c - 0.2,
                "high": c + 1.0,
                "low": c - 1.0,
                "close": c,
                "volume": vol,
                "rs_pctile_cross_sector": 0.75,  # Strong RS — passes 0.60 gate
            }
        )
    if inject_ppc:
        last = rows[-1]
        c = last["close"]
        last["open"] = c - 2.0  # green candle: close > open
        last["close"] = c + 4.5  # close higher than open
        last["high"] = c + 5.5  # close_pct = (4.5+2.0)/(5.5+1.0+2.0) = 0.76 ≥ 0.60
        last["low"] = c - 3.0
        last["volume"] = 800_000.0  # >> prior down-day volumes (~150k)
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
    assert not ppc_rows.empty, "expected PPC to fire on injected candle"
    assert (ppc_rows["ppc_strength"].dropna() >= 0).all()
    assert (ppc_rows["ppc_strength"].dropna() <= 1).all()


def test_npc_not_fired_on_green_candle() -> None:
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    last = out.iloc[-1]
    assert last["is_ppc"], "expected PPC to fire on injected candle"
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
    """NPC should fire when a large red candle closes in bottom 40% on heavy volume.

    Uses 200-bar downtrend to ensure SMA_150 is available and stage is 3 or 4
    (NPC requires stage >= 3) and RS <= 0.40.
    """
    n = 200
    # Downtrend: price starts high and declines linearly → price below SMA → stage 3/4
    closes = np.linspace(200, 140, n)
    rows = []
    for i in range(n):
        c = float(closes[i])
        # Every 3rd bar is slightly higher (creates up-close days; rest are down-close)
        vol = 150_000.0 if i % 3 != 0 else 200_000.0
        rows.append(
            {
                "instrument_id": "INS1",
                "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                "open": c + 0.2,  # red candle: open > close
                "high": c + 1.0,
                "low": c - 1.0,
                "close": c,
                "volume": vol,
                "rs_pctile_cross_sector": 0.25,  # weak RS < 0.40 gate
            }
        )
    # Inject NPC: large range, close near the low, red, heavy volume
    last = rows[-1]
    c = last["close"]
    last["open"] = c + 6.5  # was higher — red candle
    last["high"] = c + 8.0
    last["low"] = c - 0.5  # close near low → close_pct = 0.5/8.5 ≈ 0.06 ≤ 0.40
    last["volume"] = 800_000.0  # >> prior down-day volumes
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert out.iloc[-1][
        "is_npc"
    ], "expected NPC to fire on large red candle near low with heavy volume"


def test_ppc_requires_stage2() -> None:
    """PPC must not fire in Stage 4 even on a textbook candle."""
    n = 200
    # Downtrend: SMA_150 declining, price below it → Stage 4
    closes = np.linspace(200, 140, n)
    rows = [
        {
            "instrument_id": "INS1",
            "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
            "open": float(closes[i]) - 0.2,
            "high": float(closes[i]) + 1.0,
            "low": float(closes[i]) - 1.0,
            "close": float(closes[i]),
            "volume": 200_000.0,
            "rs_pctile_cross_sector": 0.30,
        }
        for i in range(n)
    ]
    # Inject wide-range green candle with heavy volume on last bar
    rows[-1]["open"] = float(closes[-1]) - 2.0
    rows[-1]["close"] = float(closes[-1]) + 5.0
    rows[-1]["high"] = float(closes[-1]) + 6.0
    rows[-1]["volume"] = 900_000.0
    df = pd.DataFrame(rows)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert not out.iloc[-1]["is_ppc"], "PPC must not fire in Stage 4"


def test_ppc_requires_strong_rs() -> None:
    """PPC must not fire when rs_pctile_cross_sector < 0.60."""
    df = _build_universe(inject_ppc=True)
    # Override RS on last bar below gate
    df.iloc[-1, df.columns.get_loc("rs_pctile_cross_sector")] = 0.35
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert not out.iloc[-1]["is_ppc"], "PPC must not fire when RS < 0.60"


def test_ppc_fires_with_all_quality_gates_met() -> None:
    """PPC fires when Stage 2, strong RS, Morales volume, and geometry all pass."""
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    ppc_rows = out[out["is_ppc"]]
    assert not ppc_rows.empty, "Expected PPC to fire when all quality gates are met"
    assert (ppc_rows["stage"] == 2).all(), "All PPC rows must be Stage 2"


def test_conviction_score_present_and_bounded() -> None:
    """cts_conviction_score must exist and be in [0, 100]."""
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert "cts_conviction_score" in out.columns
    ppc_rows = out[out["is_ppc"]]
    assert not ppc_rows.empty
    scores = ppc_rows["cts_conviction_score"].dropna()
    assert (scores >= 0).all()
    assert (scores <= 100).all()


def test_action_confidence_only_on_ppc_rows() -> None:
    """cts_action_confidence must be False on all non-PPC rows."""
    df = _build_universe(inject_ppc=True)
    out = detect_signals(df, thresholds=THRESHOLDS)
    assert "cts_action_confidence" in out.columns
    non_ppc = out[~out["is_ppc"].fillna(False)]
    assert (
        not non_ppc["cts_action_confidence"].fillna(False).any()
    ), "action_confidence must be False on all non-PPC rows"
