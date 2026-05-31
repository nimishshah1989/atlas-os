"""Backfill the breadth columns added in migration 122.

Populates ``pct_above_ema_20``, ``pct_above_ema_100`` and ``pct_4w_high`` on
``atlas.atlas_market_regime_daily`` across all history. SURGICAL: writes only
those three columns via ``bulk_upsert`` (``ON CONFLICT (date) DO UPDATE SET``
touches only provided columns), so ``regime_state`` and every other column are
left exactly as-is — no regime re-classification.

Vectorised end-to-end: one universe load, pandas groupby/ewm/rolling (no
iterrows). The mv_india_pulse v2 breadth rows auto-flip ``data_gap`` false once
these columns are populated (the MV reads ``col IS NULL``).

Usage (on EC2)::

    python scripts/backfill_breadth_ema_4wh.py
    python scripts/backfill_breadth_ema_4wh.py --start 2024-01-01

Run AFTER ``alembic upgrade`` has applied migration 122 (which adds the two new
columns). Re-runnable; idempotent.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import structlog
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session  # noqa: E402
from atlas.compute.breadth import compute_ma_breadth, compute_pct_4w_high  # noqa: E402
from atlas.compute.regime import _load_stock_data_for_regime  # noqa: E402
from atlas.config import Config  # noqa: E402
from atlas.db import get_engine  # noqa: E402

log = structlog.get_logger()

_WRITE_COLS = ["date", "pct_above_ema_20", "pct_above_ema_100", "pct_4w_high"]


def _existing_dates(engine, start: date, end: date) -> set[date]:
    """Dates that already have a row in atlas_market_regime_daily.

    The upsert's INSERT arm would violate the NOT NULL on ``regime_state`` for a
    brand-new date, so we only emit dates that already exist (every historical
    date does). Guards against silently writing half-rows.
    """
    with open_compute_session(engine) as conn:
        result = conn.execute(
            text(
                "SELECT date FROM atlas.atlas_market_regime_daily "
                "WHERE date BETWEEN :start AND :end"
            ),
            {"start": start, "end": end},
        )
        return {row[0] for row in result}


def backfill(
    engine=None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    """Compute and write the three breadth columns over [start, end]."""
    eng = engine or get_engine()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()

    stock_data = _load_stock_data_for_regime(eng, start, end)
    if stock_data.empty:
        log.warning("breadth_backfill_no_stock_data", start=str(start), end=str(end))
        return 0

    ma = compute_ma_breadth(stock_data)  # 20/50/100/200
    p4wh = compute_pct_4w_high(stock_data)  # 4-week-high
    merged = ma.merge(p4wh, on="date", how="outer").sort_values("date")

    # Keep only the columns we write + restrict to dates that already exist.
    existing = _existing_dates(eng, start, end)
    out = merged.loc[merged["date"].isin(list(existing)), _WRITE_COLS].copy()

    rows_in = len(merged)
    rows_existing = len(out)
    log.info(
        "breadth_backfill_rowcounts",
        computed_dates=rows_in,
        writable_dates=rows_existing,
        dropped_nonexistent=rows_in - rows_existing,
        ema20_nonnull=int(out["pct_above_ema_20"].notna().sum()),
        ema100_nonnull=int(out["pct_above_ema_100"].notna().sum()),
        p4wh_nonnull=int(out["pct_4w_high"].notna().sum()),
    )
    if out.empty:
        return 0

    written = bulk_upsert(
        eng,
        table="atlas.atlas_market_regime_daily",
        columns=_WRITE_COLS,
        rows=df_to_pg_rows(out),
        pk_columns=["date"],
    )
    log.info("breadth_backfill_complete", rows_written=written)

    # Refresh mv_india_pulse so the backfilled breadth columns become visible
    # immediately (otherwise they wait for the nightly mv_refresh_v6_all cron).
    # Non-concurrent: a brief read lock during deploy is acceptable, and it
    # avoids the CONCURRENTLY-can't-run-in-a-transaction constraint.
    _refresh_india_pulse(eng)
    return written


def _refresh_india_pulse(engine) -> None:
    """REFRESH mv_india_pulse (non-concurrent) so backfilled cols show at once."""
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")
        cur.execute("REFRESH MATERIALIZED VIEW atlas.mv_india_pulse")
        raw.commit()
        log.info("mv_india_pulse_refreshed")
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill EMA-20/100 + 4wk-high breadth")
    parser.add_argument(
        "--start", type=str, default=None, help="YYYY-MM-DD (default: HISTORICAL_START_DATE)"
    )
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    start = pd.to_datetime(args.start).date() if args.start else None
    end = pd.to_datetime(args.end).date() if args.end else None
    written = backfill(start_date=start, end_date=end)
    print(f"breadth backfill wrote {written} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
