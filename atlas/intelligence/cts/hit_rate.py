from __future__ import annotations

from typing import Any

import pandas as pd


def compute_hit_rate(
    df: pd.DataFrame,
    *,
    signal_col: str,
    stage_filter: int | None,
    forward_col: str,
    return_threshold: float,
) -> dict[str, Any]:
    """Compute hit rate and lift ratio for a binary signal.

    Args:
        df: must have signal_col (bool), stage (int), forward_col (float).
        signal_col: 'is_ppc', 'is_npc', or 'is_contraction'.
        stage_filter: if not None, restrict universe to rows where stage == stage_filter.
        forward_col: 'fwd_ret_5d', 'fwd_ret_10d', or 'fwd_ret_20d'.
        return_threshold: minimum return to count as a 'hit'.

    Returns dict with hit_count, total_signals, hit_rate, base_rate, lift_ratio.
    """
    valid = df[df[forward_col].notna()].copy()
    if stage_filter is not None:
        valid = valid[valid["stage"] == stage_filter]

    if valid.empty:  # type: ignore[union-attr]  # pandas stubs widen df[mask] to include ndarray
        return {
            "hit_count": 0,
            "total_signals": 0,
            "hit_rate": None,
            "base_rate": None,
            "lift_ratio": None,
        }

    signals = valid[valid[signal_col] == True]  # noqa: E712
    non_signals = valid[valid[signal_col] != True]  # noqa: E712

    hit_count = int((signals[forward_col] >= return_threshold).sum())
    total_signals = len(signals)
    hit_rate = hit_count / total_signals if total_signals > 0 else None

    base_count = int((non_signals[forward_col] >= return_threshold).sum())
    base_rate = base_count / len(non_signals) if len(non_signals) > 0 else None

    lift_ratio: float | None = (
        (hit_rate / base_rate) if (hit_rate and base_rate and base_rate > 0) else None
    )

    return {
        "hit_count": hit_count,
        "total_signals": total_signals,
        "hit_rate": hit_rate,
        "base_rate": base_rate,
        "lift_ratio": lift_ratio,
    }
