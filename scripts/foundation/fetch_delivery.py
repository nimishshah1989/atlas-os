#!/usr/bin/env python3
"""Fetch NSE security-wise delivery (sec_bhavdata_full) and upsert it into
foundation_staging.delivery_raw (Atlas-owned, single-schema) so the delivery_daily
backfill can compute a COMPLETE rolling series to the latest session.

The standard UDiFF CM bhavcopy (ingest_bhavcopy.py) carries NO delivery; delivery lives
in the separate sec_bhavdata_full_<DDMMYYYY>.csv (cols incl DELIV_QTY, DELIV_PER). PIT
same-day data (published EOD). Idempotent; resumable (re-run re-fills).

    python fetch_delivery.py                          # incremental (since last, → EOD)
    python fetch_delivery.py --start 2026-04-07 --end 2026-06-19   # explicit range
"""

from __future__ import annotations

import argparse
import io
import time
from datetime import date

import _db
import pandas as pd
import requests

H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/",
}
ARCH = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{}.csv"
EQ_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}


def sessions(start: date, end: date) -> list[date]:
    d = _db.read_df(
        "SELECT DISTINCT date FROM foundation_staging.index_prices "
        "WHERE index_code='NIFTY 50' AND date>=:s AND date<=:e ORDER BY date",
        {"s": start, "e": end},
    )
    return [x.date() if hasattr(x, "date") else x for x in d["date"].tolist()]


def fetch_one(d: date) -> pd.DataFrame | None:
    try:
        r = requests.get(ARCH.format(d.strftime("%d%m%Y")), headers=H, timeout=30)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    df = pd.read_csv(io.BytesIO(r.content))
    df.columns = [c.strip() for c in df.columns]
    if "DELIV_PER" not in df.columns:
        return None
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    df = df[df["SERIES"].isin(EQ_SERIES)].copy()
    df["DELIV_PER"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")  # ' -' -> NaN
    df = df[df["DELIV_PER"].notna()]
    out = df[["SYMBOL", "DELIV_PER"]].copy()
    out["date"] = d
    return out


def run(start: date, end: date) -> None:
    sess = sessions(start, end)
    if not sess:
        print("no sessions in window — nothing to fetch", flush=True)
        return
    print(f"{len(sess)} sessions {sess[0]}..{sess[-1]}", flush=True)
    im = _db.read_df(
        "SELECT instrument_id, symbol FROM foundation_staging.instrument_master "
        "WHERE asset_class='stock'"
    )
    sym2iid = dict(
        zip(im["symbol"].astype(str).str.strip(), im["instrument_id"].astype(str), strict=False)
    )
    frames, missing = [], []
    for d in sess:
        f = fetch_one(d)
        if f is None or f.empty:
            missing.append(d)
            print(f"  {d}: MISSING", flush=True)
        else:
            frames.append(f)
            print(f"  {d}: {len(f)} delivery rows", flush=True)
        time.sleep(0.6)
    if not frames:
        print("no delivery fetched")
        return
    allf = pd.concat(frames, ignore_index=True)
    allf["instrument_id"] = allf["SYMBOL"].map(sym2iid)
    allf = allf[allf["instrument_id"].notna()]
    print(
        f"mapped {len(allf)} rows -> {allf['instrument_id'].nunique()} instruments; "
        f"{len(missing)} missing sessions",
        flush=True,
    )

    out = allf[["instrument_id", "date", "DELIV_PER"]].rename(columns={"DELIV_PER": "delivery_pct"})
    out["date"] = out["date"].astype(str)
    # Upsert into the Atlas-owned raw delivery table (single-schema; no public.* hop).
    _db.exec_sql(
        "CREATE TABLE IF NOT EXISTS foundation_staging.delivery_raw ("
        "instrument_id uuid NOT NULL, date date NOT NULL, delivery_pct numeric, "
        "PRIMARY KEY (instrument_id, date))"
    )
    n = _db.upsert_df("foundation_staging.delivery_raw", out, ["instrument_id", "date"])
    print(f"upsert foundation_staging.delivery_raw: {n} rows", flush=True)
    print("DONE", flush=True)


def _default_window() -> tuple[date, date]:
    """Incremental window: a few sessions before the latest delivery_raw date (overlap
    self-heals a missed day) → last complete EOD. Full 2019+ if delivery_raw is empty."""
    end = _db.eod_cutoff()
    last = _db.read_df("SELECT max(date) mx FROM foundation_staging.delivery_raw", {}).iloc[0]["mx"]
    if last is None:
        return date.fromisoformat("2019-01-01"), end
    return (pd.Timestamp(last) - pd.Timedelta(days=7)).date(), end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    args = ap.parse_args()
    if args.start and args.end:
        run(args.start, args.end)
    else:
        s, e = _default_window()
        print(f"incremental delivery window {s}..{e}", flush=True)
        run(s, e)


if __name__ == "__main__":
    main()
