#!/usr/bin/env python3
"""Backfill delivery-% accumulation signals into foundation_staging.delivery_daily.

Load-once + vectorized + fast write: pull the whole delivery series via COPY, compute
PIT rolling signals in pandas (fast groupby-rolling), and bulk-load a FRESH delivery_daily
table via a single COPY (no in-place UPDATE → no 2M-row rewrite/WAL, ~20-30s). The lens
engine LEFT-JOINs delivery_daily into its daily frame, so delivery feeds ONLY the Flow
lens (the technical score is untouched) and delivery lives in its own clean home.

Signals (all PIT — delivery_pct(D) is published EOD with the bhavcopy; trailing windows
use only sessions <= D, in SESSIONS not calendar days):
  delivery_pct          raw daily delivery % (fraction of volume that settles as delivery)
  delivery_avg_30d/60d  trailing means (min 15 / 30 obs -> NULL = illiquid, the floor)
  delivery_trend        delivery_pct / delivery_avg_30d - 1  (raw daily ratio; reference)
  delivery_updown_asym  avg delivery on up-days minus down-days, trailing 30 sessions

The Flow accumulation sub-component reads the SMOOTHED quantities (avg_30d vs avg_60d +
asymmetry) so it is medium-term, matching Flow's quarterly cadence (see compute/flow.py).

Source: public.de_equity_ohlcv.delivery_pct (~72.6% coverage, 2019+; D22 brings it INTO
foundation_staging here). Missing/illiquid -> NULL (RULE #0, never 0).

    python backfill_delivery.py            # full (re)build of delivery_daily
    python backfill_delivery.py --check IID # preview computed signals for one instrument
"""

from __future__ import annotations

import argparse
import io
import time

import _db
import numpy as np
import pandas as pd

M = "foundation_staging"
SRC = "public.de_equity_ohlcv"
TARGET = f"{M}.delivery_daily"
START = "2019-01-01"

DELIVERY_COLS = [
    "delivery_pct",
    "delivery_avg_30d",
    "delivery_avg_60d",
    "delivery_trend",
    "delivery_updown_asym",
]
_KEYS = ["instrument_id", "date"]
_ALL = _KEYS + DELIVERY_COLS


def ensure_table_fresh() -> None:
    _db.exec_sql(f"DROP TABLE IF EXISTS {TARGET}")
    _db.exec_sql(
        f"CREATE TABLE {TARGET} (instrument_id uuid NOT NULL, date date NOT NULL, "
        "delivery_pct numeric, delivery_avg_30d numeric, delivery_avg_60d numeric, "
        "delivery_trend numeric, delivery_updown_asym numeric)"
    )


def load_delivery() -> pd.DataFrame:
    """COPY the whole delivery series (instrument_id, date, delivery_pct, close, volume)."""
    raw = _db.engine().raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET LOCAL statement_timeout = '1200000'")
        buf = io.StringIO()
        cur.copy_expert(
            f"COPY (SELECT instrument_id, date, delivery_pct, close, volume FROM {SRC} "
            f"WHERE delivery_pct IS NOT NULL AND date >= '{START}' "
            "ORDER BY instrument_id, date) TO STDOUT WITH CSV HEADER",
            buf,
        )
        raw.rollback()
        buf.seek(0)
        return pd.read_csv(buf, parse_dates=["date"])
    finally:
        raw.close()


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized PIT rolling signals — fast groupby-rolling (no per-group Python lambda).

    df sorted by (instrument_id, date) -> each group's rows are contiguous + index-ordered,
    so groupby().rolling() results realign to df by index directly."""
    df = df.sort_values(_KEYS).reset_index(drop=True)

    def roll(col, w, mp):
        return (
            df.groupby("instrument_id", sort=False)[col]
            .rolling(w, min_periods=mp)
            .mean()
            .reset_index(level=0, drop=True)
        )

    df["delivery_avg_30d"] = roll("delivery_pct", 30, 15)
    df["delivery_avg_60d"] = roll("delivery_pct", 60, 30)
    df["delivery_trend"] = np.where(
        df["delivery_avg_30d"] > 0, df["delivery_pct"] / df["delivery_avg_30d"] - 1.0, np.nan
    )
    # up/down-day asymmetry: close-to-close direction (flat / first-of-group excluded from both)
    diff = df.groupby("instrument_id", sort=False)["close"].diff()
    df["_d_up"] = df["delivery_pct"].where(diff > 0)
    df["_d_dn"] = df["delivery_pct"].where(diff < 0)
    df["delivery_updown_asym"] = roll("_d_up", 30, 5) - roll("_d_dn", 30, 5)
    return df.drop(columns=["_d_up", "_d_dn"])


def write_copy(df: pd.DataFrame) -> int:
    """One COPY into the fresh delivery_daily table, then add the PK (join index)."""
    out = df[_ALL].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    csv = io.StringIO()
    out.to_csv(csv, index=False, header=False)  # NaN -> empty -> NULL on COPY CSV
    csv.seek(0)
    raw = _db.engine().raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET LOCAL statement_timeout = '1200000'")
        cur.copy_expert(f"COPY {TARGET} ({','.join(_ALL)}) FROM STDIN WITH CSV", csv)
        n = cur.rowcount
        cur.execute(f"ALTER TABLE {TARGET} ADD PRIMARY KEY (instrument_id, date)")
        raw.commit()
        return n
    finally:
        raw.close()


def run() -> dict:
    t0 = time.time()
    ensure_table_fresh()
    print("delivery_daily (re)created", flush=True)
    df = load_delivery()
    print(f"loaded {len(df):,} delivery rows in {time.time() - t0:.0f}s", flush=True)
    t1 = time.time()
    df = compute_signals(df)
    print(
        f"computed signals in {time.time() - t1:.0f}s "
        f"(avg30 non-null {df['delivery_avg_30d'].notna().mean():.0%})",
        flush=True,
    )
    t2 = time.time()
    n = write_copy(df)
    print(f"COPY -> delivery_daily: {n:,} rows in {time.time() - t2:.0f}s", flush=True)
    print(f"DONE in {time.time() - t0:.0f}s total", flush=True)
    return {"rows": n}


def check(iid: str) -> None:
    df = compute_signals(load_delivery())
    print(df[df["instrument_id"].astype(str) == iid].tail(8)[_ALL].to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="instrument_id to preview computed signals")
    args = ap.parse_args()
    check(args.check) if args.check else run()


if __name__ == "__main__":
    main()
