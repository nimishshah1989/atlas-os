#!/usr/bin/env python3
"""Compute TA-Lib technicals for EVERY instrument → technical_daily (resumable).

Generic over asset class: pulls the adjusted close from the right staging table
(stock→ohlcv_stock, etf→ohlcv_etf, index→index_prices), computes EMA 21/50/200,
RSI14, returns, RS vs N50/N500, and above-EMA flags via the canonical technicals
module, and upserts to foundation_staging.technical_daily.

Resumability: every instrument's outcome is recorded in compute_state; re-running
skips status='done'. Run after (or alongside) the backfill, in the background.

    python compute_all.py                  # all instruments with OHLCV, pending
    python compute_all.py --asset stock
    python compute_all.py --limit 20        # smoke test
    python compute_all.py --redo
"""

from __future__ import annotations

import argparse
import datetime as dt
import uuid

import pandas as pd

import _db
import technicals as T
from harness import BENCHMARKS, STAGING_SCHEMA

M = STAGING_SCHEMA
_SRC = {
    "stock": (f"{M}.ohlcv_stock", "close_adj", "instrument_id = cast(:k as uuid)"),
    "etf":   (f"{M}.ohlcv_etf", "close_adj", "ticker = :k"),
    "index": (f"{M}.index_prices", "close", "index_code = :k"),
}
_RS_COLS = [f"rs_{w}_{b}" for b in BENCHMARKS for w in T.RETURN_WINDOWS]
_VV_COLS = ["atr_14", "bb_width", "vol_ratio_30d", "vol_ratio_60d", "pos_52w"]
_TECH_COLS = (["ema_21", "ema_50", "ema_200", "rsi_14"]
              + [f"ret_{w}" for w in T.RETURN_WINDOWS] + _RS_COLS
              + ["above_ema_21", "above_ema_50", "above_ema_200"] + _VV_COLS)


def load_benchmarks() -> dict[str, pd.Series]:
    out = {}
    for suf, code in BENCHMARKS.items():
        df = _db.read_df(f"select date, close from {M}.index_prices "
                         "where index_code = :c order by date", {"c": code})
        out[suf] = pd.Series(df["close"].astype(float).values,
                             index=pd.DatetimeIndex(pd.to_datetime(df["date"])))
    return out


def targets(asset_classes, only_pending, limit, shard=None) -> pd.DataFrame:
    q = (f"select instrument_id, asset_class, symbol from {M}.instrument_master "
         "where kite_token is not null")
    params: dict = {}
    if asset_classes:
        q += " and asset_class = any(:ac)"; params["ac"] = asset_classes
    df = _db.read_df(q, params)
    df["instrument_id"] = df["instrument_id"].astype(str)
    if shard:  # k/N: stable hash on uuid hex → disjoint, coordination-free shards
        k, n = shard
        df = df[df["instrument_id"].map(lambda u: int(u.replace("-", "")[:8], 16) % n == k)]
    if only_pending:
        done = _db.read_df(f"select instrument_id from {M}.compute_state where status='done'")
        df = df[~df["instrument_id"].isin(set(done["instrument_id"].astype(str)))]
    df = df.sort_values("asset_class")
    return df.head(limit) if limit else df


def _close_series(asset_class: str, iid: str, symbol: str) -> pd.Series:
    tbl, col, where = _SRC[asset_class]
    key = iid if asset_class == "stock" else symbol
    px = _db.read_df(f"select date, {col} as c from {tbl} where {where} order by date",
                     {"k": key})
    return pd.Series(px["c"].astype(float).values,
                     index=pd.DatetimeIndex(pd.to_datetime(px["date"])))


def _ohlcv_frame(iid: str) -> pd.DataFrame:
    """Adjusted H/L/C + raw volume for a stock, ascending date index."""
    df = _db.read_df(
        f"select date, high_adj, low_adj, close_adj, volume from {M}.ohlcv_stock "
        "where instrument_id = cast(:k as uuid) order by date", {"k": iid})
    df.index = pd.DatetimeIndex(pd.to_datetime(df["date"]))
    return df


