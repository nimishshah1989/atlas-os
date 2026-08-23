#!/usr/bin/env python3
"""Daily universe-membership journal -> atlas_foundation.atlas_universe_snapshot.

WHY THIS EXISTS: de_index_constituents has no reconstitution history — every row is
effective_to IS NULL (500 live of 500 total). Today's membership is therefore applied
to 2019 lens scores, which is survivorship bias and will inflate any forward-return
study. This table is the fix, and it only works going forward: a day not recorded is
a day lost.

Writes one row per stock per run, whether or not it is in the universe, with the ADV
that produced the decision — so a past membership call can be re-derived, not just
looked up.

    python build_universe_snapshot.py            # append today
    python build_universe_snapshot.py --dry-run  # compute + report, no write
"""

from __future__ import annotations

import argparse
import datetime as dt

import _db
import pandas as pd
import universe_core as U

M = "atlas_foundation"
TGT = f"{M}.atlas_universe_snapshot"


def ensure_table() -> None:
    _db.exec_sql(f"""CREATE TABLE IF NOT EXISTS {TGT} (
        date date NOT NULL,
        instrument_id uuid NOT NULL,
        in_universe boolean NOT NULL,
        adv_median_60d numeric(20,4),
        liquidity_rank integer,
        floor_inr numeric(18,6) NOT NULL,
        computed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (date, instrument_id))""")
    _db.exec_sql(
        f"CREATE INDEX IF NOT EXISTS ix_universe_snapshot_instrument ON {TGT} (instrument_id)"
    )


def snapshot_date() -> dt.date | None:
    """The trading day this snapshot describes.

    eod_cutoff() is an upper BOUND, not a trading date — it returns weekends and
    holidays, and the house rule is that callers anchor to the latest data date at or
    below it. Anchoring matters more here than elsewhere: the date IS the record in a
    journal, so a Sunday-stamped row could never be joined to OHLCV or lens history,
    and the Saturday/Sunday cron runs would each append a duplicate of Friday's
    membership under a date the market never traded. Anchored, a weekend re-run is
    instead a no-op upsert over Friday's row.
    """
    return _db.scalar(
        f"SELECT max(date) FROM {M}.ohlcv_stock WHERE date <= :c", {"c": _db.eod_cutoff()}
    )


def adv_frame() -> pd.DataFrame:
    """One row per stock: trailing-60-trading-day MEDIAN traded value, in rupees.

    LEFT JOIN, so a stock with no recent trading gets adv_median_60d = NULL — "no
    signal", never 0. The window is the most recent 60 DISTINCT trading dates at or
    before the EOD cutoff, not 60 calendar days, so holidays and long weekends cannot
    shorten it and today's partial in-session candle can never enter it.
    """
    return _db.read_df(
        f"""
        WITH d AS (
            SELECT DISTINCT date FROM {M}.ohlcv_stock
            WHERE date <= :cutoff
              AND date > (CAST(:cutoff AS date) - INTERVAL '{U.LOOKBACK_CALENDAR_DAYS} days')
            ORDER BY date DESC LIMIT {U.LOOKBACK_TRADING_DAYS}
        ),
        liq AS (
            SELECT instrument_id,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY close_adj * volume)::numeric
                       AS adv_median_60d
            FROM {M}.ohlcv_stock
            WHERE date IN (SELECT date FROM d)
              AND close_adj IS NOT NULL AND volume IS NOT NULL
            GROUP BY instrument_id
        )
        SELECT im.instrument_id::text AS instrument_id, im.symbol, liq.adv_median_60d
        FROM {M}.instrument_master im
        LEFT JOIN liq ON liq.instrument_id = im.instrument_id
        WHERE im.asset_class = 'stock'
        """,
        {"cutoff": _db.eod_cutoff()},
    )


def held_ids() -> frozenset[str]:
    """instrument_ids with any trade in a portfolio book.

    portfolio_trades.instrument_key holds the instrument_id UUID as text — NOT the
    symbol, despite the name. Joining it against instrument_master.symbol matches zero
    rows, which silently voids the whole retention guarantee, so the join goes through
    instrument_id. Still joined (rather than read straight off the trade) to confirm
    the key is a live stock instrument and to keep etf/fund books out.
    """
    df = _db.read_df(
        f"""SELECT DISTINCT im.instrument_id::text AS instrument_id
            FROM {M}.portfolio_trades pt
            JOIN {M}.instrument_master im
              ON im.instrument_id::text = pt.instrument_key AND im.asset_class = 'stock'"""
    )
    return frozenset(df["instrument_id"].tolist())


def run(dry_run: bool = False) -> dict:
    ensure_table()
    floor = _db.scalar(
        f"SELECT threshold_value FROM {M}.atlas_thresholds WHERE threshold_key = :k AND is_active",
        {"k": U.THRESHOLD_KEY},
    )
    if floor is None:
        raise RuntimeError(f"{U.THRESHOLD_KEY} missing from {M}.atlas_thresholds")
    as_of = snapshot_date()
    if as_of is None:
        raise RuntimeError(f"no {M}.ohlcv_stock rows at or before {_db.eod_cutoff()}")

    adv = adv_frame()
    held = held_ids()
    inside = U.members(adv, floor, held)

    adv["in_universe"] = adv["instrument_id"].isin(list(inside))
    adv["liquidity_rank"] = (
        pd.Series(pd.to_numeric(adv["adv_median_60d"], errors="coerce"))
        .rank(ascending=False, method="first")
        .astype("Int64")
    )
    adv["floor_inr"] = floor
    adv["date"] = as_of

    n_in = int(adv["in_universe"].sum())
    print(
        f"  universe: {n_in} / {len(adv)} stocks at floor "
        f"₹{float(floor) / 1e7:.2f} cr, as of {as_of}"
    )

    if dry_run:
        print("  DRY RUN — no write.")
        return {"written": 0, "dry_run": True, "in_universe": n_in, "date": as_of}

    cols = ["date", "instrument_id", "in_universe", "adv_median_60d", "liquidity_rank", "floor_inr"]
    n = _db.upsert_df(TGT, adv.loc[:, cols], ["date", "instrument_id"])
    return {"written": n, "in_universe": n_in, "date": as_of}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute + report, no write")
    print(run(dry_run=ap.parse_args().dry_run))
