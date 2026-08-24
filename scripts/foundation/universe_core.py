"""Liquidity-floor universe membership — the SINGLE place the rule is expressed.

A stock is in Atlas's coverage universe if its trailing 60-day MEDIAN daily traded
value is at least the floor in atlas_thresholds.liquidity_min_traded_value_inr
(methodology §3.3), or if it is currently held in a portfolio book.

Median, not mean: one block deal must not promote an illiquid name. That guarantee
only holds if the median is taken over enough sessions to have a middle — a median of
two prints IS the block deal — so the ADV is NULL below
atlas_thresholds.liquidity_min_observations_60d traded sessions rather than low, and
NULL again when the last print is more than
atlas_thresholds.liquidity_recency_trading_days sessions from the window's end, since
a stale median is not a current one. NULL never passes here, so neither guard needs a
second code path.

Sixty days, not two weeks: measured monthly churn is 5% at 60 days versus 16% at two
weeks for a near-identical member count (spec, 2026-08-23).

Pure — no I/O, no DB access. The SQL that produces the ADV frame lives in
build_universe_snapshot.adv_frame().
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

# 60 trading days back. Calendar span is wider than 60 to absorb weekends/holidays;
# the query takes the most recent 60 DISTINCT trading dates, not 60 calendar days.
# These two stay code constants deliberately: they define what "60-day median" MEANS
# (the measurement window), rather than tuning a gate applied to it. The three gate
# knobs below are FM-tunable from /admin/thresholds; changing the window is a
# methodology change, not a setting.
LOOKBACK_TRADING_DAYS = 60
LOOKBACK_CALENDAR_DAYS = 150

THRESHOLD_KEY = "liquidity_min_traded_value_inr"
THRESHOLD_KEY_MIN_OBS = "liquidity_min_observations_60d"
THRESHOLD_KEY_RECENCY = "liquidity_recency_trading_days"


def members(
    adv: pd.DataFrame,
    floor_inr: Decimal,
    held_ids: frozenset[str],
) -> set[str]:
    """instrument_ids in the universe.

    Args:
        adv: frame with ``instrument_id`` and ``adv_median_60d`` (rupees). A NULL
             adv_median_60d means "no signal" — too few sessions, or none — and never
             passes. It is not zero and it is not low.
        floor_inr: the floor, from atlas_thresholds. Never a literal (rule #4).
        held_ids: instrument_ids with a net open position (> 0) in ANY portfolio book —
                  backtest and simulated books included, not live books only. Always
                  retained. The over-inclusion is deliberate: this is a safety valve,
                  and its two failure modes are not symmetric. Scoring a simulated
                  position costs a row; letting a real position silently lose its
                  conviction score is the thing being guarded against. Bounded, because
                  an exited position is not held and is not retained.
    """
    # The pd.Series() wrap is load-bearing for pyright, not decoration: to_numeric is
    # typed as returning a broad union (it can take scalars), so .notna()/>= on the bare
    # result costs 18 ratchet errors. Same pattern as portfolio_sweep.py:56.
    v = pd.Series(pd.to_numeric(adv["adv_median_60d"], errors="coerce"))
    passing = adv.loc[v.notna() & (v >= float(floor_inr)), "instrument_id"]
    return {str(x) for x in passing} | {str(x) for x in held_ids}
