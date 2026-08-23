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

    python build_universe_snapshot.py            # append the latest trading day
    python build_universe_snapshot.py --dry-run  # compute + report, no write
    python build_universe_snapshot.py --as-of 2026-08-18   # rebuild one past day
"""

from __future__ import annotations

import argparse
import datetime as dt
from decimal import Decimal

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
        floor_inr numeric(18,6) NOT NULL,
        computed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (date, instrument_id))""")
    _db.exec_sql(
        f"CREATE INDEX IF NOT EXISTS ix_universe_snapshot_instrument ON {TGT} (instrument_id)"
    )


def threshold(key: str) -> Decimal:
    v = _db.scalar(
        f"SELECT threshold_value FROM {M}.atlas_thresholds WHERE threshold_key = :k AND is_active",
        {"k": key},
    )
    if v is None:
        raise RuntimeError(f"{key} missing from {M}.atlas_thresholds")
    return v


def snapshot_date(cutoff: dt.date | None = None) -> dt.date | None:
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
        f"SELECT max(date) FROM {M}.ohlcv_stock WHERE date <= :c",
        {"c": cutoff or _db.eod_cutoff()},
    )


def adv_frame(cutoff: dt.date, min_obs: int) -> pd.DataFrame:
    """One row per stock: trailing-60-trading-day MEDIAN traded value, in rupees.

    Traded value is `close * volume` — the raw close, not close_adj. volume has no
    adjusted twin, so close_adj * volume is neither actual rupees transacted nor a
    consistently adjusted series: after a split the adjusted close drops by the split
    factor while volume does not, and the name's traded value would collapse for 60
    sessions for a reason that has nothing to do with liquidity.

    A median needs a middle, so a name with fewer than `min_obs` traded sessions in
    the window — or whose last print is older than the window's final few dates — gets
    adv_median_60d = NULL. NULL is "no signal", never 0 and never "low": members()
    already excludes it, so the guard needs no second code path. The LEFT JOIN then
    keeps a row for every stock regardless.

    The window is the most recent 60 DISTINCT trading dates at or before `cutoff`, so
    holidays and long weekends cannot shorten it and today's partial in-session candle
    can never enter it.
    """
    return _db.read_df(
        f"""
        WITH d AS (
            SELECT DISTINCT date FROM {M}.ohlcv_stock
            WHERE date <= :cutoff
              AND date > (CAST(:cutoff AS date) - INTERVAL '{U.LOOKBACK_CALENDAR_DAYS} days')
            ORDER BY date DESC LIMIT {U.LOOKBACK_TRADING_DAYS}
        ),
        recent AS (
            SELECT date FROM d ORDER BY date DESC LIMIT {U.RECENCY_TRADING_DAYS}
        ),
        liq AS (
            SELECT instrument_id,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume)::numeric
                       AS adv_median_60d
            FROM {M}.ohlcv_stock
            WHERE date IN (SELECT date FROM d)
              AND close IS NOT NULL AND volume IS NOT NULL
            GROUP BY instrument_id
            HAVING count(*) >= :min_obs
               AND max(date) IN (SELECT date FROM recent)
        )
        SELECT im.instrument_id::text AS instrument_id, im.symbol, liq.adv_median_60d
        FROM {M}.instrument_master im
        LEFT JOIN liq ON liq.instrument_id = im.instrument_id
        WHERE im.asset_class = 'stock'
        """,
        {"cutoff": cutoff, "min_obs": min_obs},
    )


def held_ids() -> frozenset[str]:
    """instrument_ids CURRENTLY held in a portfolio book — net open position > 0.

    Not "ever traded": the clause exists so a live position cannot silently lose its
    conviction score, and an exited position has no score to lose. Ever-traded turns a
    safety valve into a ratchet that only grows (654 ever-traded against 150 actually
    held, of which 504 are fully exited).

    Netting is per (portfolio_id, instrument_key) — netting across books would let one
    book's sell cancel another's buy. portfolio_trades.instrument_key holds the
    instrument_id UUID as text, NOT the symbol despite the name; joining it against
    instrument_master.symbol matches zero rows and silently voids the whole guarantee.
    """
    df = _db.read_df(
        f"""WITH net AS (
                SELECT portfolio_id, instrument_key,
                       SUM(CASE WHEN side = 'buy' THEN qty ELSE -qty END) AS net_qty
                FROM {M}.portfolio_trades
                WHERE asset_class = 'stock'
                GROUP BY portfolio_id, instrument_key
            )
            SELECT DISTINCT im.instrument_id::text AS instrument_id
            FROM net
            JOIN {M}.instrument_master im
              ON im.instrument_id::text = net.instrument_key AND im.asset_class = 'stock'
            WHERE net.net_qty > 0"""
    )
    return frozenset(df["instrument_id"].tolist())


def run(dry_run: bool = False, as_of: dt.date | None = None) -> dict:
    floor = threshold(U.THRESHOLD_KEY)
    min_obs = int(threshold(U.THRESHOLD_KEY_MIN_OBS))
    as_of = snapshot_date(as_of)
    if as_of is None:
        raise RuntimeError(f"no {M}.ohlcv_stock rows at or before the cutoff")

    adv = adv_frame(as_of, min_obs)
    inside = U.members(adv, floor, held_ids())

    adv["in_universe"] = adv["instrument_id"].isin(list(inside))
    adv["floor_inr"] = floor
    adv["date"] = as_of
    adv["computed_at"] = pd.Timestamp.now(tz="Asia/Kolkata")

    n_in = int(adv["in_universe"].sum())
    print(
        f"  universe: {n_in} / {len(adv)} stocks at floor "
        f"₹{float(floor) / 1e7:.2f} cr, min {min_obs} obs, as of {as_of}"
    )

    if dry_run:
        print("  DRY RUN — no write.")
        return {"written": 0, "dry_run": True, "in_universe": n_in, "date": as_of}

    ensure_table()
    cols = ["date", "instrument_id", "in_universe", "adv_median_60d", "floor_inr", "computed_at"]
    n = _db.upsert_df(TGT, adv.loc[:, cols], ["date", "instrument_id"])
    return {"written": n, "in_universe": n_in, "date": as_of}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute + report, no write")
    ap.add_argument(
        "--as-of",
        type=dt.date.fromisoformat,
        default=None,
        help="rebuild one past day (YYYY-MM-DD)",
    )
    a = ap.parse_args()
    print(run(dry_run=a.dry_run, as_of=a.as_of))
