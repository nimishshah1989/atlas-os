"""Liquidity-floor universe membership — the SINGLE place the rule is expressed.

A stock is in Atlas's coverage universe if its trailing 60-day MEDIAN daily traded
value is at least the floor in atlas_thresholds.liquidity_min_traded_value_inr
(methodology §3.3), or if it is held in a portfolio book.

Median, not mean: one block deal must not promote an illiquid name. Sixty days, not
two weeks: measured monthly churn is 5% at 60 days versus 16% at two weeks for a
near-identical member count (spec, 2026-08-23).

Pure — no I/O, no DB access. The SQL that produces the ADV frame lives in
build_universe_snapshot.adv_frame().
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

# 60 trading days back. Calendar span is wider than 60 to absorb weekends/holidays;
# the query takes the most recent 60 DISTINCT trading dates, not 60 calendar days.
LOOKBACK_TRADING_DAYS = 60
LOOKBACK_CALENDAR_DAYS = 150

THRESHOLD_KEY = "liquidity_min_traded_value_inr"


def members(
    adv: pd.DataFrame,
    floor_inr: Decimal,
    held_ids: frozenset[str],
) -> set[str]:
    """instrument_ids in the universe.

    Args:
        adv: frame with ``instrument_id`` and ``adv_median_60d`` (rupees). A NULL
             adv_median_60d means "no signal" and never passes — it is not zero.
        floor_inr: the floor, from atlas_thresholds. Never a literal (rule #4).
        held_ids: instrument_ids held in any portfolio book. Always retained, so a
                  live position cannot silently lose its conviction score.
    """
    if adv.empty:
        return set(held_ids)
    v = pd.Series(pd.to_numeric(adv["adv_median_60d"], errors="coerce"))
    passing = adv.loc[v.notna() & (v >= float(floor_inr)), "instrument_id"]
    return {str(x) for x in passing} | {str(x) for x in held_ids}
