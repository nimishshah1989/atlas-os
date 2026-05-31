"""Unit tests for the gold-numéraire RS variant in ``atlas.compute.stocks``.

M3 (ADR-0002): ``rs_{w}_tier_gold`` is redefined as the DIRECT stock-vs-gold
relative-strength ratio ``(1 + ret_stock) / (1 + ret_gold) - 1`` across all 7
RS windows (was the deflated-excess form at 1w/1m/3m only). Hand-traceable
frames, no DB.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.compute.benchmarks import GOLD_BENCHMARK
from atlas.compute.primitives import RS_WINDOWS
from atlas.compute.stocks import _gold_relative_strength


@pytest.mark.unit
def test_gold_rs_uses_direct_stock_vs_gold_form() -> None:
    # ADR-0002: rs_{w}_tier_gold = (1+ret_stock)/(1+ret_gold) - 1, the DIRECT
    # stock-vs-gold ratio — NOT the old deflated-excess rs_{w}_tier/(1+ret_gold).
    d = pd.Timestamp("2024-01-31").date()
    stock_ret = 0.30
    gold_ret = 0.10
    # Production frames always carry all 7 RS windows; the assertion focuses on 3m.
    df = pd.DataFrame(
        {
            "instrument_id": ["A"],
            "date": [d],
            **{f"ret_{w}": [stock_ret] for w in RS_WINDOWS},
            # an excess-form rs_3m_tier value that the OLD code would have deflated
            "rs_3m_tier": [0.18],
        }
    )
    cache = pd.DataFrame(
        {
            "benchmark_code": [GOLD_BENCHMARK],
            "date": [d],
            **{f"ret_{w}": [gold_ret] for w in RS_WINDOWS},
        }
    )

    out = _gold_relative_strength(df, cache)
    expected = (1 + stock_ret) / (1 + gold_ret) - 1
    assert abs(out["rs_3m_tier_gold"].iloc[0] - expected) < 1e-12
    # explicitly NOT the old deflated-excess form rs_3m_tier / (1 + ret_gold)
    old_form = 0.18 / (1 + gold_ret)
    assert abs(out["rs_3m_tier_gold"].iloc[0] - old_form) > 1e-6


@pytest.mark.unit
def test_gold_rs_covers_all_seven_windows() -> None:
    d = pd.Timestamp("2024-01-31").date()
    stock = {w: 0.05 * (i + 1) for i, w in enumerate(RS_WINDOWS)}
    gold = {w: 0.02 * (i + 1) for i, w in enumerate(RS_WINDOWS)}
    df = pd.DataFrame(
        {
            "instrument_id": ["A"],
            "date": [d],
            **{f"ret_{w}": [stock[w]] for w in RS_WINDOWS},
        }
    )
    cache = pd.DataFrame(
        {
            "benchmark_code": [GOLD_BENCHMARK],
            "date": [d],
            **{f"ret_{w}": [gold[w]] for w in RS_WINDOWS},
        }
    )

    out = _gold_relative_strength(df, cache)
    for w in RS_WINDOWS:
        col = f"rs_{w}_tier_gold"
        assert col in out.columns, f"missing {col}"
        expected = (1 + stock[w]) / (1 + gold[w]) - 1
        assert abs(out[col].iloc[0] - expected) < 1e-12


@pytest.mark.unit
def test_gold_rs_missing_gold_yields_na_for_all_windows() -> None:
    d = pd.Timestamp("2024-01-31").date()
    df = pd.DataFrame(
        {
            "instrument_id": ["A"],
            "date": [d],
            **{f"ret_{w}": [0.1] for w in RS_WINDOWS},
        }
    )
    cache = pd.DataFrame({"benchmark_code": [], "date": [], **{f"ret_{w}": [] for w in RS_WINDOWS}})

    out = _gold_relative_strength(df, cache)
    for w in RS_WINDOWS:
        assert f"rs_{w}_tier_gold" in out.columns
        assert pd.isna(out[f"rs_{w}_tier_gold"].iloc[0])
