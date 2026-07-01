#!/usr/bin/env python3
"""Compute TA-Lib technicals for EVERY instrument → technical_daily (resumable).

Generic over asset class: pulls the adjusted close from the right staging table
(stock→ohlcv_stock, etf→ohlcv_etf, index→index_prices), computes EMA 21/50/200,
RSI14, returns, RS vs N50/N500, and above-EMA flags via the canonical technicals
module, and upserts to foundation_staging.technical_daily.

Incremental BY DATE: a normal run recomputes only instruments whose source OHLCV
extends beyond what technical_daily already holds, and writes only the new tail
(EMAs/RS are still derived from the full history, so the appended rows are exact).
A new trading day therefore costs ~1 upsert/instrument, not a full-history rewrite.
`compute_state` still records each instrument's outcome for visibility.

    python compute_all.py                  # incremental: only instruments with new dates
    python compute_all.py --asset stock
    python compute_all.py --limit 20        # smoke test
    python compute_all.py --redo|--full     # full recompute + rewrite of ALL history
"""

from __future__ import annotations

import argparse
import datetime as dt
import uuid

import _db
import pandas as pd
import technicals as T
from harness import BENCHMARKS, STAGING_SCHEMA

M = STAGING_SCHEMA
_SRC = {
    "stock": (f"{M}.ohlcv_stock", "close_adj", "instrument_id = cast(:k as uuid)"),
    "etf": (f"{M}.ohlcv_etf", "close_adj", "ticker = :k"),
    "index": (f"{M}.index_prices", "close", "index_code = :k"),
}
_RS_COLS = [f"rs_{w}_{b}" for b in BENCHMARKS for w in T.RETURN_WINDOWS]
_VV_COLS = ["atr_14", "bb_width", "vol_ratio_30d", "vol_ratio_60d", "pos_52w"]
_TECH_COLS = (
    ["ema_21", "ema_50", "ema_200", "rsi_14"]
    + [f"ret_{w}" for w in T.RETURN_WINDOWS]
    + _RS_COLS
    + ["above_ema_21", "above_ema_50", "above_ema_200"]
    + _VV_COLS
)


def load_benchmarks() -> dict[str, pd.Series]:
    out = {}
    for suf, code in BENCHMARKS.items():
        df = _db.read_df(
            f"select date, close from {M}.index_prices where index_code = :c order by date",
            {"c": code},
        )
        out[suf] = pd.Series(
            df["close"].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(df["date"]))
        )
    return out


def tech_max_dates() -> dict[str, object]:
    """Per-instrument latest date already in technical_daily (keyed by instrument_id).

    This is the incremental floor: an instrument is recomputed only when its source
    OHLCV has a date beyond this. Keyed by instrument_id (technical_daily carries it
    for every asset class)."""
    df = _db.read_df(
        f"select instrument_id::text id, max(date) d from {M}.technical_daily group by 1"
    )
    return dict(zip(df["id"], df["d"], strict=False))


def _source_max_dates(cutoff) -> dict[tuple, object]:
    """Per-instrument latest available SOURCE date (capped at the EOD cutoff, so an
    in-session partial day doesn't mark the universe stale), keyed by (asset_class,
    key) where key = instrument_id for stocks, else the symbol (etf→ticker,
    index→index_code) — mirroring `_close_series`'s keying."""
    out: dict[tuple, object] = {}
    for ac, (tbl, keycol) in {
        "stock": ("ohlcv_stock", "instrument_id::text"),
        "etf": ("ohlcv_etf", "ticker"),
        "index": ("index_prices", "index_code"),
    }.items():
        df = _db.read_df(
            f"select {keycol} k, max(date) d from {M}.{tbl} where date <= :c group by 1",
            {"c": cutoff},
        )
        for r in df.itertuples(index=False):
            out[(ac, str(r.k))] = r.d
    return out


def targets(asset_classes, incremental, limit, shard=None, floor=None, cutoff=None) -> pd.DataFrame:
    """Instruments to (re)compute. When `incremental`, keep only those whose source
    OHLCV extends beyond what technical_daily already holds — i.e. compute missing
    DATES per instrument, not 'every instrument that isn't done'. `floor` = the
    tech_max_dates() map (computed once by the caller)."""
    q = (
        f"select instrument_id, asset_class, symbol from {M}.instrument_master "
        "where kite_token is not null"
    )
    params: dict = {}
    if asset_classes:
        q += " and asset_class = any(:ac)"
        params["ac"] = asset_classes
    df = _db.read_df(q, params)
    df["instrument_id"] = df["instrument_id"].astype(str)
    if shard:  # k/N: stable hash on uuid hex → disjoint, coordination-free shards
        k, n = shard
        df = df[df["instrument_id"].map(lambda u: int(u.replace("-", "")[:8], 16) % n == k)]
    if incremental:
        floor = floor if floor is not None else tech_max_dates()
        src = _source_max_dates(cutoff if cutoff is not None else _db.eod_cutoff())

        def _stale(r) -> bool:
            key = r.instrument_id if r.asset_class == "stock" else r.symbol
            s = src.get((r.asset_class, str(key)))
            tm = floor.get(r.instrument_id)
            return s is not None and (tm is None or s > tm)

        df = df[df.apply(_stale, axis=1)]
    df = df.sort_values("asset_class")
    return df.head(limit) if limit else df


