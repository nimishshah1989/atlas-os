"""Deterministic sampling for validation tiers.

Each milestone seeds its sampler from a fixed string so re-runs reproduce the
same picks — required for sign-off audit trails.
"""

from __future__ import annotations

import hashlib
from datetime import date

import pandas as pd
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session


def _seed(milestone: str) -> int:
    """Stable integer seed from a milestone label."""
    return int(hashlib.sha256(milestone.encode()).hexdigest()[:8], 16)


def sample_stock_dates(
    engine: Engine,
    *,
    milestone: str = "M2",
    n_stocks: int = 15,
    n_dates: int = 5,
) -> list[tuple[str, date]]:
    """Return ``(instrument_id, date)`` pairs for Tier 2 hand-validation.

    Per validation framework §3.4: 15 stocks x 5 dates = 75 pairs; Tier 2
    multiplies these against ~25 metrics for a total of 1,875 hand-checks.

    Only pairs where OHLCV source data exists are included — stock/date
    cross-products can produce invalid pairs when a stock listed after the
    sampled date.
    """
    seed = _seed(milestone)
    with open_compute_session(engine) as conn:
        stocks = pd.read_sql(
            """
            SELECT instrument_id FROM atlas.atlas_universe_stocks
            WHERE effective_to IS NULL
            """,
            conn,
        )
        dates = pd.read_sql(
            """
            SELECT DISTINCT date FROM atlas.atlas_stock_metrics_daily
            ORDER BY date
            """,
            conn,
        )

    rng = pd.Series(range(len(stocks))).sample(n=n_stocks, random_state=seed).tolist()
    chosen_stocks = stocks.iloc[rng]["instrument_id"].tolist()

    rng_dates = pd.Series(range(len(dates))).sample(n=n_dates, random_state=seed).tolist()
    chosen_dates = pd.to_datetime(dates.iloc[rng_dates]["date"]).dt.date.tolist()

    # Filter cross-product to only pairs where:
    # (a) OHLCV source data exists on the sampled date, AND
    # (b) stock has ≥252 cumulative bars on or before the sampled date so
    #     rolling indicators (ATR, EMA, vol) have converged. New listings
    #     with fewer bars give spurious deviations in the hand validator.
    with open_compute_session(engine) as conn:
        ohlcv_check = pd.read_sql(
            """
            WITH ranked AS (
                SELECT instrument_id, date,
                       ROW_NUMBER() OVER (
                           PARTITION BY instrument_id ORDER BY date
                       ) AS bar_seq
                FROM public.de_equity_ohlcv
                WHERE instrument_id = ANY(%(stocks)s)
            )
            SELECT instrument_id, date
            FROM ranked
            WHERE date = ANY(%(dates)s::date[])
              AND bar_seq >= 252
            """,
            conn,
            params={
                "stocks": chosen_stocks,
                "dates": [str(d) for d in chosen_dates],
            },
        )
    ohlcv_check["date"] = pd.to_datetime(ohlcv_check["date"]).dt.date
    valid = set(zip(ohlcv_check["instrument_id"], ohlcv_check["date"], strict=False))
    return [(s, d) for s in chosen_stocks for d in chosen_dates if (s, d) in valid]


def sample_stocks_for_states(
    engine: Engine,
    *,
    milestone: str = "M2",
    n: int = 30,
) -> list[str]:
    """Return ``instrument_id`` list for Tier 3 hand-classification (30 stocks).

    Per validation framework §4: 30 stocks x 4 state types = 120 hand-checks.
    """
    seed = _seed(milestone + "_states")
    with open_compute_session(engine) as conn:
        stocks = pd.read_sql(
            """
            SELECT instrument_id FROM atlas.atlas_universe_stocks
            WHERE effective_to IS NULL
            """,
            conn,
        )
    rng = pd.Series(range(len(stocks))).sample(n=n, random_state=seed).tolist()
    return stocks.iloc[rng]["instrument_id"].tolist()
