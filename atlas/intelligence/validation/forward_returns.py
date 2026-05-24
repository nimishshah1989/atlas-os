"""Forward-returns matrix builder.

Reads public.de_equity_ohlcv.close_adj into a wide (date × instrument)
DataFrame, then computes simple percentage forward returns over the
requested horizons.

Schema note: atlas_stock_metrics_daily does not have a close price column.
The adjusted close price lives in public.de_equity_ohlcv.close_adj, which
is partitioned by year. The base view de_equity_ohlcv spans all partitions.
instrument_id is UUID in both atlas and de_ tables — they share the same
namespace from de_instrument.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

# Fetch adjusted close from the OHLCV view.
# Accepts ``data_status IN ('raw','validated')`` because JIP's validation step
# sometimes lags or fails — without this, 100% of rows are excluded.
# Falls back to ``close`` when ``close_adj`` is NULL (JIP adjustment-factors
# pipeline is currently not populating close_adj). Identical pattern to
# ``atlas.intelligence.conviction.tier_assignment``.
_PRICE_SQL = """
    SELECT date,
           instrument_id::text,
           COALESCE(close_adj, close) AS close_adj
    FROM public.de_equity_ohlcv
    WHERE date >= :start_date
      AND date <= :end_date
      AND data_status IN ('raw', 'validated')
      AND COALESCE(close_adj, close) > 0
    ORDER BY date
"""


def load_price_matrix(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load close_adj into a wide DataFrame: rows=dates, columns=instrument_ids.

    Returns an empty DataFrame if no rows match the date range.
    Columns are instrument_id strings (UUID). NaN where an instrument
    did not trade on a given day.
    """
    with engine.connect() as conn:
        long_df = pd.read_sql(
            text(_PRICE_SQL),
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )

    if long_df.empty:
        return pd.DataFrame()

    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df["close_adj"] = pd.to_numeric(long_df["close_adj"], errors="coerce")

    wide = long_df.pivot(index="date", columns="instrument_id", values="close_adj")
    wide.index = pd.DatetimeIndex(wide.index)
    wide.columns.name = "instrument_id"

    log.info(
        "price_matrix_loaded",
        n_dates=wide.shape[0],
        n_instruments=wide.shape[1],
        date_range=f"{start_date}..{end_date}",
    )
    return wide


def compute_forward_returns(
    prices: pd.DataFrame,
    *,
    periods: Sequence[int],
) -> pd.DataFrame:
    """Compute forward returns for each (date, instrument) over each period.

    Returns a DataFrame with MultiIndex columns:
      level 0 = "return_{N}d"  (e.g. "return_5d", "return_21d")
      level 1 = instrument_id

    Last N rows of each instrument are NaN where lookahead extends past data.
    Simple percentage return: (price[t+N] / price[t]) - 1.
    """
    frames: list[pd.DataFrame] = []
    for n in periods:
        fwd = prices.shift(-n) / prices - 1.0
        fwd.columns = pd.MultiIndex.from_product(
            [[f"return_{n}d"], fwd.columns.tolist()],
            names=["period", "instrument_id"],
        )
        frames.append(fwd)
    return pd.concat(frames, axis=1)
