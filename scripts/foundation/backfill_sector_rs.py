#!/usr/bin/env python3
"""Backfill technical_daily.rs_{1m,3m,6m,12m}_sector (was NULL for every row — D17).

Method (handoff 2026-06-23 task 1, FM-endorsed formula):
    rs_W_sector(stock, date) = ret_W(stock) - ret_W(sector_index)
where ret_W(stock) is ALREADY in technical_daily and ret_W(sector_index) is the sector
index's own positional trailing return over W trading days (1m=21, 3m=63, 6m=126, 12m=252 —
identical to technicals.RETURN_WINDOWS / compute_relative_strength). The stock's sector index
comes from instrument_master.sector -> atlas_sector_master.primary_nse_index -> index_prices.

Why this shape (NOT a per-row UPDATE): an in-place per-row UPDATE on the 6.95M-row
technical_daily hung before. Instead we precompute a tiny sector_index_returns table
(~21 indices x ~5k dates) and run a batched, set-based HASH-JOIN UPDATE (one seq-scan of
technical_daily per date-batch). RULE #0: where the stock return or the sector index return is
absent (e.g. before a young sector index like NIFTY CHEMICALS existed), rs stays NULL — never
a fabricated value.

Idempotent + re-runnable (rebuilds sector_index_returns; the UPDATE is deterministic). Safe to
run nightly after compute_all. Uses ONE DB connection throughout to stay under the Supabase
session-pooler cap (the dev server holds ~14 of 15).

    python backfill_sector_rs.py            # full history (batched by year)
    python backfill_sector_rs.py --latest   # only the most recent date (fast; lights the RS matrix)
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import warnings

import pandas as pd

import _db

FS = "foundation_staging"
# Sector RS windows = the 4 sector columns on technical_daily (no 1d/1w sector).
WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
RS_COLS = [f"rs_{w}_sector" for w in WINDOWS]


def _index_returns(conn) -> pd.DataFrame:
    """Per (sector index, date) positional trailing returns, long form."""
    codes = pd.read_sql(
        f"""select distinct m.primary_nse_index as code
            from {FS}.instrument_master im
            join {FS}.atlas_sector_master m on m.sector_name = im.sector
            where im.sector is not null and m.primary_nse_index is not null""",
        conn,
    )["code"].tolist()
    px = pd.read_sql(
        f"select index_code, date, close from {FS}.index_prices "
        f"where index_code = any(%(codes)s) order by index_code, date",
        conn, params={"codes": codes},
    )
    px["close"] = px["close"].astype(float)
    px = px[px["close"] > 0]  # drop zero/blank deep-history prints (matches compute_all)
    frames = []
    for code, g in px.groupby("index_code", sort=False):
        g = g.sort_values("date")
        out = pd.DataFrame({"index_code": code, "date": g["date"].values})
        c = g["close"]
        for w, n in WINDOWS.items():
            out[f"ret_{w}"] = (c / c.shift(n) - 1.0).values
        frames.append(out)
    long = pd.concat(frames, ignore_index=True)
    ret_cols = [f"ret_{w}" for w in WINDOWS]
    long = long.dropna(subset=ret_cols, how="all")  # keep rows with >=1 real return
    print(f"  sector_index_returns: {len(long):,} rows over {len(codes)} indices")
    return long


def _write_sector_index_returns(conn, long: pd.DataFrame) -> None:
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {FS}.sector_index_returns")
    cur.execute(
        f"""CREATE TABLE {FS}.sector_index_returns (
                index_code text NOT NULL, date date NOT NULL,
                ret_1m numeric, ret_3m numeric, ret_6m numeric, ret_12m numeric,
                PRIMARY KEY (index_code, date))""")
    buf = io.StringIO()
    long.to_csv(buf, index=False, header=False)
    buf.seek(0)
    cur.copy_expert(
        f"COPY {FS}.sector_index_returns "
        "(index_code, date, ret_1m, ret_3m, ret_6m, ret_12m) FROM STDIN WITH CSV",
        buf)
    cur.execute(f"ANALYZE {FS}.sector_index_returns")
    conn.commit()
    cur.close()


# Set-based, hash-join UPDATE. The two driver tables (instrument_master ~2.8k,
# sector_index_returns ~100k) hash into memory; technical_daily is scanned once per batch.
_UPDATE = f"""
UPDATE {FS}.technical_daily t
SET rs_1m_sector  = t.ret_1m  - r.ret_1m,
    rs_3m_sector  = t.ret_3m  - r.ret_3m,
    rs_6m_sector  = t.ret_6m  - r.ret_6m,
    rs_12m_sector = t.ret_12m - r.ret_12m
