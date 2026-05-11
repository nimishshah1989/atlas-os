"""IC computation engine.

Pure pandas / numpy / scipy — no I/O. Provides per-date Spearman rank IC,
rolling-window IC, quantile spread, and turnover. Built from primitives
(no alphalens) so behaviour is explicit and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import cast

import numpy as np
import pandas as pd
import structlog
from scipy import stats

log = structlog.get_logger()


@dataclass(frozen=True)
class ICResult:
    """One IC observation across a window."""

    mean_ic: float
    ic_std: float
    ic_t_stat: float
    n_observations: int
    window_start: pd.Timestamp | None = None
    window_end: pd.Timestamp | None = None


def _align_factor_to_returns(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
) -> pd.DataFrame:
    """Align (date, instrument_id) MultiIndex factor to wide returns DataFrame.

    Returns long DataFrame with columns: factor, fwd_return, indexed by
    (date, instrument_id). Drops rows where either is NaN.
    """
    long_returns = returns_wide.stack()
    long_returns.name = "fwd_return"
    long_returns.index = long_returns.index.set_names(["date", "instrument_id"])

    aligned = factor.join(long_returns, how="inner")
    return aligned.dropna(subset=["factor", "fwd_return"])


def _spearman_or_nan(group: pd.DataFrame) -> float:
    """Per-date Spearman rank correlation; NaN if too few observations."""
    if len(group) < 5:
        return float("nan")
    res = stats.spearmanr(group["factor"], group["fwd_return"])
    return float(cast(float, res.statistic))  # pyright: ignore[reportAttributeAccessIssue]


def compute_ic_over_window(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
) -> ICResult:
    """Compute IC (Spearman rank correlation) per date across instruments,
    then return the mean and t-stat across dates.

    factor: MultiIndex (date, instrument_id), column 'factor'
    returns_wide: DataFrame indexed by date, instruments as columns
    """
    aligned = _align_factor_to_returns(factor, returns_wide)

    if aligned.empty:
        return ICResult(
            mean_ic=float("nan"),
            ic_std=float("nan"),
            ic_t_stat=float("nan"),
            n_observations=0,
        )

    ic_per_date = aligned.groupby(level="date", group_keys=False).apply(_spearman_or_nan)
    ic_per_date = ic_per_date.dropna()

    if len(ic_per_date) < 2:
        return ICResult(
            mean_ic=float("nan"),
            ic_std=float("nan"),
            ic_t_stat=float("nan"),
            n_observations=len(ic_per_date),
        )

    mean_ic = float(ic_per_date.mean())
    ic_std = float(ic_per_date.std(ddof=1))
    t_stat = mean_ic / (ic_std / np.sqrt(len(ic_per_date))) if ic_std > 0 else float("nan")

    return ICResult(
        mean_ic=mean_ic,
        ic_std=ic_std,
        ic_t_stat=t_stat,
        n_observations=len(ic_per_date),
        window_start=cast("pd.Timestamp | None", ic_per_date.index.min()),
        window_end=cast("pd.Timestamp | None", ic_per_date.index.max()),
    )


def compute_rolling_ic(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
    *,
    window_days: int,
    step_days: int = 21,
) -> list[ICResult]:
    """Compute IC over rolling windows. Returns one ICResult per window."""
    all_dates = factor.index.get_level_values("date").unique().sort_values()
    if len(all_dates) < window_days:
        return []

    results: list[ICResult] = []
    start_i = 0
    while start_i + window_days <= len(all_dates):
        window_dates = all_dates[start_i : start_i + window_days]
        window_factor = factor.loc[window_dates]
        window_returns = returns_wide.loc[returns_wide.index.intersection(window_dates)]
        results.append(compute_ic_over_window(window_factor, window_returns))
        start_i += step_days

    return results


def _bucket_quantiles(group: pd.DataFrame, n_quantiles: int) -> pd.DataFrame:
    """Assign per-date quantile labels; NaN on degenerate groups."""
    group = group.copy()
    try:
        group["quantile"] = pd.qcut(group["factor"], q=n_quantiles, labels=False, duplicates="drop")
    except ValueError:
        group["quantile"] = np.nan
    return group


def compute_quantile_spread(
    factor: pd.DataFrame,
    returns_wide: pd.DataFrame,
    *,
    n_quantiles: int = 5,
) -> float:
    """Compute Q_top minus Q_bottom mean forward return.

    Quantiles are computed per date (cross-sectional bucketing). Returns the
    raw per-period spread — caller is responsible for annualization.
    """
    aligned = _align_factor_to_returns(factor, returns_wide)
    if aligned.empty:
        return float("nan")

    bucketed = (
        aligned.groupby(level="date", group_keys=False)
        .apply(_bucket_quantiles, n_quantiles=n_quantiles)
        .dropna(subset=["quantile"])
    )
    if bucketed.empty:
        return float("nan")

    top = bucketed[bucketed["quantile"] == n_quantiles - 1]["fwd_return"].mean()
    bot = bucketed[bucketed["quantile"] == 0]["fwd_return"].mean()

    return float(top - bot)


def compute_turnover(
    factor: pd.DataFrame,
    *,
    n_quantiles: int = 5,
) -> float:
    """Average fraction of instruments that change top-quintile membership
    day-over-day, scaled to monthly (×21 trading days).
    """
    top_sets: list[set[object]] = []
    dates_sorted = factor.index.get_level_values("date").unique().sort_values()
    for d in dates_sorted:
        snapshot = factor.loc[d]
        if len(snapshot) < n_quantiles:
            continue
        try:
            q = pd.qcut(snapshot["factor"], q=n_quantiles, labels=False, duplicates="drop")
        except ValueError:
            continue
        q_series = cast(pd.Series, q)
        top_index = cast(pd.Index, q_series.index[q_series == n_quantiles - 1])
        top_sets.append(set(top_index.tolist()))

    if len(top_sets) < 2:
        return float("nan")

    deltas: list[float] = []
    for prev_set, curr_set in pairwise(top_sets):
        if not prev_set:
            continue
        added = len(curr_set - prev_set)
        deltas.append(added / max(1, len(prev_set)))

    if not deltas:
        return float("nan")

    daily_turnover = float(np.mean(deltas))
    return daily_turnover * 21.0
