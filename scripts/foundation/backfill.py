#!/usr/bin/env python3
"""Full Kite backfill: 25y OHLCV for the whole universe → staging (resumable).

Drives foundation_staging.instrument_master (kite_token not null) through Kite's
historical API into the right staging table per asset class:
    stock → ohlcv_stock (instrument_id)   etf → ohlcv_etf (ticker)   index → index_prices (index_code)

Kite candles are already corp-action adjusted, so adj == raw (factor 1) at write;
genuine demergers are handled later by the harness whitelist, not here.

Resumability: every instrument's outcome is recorded in backfill_state; re-running
skips status='done'. Safe to kill/restart (e.g. across a Kite token refresh).
Rate-limited via ingest_kite.THROTTLE_S. Run in the background / tmux.

    python backfill.py                       # all pending, max depth
    python backfill.py --asset index etf     # only those classes
    python backfill.py --limit 20            # smoke test
    python backfill.py --redo                # ignore prior 'done' state
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

import _db
import ingest_kite as ik
from harness import STAGING_SCHEMA

HIST_START = dt.date(2000, 1, 1)   # Kite returns from each instrument's true start
M = f"{STAGING_SCHEMA}"


def targets(asset_classes: list[str] | None, only_pending: bool,
            limit: int | None) -> pd.DataFrame:
    q = (f"select instrument_id, asset_class, symbol, isin, kite_token "
         f"from {M}.instrument_master where kite_token is not null")
    params: dict = {}
    if asset_classes:
        q += " and asset_class = any(:ac)"
        params["ac"] = asset_classes
    df = _db.read_df(q, params)
    df["instrument_id"] = df["instrument_id"].astype(str)
    if only_pending:
        done = _db.read_df(f"select instrument_id from {M}.backfill_state where status='done'")
        done_ids = set(done["instrument_id"].astype(str))
        df = df[~df["instrument_id"].isin(done_ids)]
    # widest-history first (stocks), then etf, then index — biggest pulls early
    df = df.sort_values("asset_class")
    return df.head(limit) if limit else df


def _write(asset_class: str, symbol: str, iid: str, isin, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"].astype("Int64")
    if asset_class == "stock":
        rows = pd.DataFrame({
            "instrument_id": iid, "symbol": symbol, "date": df["date"],
            "open": o, "high": h, "low": l, "close": c,
            "open_adj": o, "high_adj": h, "low_adj": l, "close_adj": c,
            "adj_factor": 1.0, "volume": v, "series": "EQ", "source": ik.SOURCE})
        return _db.upsert_df(f"{M}.ohlcv_stock", rows, ["instrument_id", "date"])
    if asset_class == "etf":
        rows = pd.DataFrame({
            "ticker": symbol, "isin": isin, "date": df["date"],
            "open": o, "high": h, "low": l, "close": c, "close_adj": c,
            "adj_factor": 1.0, "volume": v, "source": ik.SOURCE})
        return _db.upsert_df(f"{M}.ohlcv_etf", rows, ["ticker", "date"])
    if asset_class == "index":
        rows = pd.DataFrame({
            "index_code": symbol, "date": df["date"],
            "open": o, "high": h, "low": l, "close": c, "volume": v, "source": ik.SOURCE})
        return _db.upsert_df(f"{M}.index_prices", rows, ["index_code", "date"])
    return 0


def _mark(iid, ac, sym, status, rows=None, df=None, err=None):
    first = str(df["date"].min()) if df is not None and len(df) else None
    last = str(df["date"].max()) if df is not None and len(df) else None
    _db.upsert_df(f"{M}.backfill_state", pd.DataFrame([{
        "instrument_id": iid, "asset_class": ac, "symbol": sym, "status": status,
        "rows_written": rows, "first_date": first, "last_date": last,
        "error": (err or "")[:500] or None, "updated_at": dt.datetime.now(dt.UTC),
    }]), ["instrument_id"])


def run(asset_classes=None, only_pending=True, limit=None, end=None) -> dict:
    end = end or dt.date.today()
    kite = ik.kite_client()
    tgt = targets(asset_classes, only_pending, limit)
    total = len(tgt)
    print(f"[backfill] targets={total} classes={asset_classes or 'all'} "
          f"depth>={HIST_START} end={end}", flush=True)
    done = err = nodata = rows_tot = 0
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, ac, sym = r.instrument_id, r.asset_class, r.symbol
        try:
            df = ik.fetch_history(kite, int(r.kite_token), HIST_START, end)
            if df.empty:
                _mark(iid, ac, sym, "no_data"); nodata += 1
            else:
                w = _write(ac, sym, iid, r.isin, df)
                _mark(iid, ac, sym, "done", rows=w, df=df); done += 1; rows_tot += w
        except Exception as e:
            msg = repr(e)
            _mark(iid, ac, sym, "error", err=msg); err += 1
            if any(t in msg for t in ("TokenException", "Insufficient permission",
                                      "api_key", "access_token")):
                print(f"[backfill] AUTH FAILURE at {sym}: {msg[:160]} — stopping; "
                      "re-auth and re-run to resume.", flush=True)
                break
        if n % 25 == 0 or n == total:
            print(f"[backfill] {n}/{total}  done={done} nodata={nodata} err={err} "
                  f"rows={rows_tot:,}  last={sym}", flush=True)
    res = {"targets": total, "done": done, "no_data": nodata, "errors": err,
           "rows_written": rows_tot}
    print(f"[backfill] COMPLETE {res}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description="Full Kite backfill → staging (resumable)")
    ap.add_argument("--asset", nargs="*", choices=["stock", "etf", "index"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", action="store_true", help="ignore prior 'done' state")
    args = ap.parse_args()
    run(asset_classes=args.asset, only_pending=not args.redo, limit=args.limit)


if __name__ == "__main__":
    main()
