"""Dwell-time tracking + cohort baselines + urgency derivation.

Public API:
  compute_cohort_dwell_baselines(historical_panel) -> DataFrame
  derive_urgency(state, dwell_days, cohort_baseline) -> Literal[...]

Cohort baselines aggregate historical state-episode dwell durations into
per-(cohort, state) statistics (mean / median / p25 / p75 / p95). The
urgency derivation maps a current (state, dwell_days) against the cohort's
distribution to a categorical urgency label.

Urgency polarity:
  - Stage 2A: short dwell = URGENT (fresh, alpha window open); long = LATE
  - Stage 2B: short = NORMAL; long = LATE
  - Stage 2C: short = LATE (reversion soon); long = URGENT (trim now)
  - Stage 3:  short = NORMAL (confirm first); long = URGENT (exit)
  - Stage 1, Stage 4, Uninvestable: always 'n/a' (not actionable)
"""

from __future__ import annotations

from typing import Literal, cast

import pandas as pd

Urgency = Literal["urgent", "normal", "late", "n/a"]

# Per-state rules: (short_label, long_label)
# short_label: returned when dwell_days <= cohort p25
# long_label:  returned when dwell_days >= cohort p75
# else 'normal'
_URGENCY_RULES: dict[str, tuple[Urgency, Urgency]] = {
    "stage_2a": ("urgent", "late"),
    "stage_2b": ("normal", "late"),
    "stage_2c": ("late", "urgent"),
    "stage_3": ("normal", "urgent"),
    "stage_1": ("n/a", "n/a"),
    "stage_4": ("n/a", "n/a"),
    "uninvestable": ("n/a", "n/a"),
}

_BASELINE_COLUMNS = [
    "cohort_key",
    "state",
    "mean_dwell_days",
    "median_dwell_days",
    "p25_dwell_days",
    "p75_dwell_days",
    "p95_dwell_days",
    "n_observations",
]


def compute_cohort_dwell_baselines(historical_panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate state-episode dwell durations into per-(cohort, state) statistics.

    Input columns required:
      instrument_id, date, state, dwell_days, cohort_key

    The `date` column must be present so rows are sorted chronologically
    within each instrument. Sorting by dwell_days instead of date scrambles
    multi-state instruments: all stage_1 rows get grouped together, breaking
    the cumsum-based episode-id logic and collapsing run-lengths to 1.

    Returns DataFrame with columns:
      cohort_key, state, mean_dwell_days, median_dwell_days,
      p25_dwell_days, p75_dwell_days, p95_dwell_days, n_observations

    Episode detection: each run starts where dwell_days == 0. The episode
    length is max(dwell_days) within that run. Multiple instruments produce
    separate episodes even within the same (cohort_key, state).
    """
    if historical_panel.empty:
        return pd.DataFrame(columns=pd.Index(_BASELINE_COLUMNS))

    panel = historical_panel.copy()

    # Sort chronologically so that state transitions are in temporal order.
    # Sorting by dwell_days would group all same-state rows together across
    # different time periods, breaking the cumsum episode-id logic.
    panel = panel.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # Assign a unique episode_id per contiguous run.
    # A new episode starts whenever dwell_days resets to 0.
    # cumsum on a boolean column increments the counter each time dwell_days==0.
    panel["_episode_id"] = (
        panel["instrument_id"].astype(str)
        + "::"
        + panel["state"].astype(str)
        + "::"
        + (panel["dwell_days"] == 0).cumsum().astype(str)
    )

    # Episode length = max(dwell_days) + 1, because dwell_days starts at 0
    # (e.g. dwell_days 0..4 is a 5-day episode, max=4 → length=5).
    episodes = (
        panel.groupby(["_episode_id", "cohort_key", "state"])["dwell_days"]
        .max()
        .add(1)
        .reset_index()
    )

    # Aggregate episode lengths per (cohort_key, state).
    agg = (
        episodes.groupby(["cohort_key", "state"])["dwell_days"]
        .agg(
            mean_dwell_days="mean",
            median_dwell_days="median",
            p25_dwell_days=lambda s: s.quantile(0.25),
            p75_dwell_days=lambda s: s.quantile(0.75),
            p95_dwell_days=lambda s: s.quantile(0.95),
            n_observations="count",
        )
        .reset_index()
    )

    # Round percentile/median columns to nearest integer for readability.
    for col in ("median_dwell_days", "p25_dwell_days", "p75_dwell_days", "p95_dwell_days"):
        agg[col] = agg[col].round().astype("Int64")

    return cast("pd.DataFrame", agg[_BASELINE_COLUMNS])


def derive_urgency(
    state: str,
    dwell_days: int,
    cohort_baseline: dict | None,
) -> Urgency:
    """Map (state, dwell_days, cohort_baseline) to an urgency label.

    cohort_baseline keys: 'p25', 'p75' (others informational, optional).
    If baseline is None or empty, returns 'normal' (or 'n/a' for inactive states).

    Note: uses `is not None` guards (not truthiness) so that p25/p75 == 0
    is handled correctly.
    """
    short_label, long_label = _URGENCY_RULES.get(state, ("n/a", "n/a"))
    if short_label == "n/a":
        return "n/a"

    if not cohort_baseline:
        return "normal"

    p25 = cohort_baseline.get("p25")
    p75 = cohort_baseline.get("p75")

    if p25 is not None and dwell_days <= p25:
        return short_label
    if p75 is not None and dwell_days >= p75:
        return long_label
    return "normal"
