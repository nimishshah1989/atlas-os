"""Unit tests for ``atlas.compute.benchmarks`` RS standardization (M3).

Hand-traceable: tiny frames where the relative-form RS is computable on paper.
No DB. Locks the ADR-0001/0002 invariance proof as a regression test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.compute.benchmarks import TIER_BENCHMARK, add_relative_strength


@pytest.mark.unit
def test_tier_benchmark_large_anchor_is_nifty50() -> None:
    # ADR-0001: methodology lock anchors Large-tier RS to Nifty 50, not Nifty 100.
    assert TIER_BENCHMARK["Large"] == "NIFTY50"


@pytest.mark.unit
def test_add_relative_strength_uses_relative_form() -> None:
    # ADR-0002: rs = (1+ret)/(1+bench) - 1, NOT the excess form ret - bench.
    df = pd.DataFrame(
        {
            "instrument_id": ["A"],
            "date": [pd.Timestamp("2024-01-31").date()],
            "ret_12m": [0.50],
            "ret_12m_benchmark": [0.20],
        }
    )
    out = add_relative_strength(df, windows={"12m": 252})
    expected = (1 + 0.50) / (1 + 0.20) - 1  # 0.25, not the excess 0.30
    assert abs(out["rs_12m_tier"].iloc[0] - expected) < 1e-12
    assert abs(out["rs_12m_tier"].iloc[0] - 0.30) > 1e-6  # explicitly NOT excess


@pytest.mark.unit
def test_add_relative_strength_covers_1d_and_24m() -> None:
    df = pd.DataFrame(
        {
            "instrument_id": ["A"],
            "date": [pd.Timestamp("2024-01-31").date()],
            "ret_1d": [0.01],
            "ret_1d_benchmark": [0.005],
            "ret_24m": [0.80],
            "ret_24m_benchmark": [0.40],
        }
    )
    out = add_relative_strength(df, windows={"1d": 1, "24m": 504})
    assert "rs_1d_tier" in out.columns
    assert "rs_24m_tier" in out.columns
    assert abs(out["rs_24m_tier"].iloc[0] - ((1 + 0.80) / (1 + 0.40) - 1)) < 1e-12


@pytest.mark.unit
def test_relative_form_preserves_within_tier_ranking() -> None:
    """The ADR invariance proof: within a (date, tier) group the benchmark return
    is constant, so excess (ret-bench) and relative ((1+ret)/(1+bench)-1) produce
    the SAME ordering of stocks. Locks 'no scorecard recompute needed'.
    """
    rng = np.random.default_rng(7)
    rets = rng.normal(0.05, 0.30, 50)
    bench = 0.12  # constant benchmark return for the tier on this date
    df = pd.DataFrame(
        {
            "instrument_id": [f"S{i}" for i in range(50)],
            "date": [pd.Timestamp("2024-01-31").date()] * 50,
            "ret_6m": rets,
            "ret_6m_benchmark": [bench] * 50,
        }
    )
    relative = add_relative_strength(df, windows={"6m": 126})["rs_6m_tier"].to_numpy()
    excess = rets - bench
    # Same argsort ⇒ same within-tier percentile ranks ⇒ same rs_state/scoring.
    assert np.array_equal(np.argsort(relative), np.argsort(excess))
    # And sign is preserved ⇒ breadth metrics (rs>0) unaffected by the form change.
    assert np.array_equal(relative > 0, excess > 0)
