"""Compute liquidity-tier membership per instrument per date.

Tiers are defined by 20-day ADV (Average Daily Value = volume × close_adj)
rank within the universe of NSE-listed names. Top 1000 instruments are
placed in one of five tiers; the rest are ``untiered`` and excluded from
conviction scoring.

The ADV window is a calendar 35-day lookback, which yields ~25 trading
days. The HAVING COUNT(*) >= 15 filter excludes instruments with fewer
than 15 trading days of validated OHLCV in that window — protects against
newly-listed names with thin history.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

TIER_BOUNDS: Final[list[tuple[str, int, int]]] = [
    ("tier_1_megacap", 1, 50),
    ("tier_2_largecap", 51, 150),
    ("tier_3_uppermid", 151, 300),
    ("tier_4_lowermid", 301, 500),
    ("tier_5_smallcap", 501, 1000),
]


def assign_tier_from_rank(rank: int) -> str:
    """Return the tier name for a given ADV rank. Ranks > 1000 → 'untiered'."""
    for tier, lo, hi in TIER_BOUNDS:
        if lo <= rank <= hi:
            return tier
    return "untiered"


_ADV_SQL = text("""
    SELECT instrument_id::text AS instrument_id,
           AVG(volume * COALESCE(close_adj, close)) AS adv_20d
    FROM public.de_equity_ohlcv
    WHERE date BETWEEN :window_start AND :window_end
      AND data_status IN ('raw','validated')
      AND volume > 0
      AND COALESCE(close_adj, close) > 0
    GROUP BY instrument_id
    HAVING COUNT(*) >= 15
""")


def compute_tier_membership(engine: Engine, *, as_of: date) -> pd.DataFrame:
    """Rank instruments by 20-day ADV ending ``as_of`` and assign tiers.

    Returns a DataFrame with columns: ``instrument_id, date, tier,
    adv_rank, adv_20d``. Only the top-1000 by ADV are returned;
    instruments below rank 1000 are dropped.
    """
    window_start = as_of - timedelta(days=35)
    with engine.connect() as conn:
        raw = pd.read_sql(
            _ADV_SQL,
            conn,
            params={"window_start": window_start, "window_end": as_of},
        )

    out_cols = ["instrument_id", "date", "tier", "adv_rank", "adv_20d"]

    if raw.empty:
        log.warning("tier_membership_empty", as_of=str(as_of))
        return pd.DataFrame({c: pd.Series(dtype=object) for c in out_cols})

    raw["adv_20d"] = pd.to_numeric(raw["adv_20d"])
    raw = raw.sort_values("adv_20d", ascending=False).reset_index(drop=True)
    raw["adv_rank"] = raw.index + 1

    top_1000 = raw.head(1000).copy()
    top_1000["tier"] = top_1000["adv_rank"].apply(assign_tier_from_rank)
    top_1000["date"] = as_of

    log.info(
        "tier_membership_computed",
        as_of=str(as_of),
        n_top_1000=len(top_1000),
        n_megacap=int((top_1000["tier"] == "tier_1_megacap").sum()),
    )

    result: pd.DataFrame = top_1000.loc[:, out_cols]
    return result
