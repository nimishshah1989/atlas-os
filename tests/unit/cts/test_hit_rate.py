from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.intelligence.cts.hit_rate import compute_hit_rate


def _make_signal_rows(n_signals: int, n_non: int, hit_fraction: float) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n_signals):
        ret = 0.07 if i < int(n_signals * hit_fraction) else 0.02
        rows.append({"is_ppc": True, "stage": 2, "fwd_ret_20d": ret})
    for _ in range(n_non):
        rows.append({"is_ppc": False, "stage": 2, "fwd_ret_20d": rng.uniform(-0.02, 0.06)})
    return pd.DataFrame(rows)


def test_hit_rate_matches_fraction() -> None:
    df = _make_signal_rows(100, 200, hit_fraction=0.70)
    result = compute_hit_rate(
        df,
        signal_col="is_ppc",
        stage_filter=2,
        forward_col="fwd_ret_20d",
        return_threshold=0.05,
    )
    assert abs(result["hit_rate"] - 0.70) < 0.02


def test_lift_ratio_above_one_when_signal_beats_base() -> None:
    df = _make_signal_rows(100, 200, hit_fraction=0.70)
    result = compute_hit_rate(
        df,
        signal_col="is_ppc",
        stage_filter=2,
        forward_col="fwd_ret_20d",
        return_threshold=0.05,
    )
    assert result["lift_ratio"] > 1.0


def test_returns_required_keys() -> None:
    df = _make_signal_rows(50, 100, 0.5)
    result = compute_hit_rate(
        df,
        signal_col="is_ppc",
        stage_filter=None,
        forward_col="fwd_ret_20d",
        return_threshold=0.05,
    )
    for k in ["hit_count", "total_signals", "hit_rate", "base_rate", "lift_ratio"]:
        assert k in result
