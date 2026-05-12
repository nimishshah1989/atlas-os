"""One-time bulk backfill of fwd_ret_5d / fwd_ret_10d / fwd_ret_20d.

The nightly update_cts_fwd_returns.py handles incremental PPC/NPC rows.
This script populates ALL 298k signal rows so the IC engine has a
full 504-day observation window (n~50,000 pairs vs n~100 today).

Approach: pivot prices wide → shift(-horizon) / pivot − 1 → melt →
batch UPDATE via temp table (one DB round-trip per instrument batch).

Batches by instrument to bound peak memory (~200 instruments per batch
→ 200 × 700 dates × 3 floats ≈ 3 MB per batch).

Usage:
    python -m scripts.backfill_fwd_returns_bulk [--batch-size 200] [--dry-run]
"""

from __future__ import annotations

import argparse
from datetime import date
from typing import cast

import pandas as pd
import sqlalchemy as sa
import structlog
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine

log = structlog.get_logger()

BATCH_SIZE = 200  # instruments per batch


def _load_pending(engine) -> pd.DataFrame:
    """Return all (instrument_id, date) pairs that still need fwd returns."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT instrument_id::text AS instrument_id, date
            FROM atlas.atlas_cts_signals_daily
            WHERE fwd_ret_5d IS NULL
              AND date <= CURRENT_DATE - INTERVAL '10 days'
            ORDER BY instrument_id, date
            """,
            conn,
        )


def _load_prices(engine, ids: list[str], min_date: date, max_date: date) -> pd.DataFrame:
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT instrument_id::text AS instrument_id, date, close
            FROM public.de_equity_ohlcv
            WHERE instrument_id = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s + INTERVAL '45 days'
            ORDER BY instrument_id, date
            """,
            conn,
            params={"ids": ids, "start": min_date, "end": max_date},
        )
    df["date"] = pd.to_datetime(df["date"])
    return df


def _compute_fwd_returns(pending_batch: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Vectorised forward returns via pivot → shift → melt."""
    prices_wide = prices.pivot(index="date", columns="instrument_id", values="close").sort_index()
    result = pending_batch.copy()
    result["date"] = pd.to_datetime(result["date"])

    for horizon, col in [(5, "fwd_ret_5d"), (10, "fwd_ret_10d"), (20, "fwd_ret_20d")]:
        shifted = prices_wide.shift(-horizon)
        fwd = shifted / prices_wide - 1
        ret_long = fwd.reset_index().melt(id_vars="date", var_name="instrument_id", value_name=col)
        result = result.merge(ret_long, on=["date", "instrument_id"], how="left")

    # Only keep rows where we actually have a 5d return
    return result.dropna(subset=["fwd_ret_5d"])


def _upsert_batch(engine, df: pd.DataFrame) -> int:
    """Write df to temp table, UPDATE signals, drop temp. Returns row count."""
    cols = ["instrument_id", "date", "fwd_ret_5d", "fwd_ret_10d", "fwd_ret_20d"]
    write_df = df[cols].copy()

    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        write_df.to_sql(
            "__cts_fwd_bulk_tmp",
            conn,
            if_exists="replace",
            index=False,
            dtype={  # type: ignore[arg-type]
                "instrument_id": sa.Text(),
                "date": sa.Date(),
                "fwd_ret_5d": sa.Numeric(8, 6),
                "fwd_ret_10d": sa.Numeric(8, 6),
                "fwd_ret_20d": sa.Numeric(8, 6),
            },
        )
        result = conn.execute(
            text("""
            UPDATE atlas.atlas_cts_signals_daily s
            SET fwd_ret_5d  = t.fwd_ret_5d,
                fwd_ret_10d = t.fwd_ret_10d,
                fwd_ret_20d = t.fwd_ret_20d
            FROM __cts_fwd_bulk_tmp t
            WHERE s.date             = t.date
              AND s.instrument_id    = t.instrument_id::uuid
            """)
        )
        conn.execute(text("DROP TABLE IF EXISTS __cts_fwd_bulk_tmp"))

    return result.rowcount


def run(batch_size: int = BATCH_SIZE, *, dry_run: bool = False) -> None:
    engine = get_engine()

    log.info("backfill_fwd_returns_start", dry_run=dry_run)

    pending = _load_pending(engine)
    if pending.empty:
        log.info("nothing_to_backfill")
        return

    pending["date"] = pd.to_datetime(pending["date"]).dt.date

    all_ids = pending["instrument_id"].unique().tolist()
    total_pending = len(pending)
    log.info("pending_rows", rows=total_pending, instruments=len(all_ids))

    total_updated = 0
    for batch_start in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[batch_start : batch_start + batch_size]
        batch_df = cast(pd.DataFrame, pending[pending["instrument_id"].isin(batch_ids)])

        min_date = cast(date, batch_df["date"].min())
        max_date = cast(date, batch_df["date"].max())

        prices = _load_prices(engine, batch_ids, min_date, max_date)
        if prices.empty:
            log.warning("no_prices_for_batch", batch_start=batch_start)
            continue

        result = _compute_fwd_returns(batch_df, prices)

        if dry_run:
            log.info(
                "dry_run_batch",
                batch=batch_start // batch_size + 1,
                computed=len(result),
                sample_ic=float(result["fwd_ret_5d"].mean()) if not result.empty else None,
            )
            continue

        updated = _upsert_batch(engine, result)
        total_updated += updated

        batch_num = batch_start // batch_size + 1
        total_batches = (len(all_ids) + batch_size - 1) // batch_size
        log.info(
            "batch_complete",
            batch=f"{batch_num}/{total_batches}",
            updated=updated,
            total_updated=total_updated,
        )

    log.info("backfill_fwd_returns_complete", total_updated=total_updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch_size, dry_run=args.dry_run)