FROM {FS}.instrument_master im
JOIN {FS}.atlas_sector_master m   ON m.sector_name = im.sector
JOIN {FS}.sector_index_returns r  ON r.index_code = m.primary_nse_index
WHERE t.instrument_id = im.instrument_id
  AND r.date = t.date
  AND t.date >= %(lo)s AND t.date < %(hi)s
"""


def _batched_update(conn, latest_only: bool) -> int:
    cur = conn.cursor()
    span = pd.read_sql(f"select min(date) lo, max(date) hi from {FS}.technical_daily", conn)
    lo, hi = span["lo"].iloc[0], span["hi"].iloc[0]
    if latest_only:
        batches = [(hi, hi + pd.Timedelta(days=1))]
    else:  # one batch per calendar year — each ~600k rows, a bounded transaction
        batches = [(pd.Timestamp(y, 1, 1).date(), pd.Timestamp(y + 1, 1, 1).date())
                   for y in range(lo.year, hi.year + 1)]
    total = 0
    for blo, bhi in batches:
        t0 = time.time()
        cur.execute(_UPDATE, {"lo": str(blo), "hi": str(bhi)})
        conn.commit()
        total += cur.rowcount
        print(f"  {blo}..{bhi}  updated {cur.rowcount:>7,}  ({time.time()-t0:5.1f}s)")
    cur.close()
    return total


def _verify(conn) -> None:
    print("\n=== verify: rs_3m_sector == stock.ret_3m - sector_index.ret_3m (latest date) ===")
    df = pd.read_sql(
        f"""select t.symbol, im.sector, m.primary_nse_index idx, t.date,
                   t.ret_3m, r.ret_3m sec_ret_3m, t.rs_3m_sector,
                   (t.ret_3m - r.ret_3m) expected
            from {FS}.technical_daily t
            join {FS}.instrument_master im on im.instrument_id = t.instrument_id
            join {FS}.atlas_sector_master m on m.sector_name = im.sector
            join {FS}.sector_index_returns r
              on r.index_code = m.primary_nse_index and r.date = t.date
            where t.symbol in ('TCS','HDFCBANK','RELIANCE','SUNPHARMA','TATAMOTORS')
              and t.date = (select max(date) from {FS}.technical_daily)
            order by t.symbol""", conn)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    bad = df[(df["rs_3m_sector"].astype(float) - df["expected"].astype(float)).abs() > 1e-9]
    assert bad.empty, f"MISMATCH rs_3m_sector != ret_3m - sec_ret_3m:\n{bad}"
    cov = pd.read_sql(
        f"""select count(*) n,
                   count(rs_3m_sector) has_3m, count(rs_12m_sector) has_12m
            from {FS}.technical_daily""", conn)
    print(f"\ncoverage: {int(cov['has_3m'][0]):,} / {int(cov['n'][0]):,} rows have rs_3m_sector "
          f"({100*cov['has_3m'][0]/cov['n'][0]:.1f}%); rs_12m_sector {int(cov['has_12m'][0]):,}")
    print("VERIFY OK ✓")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", action="store_true",
                    help="only update the most recent date (fast; lights the RS matrix)")
    args = ap.parse_args()
    warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
    conn = _db.engine().raw_connection()
    try:
        print(f"=== sector-RS backfill -> {FS}.technical_daily ({'LATEST' if args.latest else 'FULL'}) ===")
        t0 = time.time()
        long = _index_returns(conn)
        _write_sector_index_returns(conn, long)
        n = _batched_update(conn, args.latest)
        print(f"\ntotal rows updated: {n:,} in {time.time()-t0:.0f}s")
        _verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
