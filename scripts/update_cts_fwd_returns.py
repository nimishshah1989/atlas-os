"""Back-fill fwd_ret_5d / fwd_ret_10d / fwd_ret_20d on past signal rows.

Runs nightly. Finds signal rows where fwd_ret_20d IS NULL and the date is
old enough (>= 30 calendar days ago). Loads prices and computes exact returns.
"""

from __future__ import annotations

import argparse

import pandas as pd
import sqlalchemy as sa
import structlog
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()


def run(*, persist: bool) -> None:
    engine = get_engine()

    with open_compute_session(engine) as conn:
        pending = pd.read_sql(
            """
            SELECT s.instrument_id, s.date
            FROM atlas.atlas_cts_signals_daily s
            WHERE s.fwd_ret_20d IS NULL
              AND (s.is_ppc OR s.is_npc OR s.is_contraction)
              AND s.date <= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY s.date
            LIMIT 5000
        """,
            conn,
        )

    if pending.empty:
        log.info("fwd_returns_nothing_to_update")
        return

    log.info("fwd_returns_pending", rows=len(pending))

    ids = pending["instrument_id"].unique().tolist()
    pending["date"] = pd.to_datetime(pending["date"])
    min_date = pending["date"].min()
    max_date = pending["date"].max()

    with open_compute_session(engine) as conn:
        prices = pd.read_sql(
            """
            SELECT instrument_id, date, close
            FROM public.de_equity_ohlcv
            WHERE instrument_id = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s + INTERVAL '30 days'
            ORDER BY instrument_id, date
        """,
            conn,
            params={"ids": ids, "start": min_date.date(), "end": max_date.date()},
        )

    prices["date"] = pd.to_datetime(prices["date"])

    # Vectorised forward returns — pivot wide, shift per horizon, melt back.
    prices_wide = prices.pivot(index="date", columns="instrument_id", values="close").sort_index()

    result = pending[["date", "instrument_id"]].copy()
    for horizon, col in [(5, "fwd_ret_5d"), (10, "fwd_ret_10d"), (20, "fwd_ret_20d")]:
        fwd = prices_wide.shift(-horizon) / prices_wide - 1
        ret_long = fwd.reset_index().melt(id_vars="date", var_name="instrument_id", value_name=col)
        result = result.merge(ret_long, on=["date", "instrument_id"], how="left")

    if not persist:
        log.info("fwd_returns_computed_dry_run", count=len(result))
        return

    # Bulk UPDATE via temp table (one round-trip, not N individual UPDATEs)
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        result.to_sql(
            "__cts_fwd_tmp",
            conn,
            if_exists="replace",
            index=False,
            dtype={  # type: ignore[arg-type]  # pandas stubs don't accept SQLAlchemy types; runtime OK
                "instrument_id": sa.UUID(),
                "date": sa.Date(),
                "fwd_ret_5d": sa.Numeric(),
                "fwd_ret_10d": sa.Numeric(),
                "fwd_ret_20d": sa.Numeric(),
            },
        )
        conn.execute(
            text("""
            UPDATE atlas.atlas_cts_signals_daily s
            SET fwd_ret_5d = t.fwd_ret_5d,
                fwd_ret_10d = t.fwd_ret_10d,
                fwd_ret_20d = t.fwd_ret_20d
            FROM __cts_fwd_tmp t
            WHERE s.date = t.date AND s.instrument_id = t.instrument_id::uuid
        """)
        )
        conn.execute(text("DROP TABLE IF EXISTS __cts_fwd_tmp"))
    log.info("fwd_returns_updated", count=len(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(persist=args.persist)