def compute_one(iid, ac, sym, benches, run_id) -> int:
    close = _close_series(ac, iid, sym)
    # Drop non-positive closes: zero/blank prints in deep (2000s) history and
    # spurious pre-listing rows. They are bad data (the cleanliness axis flags
    # them separately) and a zero denominator overflows the return columns.
    close = close[close > 0]
    if len(close) < 2:
        return 0
    tech = T.compute_price_technicals(close)
    for suf in BENCHMARKS:
        tech = tech.join(T.compute_relative_strength(close, benches[suf], suf))
    flags = T.above_ema_flags(close, tech)
    out = pd.DataFrame(index=close.index)
    out["instrument_id"] = iid; out["asset_class"] = ac; out["symbol"] = sym
    out["date"] = [d.date() for d in close.index]
    for c in ["ema_21", "ema_50", "ema_200", "rsi_14"] + [f"ret_{w}" for w in T.RETURN_WINDOWS]:
        out[c] = tech[c].values
    for c in _RS_COLS:
        out[c] = tech[c].values
    for p in T.EMA_PERIODS:
        out[f"above_ema_{p}"] = flags[f"above_ema_{p}"].values
    # volatility / volume / 52w-position (stocks only — needs H/L/V)
    if ac == "stock":
        o = _ohlcv_frame(iid)
        mask = o["close_adj"].astype(float) > 0
        vv = T.compute_volatility_volume(
            o["high_adj"].astype(float)[mask], o["low_adj"].astype(float)[mask],
            o["close_adj"].astype(float)[mask], o["volume"].astype(float)[mask],
        ).reindex(close.index)
        for c in _VV_COLS:
            out[c] = vv[c].values
    else:
        for c in _VV_COLS:
            out[c] = None
    out["compute_run_id"] = run_id
    cols = ["instrument_id", "asset_class", "symbol", "date"] + _TECH_COLS + ["compute_run_id"]
    out = out[cols].astype(object).where(pd.notna(out), None)
    return _db.upsert_df(f"{M}.technical_daily", out, ["instrument_id", "date"])


def _mark(iid, ac, sym, status, rows=None, last=None, err=None):
    _db.upsert_df(f"{M}.compute_state", pd.DataFrame([{
        "instrument_id": iid, "asset_class": ac, "symbol": sym, "status": status,
        "rows_written": rows, "last_date": last, "error": (err or "")[:500] or None,
        "updated_at": dt.datetime.now(dt.UTC)}]), ["instrument_id"])


def run(asset_classes=None, only_pending=True, limit=None, shard=None) -> dict:
    run_id = str(uuid.uuid4())
    benches = load_benchmarks()
    for suf, s in benches.items():
        if s.empty:
            raise RuntimeError(f"benchmark {suf} empty — backfill indices first")
    tgt = targets(asset_classes, only_pending, limit, shard)
    total = len(tgt); done = err = nodata = rows_tot = 0
    print(f"[compute] targets={total} classes={asset_classes or 'all'}", flush=True)
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, ac, sym = r.instrument_id, r.asset_class, r.symbol
        try:
            w = compute_one(iid, ac, sym, benches, run_id)
            if w == 0:
                _mark(iid, ac, sym, "no_data"); nodata += 1
            else:
                _mark(iid, ac, sym, "done", rows=w); done += 1; rows_tot += w
        except Exception as e:
            _mark(iid, ac, sym, "error", err=repr(e)); err += 1
        if n % 50 == 0 or n == total:
            print(f"[compute] {n}/{total} done={done} nodata={nodata} err={err} "
                  f"rows={rows_tot:,} last={sym}", flush=True)
    res = {"targets": total, "done": done, "no_data": nodata, "errors": err,
           "rows_written": rows_tot}
    print(f"[compute] COMPLETE {res}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description="Compute TA-Lib technicals for all → technical_daily")
    ap.add_argument("--asset", nargs="*", choices=["stock", "etf", "index"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--shard", help="k/N — process stable shard k of N (parallel workers)")
    args = ap.parse_args()
    shard = None
    if args.shard:
        k, n = args.shard.split("/"); shard = (int(k), int(n))
    run(asset_classes=args.asset, only_pending=not args.redo, limit=args.limit, shard=shard)


if __name__ == "__main__":
    main()