def _close_series(asset_class: str, iid: str, symbol: str) -> pd.Series:
    tbl, col, where = _SRC[asset_class]
    key = iid if asset_class == "stock" else symbol
    px = _db.read_df(f"select date, {col} as c from {tbl} where {where} order by date", {"k": key})
    return pd.Series(
        px["c"].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(px["date"]))
    )


def _ohlcv_frame(iid: str) -> pd.DataFrame:
    """Adjusted H/L/C + raw volume for a stock, ascending date index."""
    df = _db.read_df(
        f"select date, high_adj, low_adj, close_adj, volume from {M}.ohlcv_stock "
        "where instrument_id = cast(:k as uuid) order by date",
        {"k": iid},
    )
    df.index = pd.DatetimeIndex(pd.to_datetime(df["date"]))
    return df


def compute_one(iid, ac, sym, benches, run_id, floor=None, cutoff=None) -> int:
    close = _close_series(ac, iid, sym)
    # EOD anchor: drop the current in-session day — calculations are as-of the last
    # complete EOD; today's partial candle is live-only.
    if cutoff is not None:
        close = close[[d.date() <= cutoff for d in close.index]]
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
    out["instrument_id"] = iid
    out["asset_class"] = ac
    out["symbol"] = sym
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
            o["high_adj"].astype(float)[mask],
            o["low_adj"].astype(float)[mask],
            o["close_adj"].astype(float)[mask],
            o["volume"].astype(float)[mask],
        ).reindex(close.index)
        for c in _VV_COLS:
            out[c] = vv[c].values
    else:
        for c in _VV_COLS:
            out[c] = None
    out["compute_run_id"] = run_id
    cols = ["instrument_id", "asset_class", "symbol", "date", *_TECH_COLS, "compute_run_id"]
    out = out[cols]
    # Incremental: EMAs/RS are recomputed from the FULL close series (so the new
    # rows are correct), but only the tail beyond the stored floor is written —
    # a normal daily run upserts ~1 row/instrument instead of the whole history.
    if floor is not None:
        out = out[[d > floor for d in out["date"]]]
        if out.empty:
            return 0
    out = out.astype(object).where(pd.notna(out), None)
    return _db.upsert_df(f"{M}.technical_daily", out, ["instrument_id", "date"])


def _mark(iid, ac, sym, status, rows=None, last=None, err=None):
    _db.upsert_df(
        f"{M}.compute_state",
        pd.DataFrame(
            [
                {
                    "instrument_id": iid,
                    "asset_class": ac,
                    "symbol": sym,
                    "status": status,
                    "rows_written": rows,
                    "last_date": last,
                    "error": (err or "")[:500] or None,
                    "updated_at": dt.datetime.now(dt.UTC),
                }
            ]
        ),
        ["instrument_id"],
    )


def run(asset_classes=None, incremental=True, limit=None, shard=None) -> dict:
    run_id = str(uuid.uuid4())
    benches = load_benchmarks()
    for suf, s in benches.items():
        if s.empty:
            raise RuntimeError(f"benchmark {suf} empty — backfill indices first")
    # EOD anchor: never compute past the last complete trading day (today's partial
    # is live-only). Compute the incremental floor once and reuse it for both target
    # selection and per-instrument tail-write filtering.
    cutoff = _db.eod_cutoff()
    floor = tech_max_dates() if incremental else {}
    tgt = targets(asset_classes, incremental, limit, shard, floor=floor, cutoff=cutoff)
    total = len(tgt)
    done = err = nodata = rows_tot = 0
    mode = "incremental" if incremental else "full"
    print(
        f"[compute] targets={total} classes={asset_classes or 'all'} mode={mode} eod={cutoff}",
        flush=True,
    )
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, ac, sym = r.instrument_id, r.asset_class, r.symbol
        try:
            w = compute_one(
                iid,
                ac,
                sym,
                benches,
                run_id,
                floor=floor.get(iid) if incremental else None,
                cutoff=cutoff,
            )
            if w == 0:
                _mark(iid, ac, sym, "no_data")
                nodata += 1
            else:
                _mark(iid, ac, sym, "done", rows=w)
                done += 1
                rows_tot += w
        except Exception as e:
            _mark(iid, ac, sym, "error", err=repr(e))
            err += 1
        if n % 50 == 0 or n == total:
            print(
                f"[compute] {n}/{total} done={done} nodata={nodata} err={err} "
                f"rows={rows_tot:,} last={sym}",
                flush=True,
            )
    res = {
        "targets": total,
        "done": done,
        "no_data": nodata,
        "errors": err,
        "rows_written": rows_tot,
    }
    print(f"[compute] COMPLETE {res}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description="Compute TA-Lib technicals for all → technical_daily")
    ap.add_argument("--asset", nargs="*", choices=["stock", "etf", "index"])
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--redo",
        "--full",
        dest="redo",
        action="store_true",
        help="full recompute+rewrite of ALL history (default is incremental by date)",
    )
    ap.add_argument("--shard", help="k/N — process stable shard k of N (parallel workers)")
    args = ap.parse_args()
    shard = None
    if args.shard:
        k, n = args.shard.split("/")
        shard = (int(k), int(n))
    run(asset_classes=args.asset, incremental=not args.redo, limit=args.limit, shard=shard)


if __name__ == "__main__":
    main()
