#!/usr/bin/env python3
"""Ingest historical OHLCV from Zerodha Kite → staging (candidate clean source).

Rationale: Kite's historical candles are (per the desk) already corporate-action
adjusted, which would resolve the foundation's #1 blocker — de_equity_ohlcv's
close_adj is NOT split/bonus adjusted (204/500 Nifty-500 fail the jump check).
We do NOT take "it's clean" on faith: `--verify` pulls a known-corp-action name
and runs the harness cleanliness jump-check so the harness is the judge.

Auth reuses the existing Atlas Kite session (atlas.intraday.auth). Kite tokens
expire at midnight IST daily, so a fresh login is required before this runs;
a token can also be passed via the KITE_ACCESS_TOKEN env var for ad-hoc tests.

Requires the Kite Connect **historical-data** subscription (paid add-on).

Cost rule: pure-Python pulls; prints only small summaries.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

import _db
import numpy as np
import pandas as pd
from harness import STAGING_SCHEMA

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

KITE_DAY_CHUNK = 2000  # Kite caps a 'day'-interval request at 2000 days
HIST_START = date(2016, 4, 7)
MIN_INTERVAL = 0.34  # ≥0.34s between request STARTS ≈ 2.9/s (Kite cap 3/s)
SOURCE = "KITE"  # single canonical price source (stocks/ETFs/indices)

_last_call = [0.0]


def _rate_limit() -> None:
    """Min-interval limiter: spaces request starts to ~2.9/s regardless of how
    long the network/DB work between calls took (vs a fixed post-call sleep,
    which stacks on top of latency and wastes half the rate budget)."""
    gap = time.monotonic() - _last_call[0]
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_call[0] = time.monotonic()


def _access_token() -> str:
    tok = os.environ.get("KITE_ACCESS_TOKEN", "").strip()
    if tok:
        return tok
    from atlas.intraday.auth import get_valid_access_token

    return get_valid_access_token(conn_str=_db.db_url())


def kite_client():
    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    kite.set_access_token(_access_token())
    return kite


def fetch_history(kite, token: int, start: date, end: date) -> pd.DataFrame:
    """Daily candles for one instrument_token across [start, end], chunked."""
    frames, cur = [], start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=KITE_DAY_CHUNK), end)
        _rate_limit()
        candles = kite.historical_data(token, cur, chunk_end, "day")
        if candles:
            frames.append(pd.DataFrame(candles))
        cur = chunk_end + timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.drop_duplicates("date").sort_values("date")


# Per-asset write target, PK, and the key used for the incremental floor lookup.
_TABLE = {"stock": "ohlcv_stock", "etf": "ohlcv_etf", "index": "index_prices"}
_PK = {
    "stock": ["instrument_id", "date"],
    "etf": ["ticker", "date"],
    "index": ["index_code", "date"],
}
_KEYCOL = {"stock": "instrument_id::text", "etf": "ticker", "index": "index_code"}
_INCR_BUFFER = 5  # re-fetch a few days of overlap so a missed session self-heals


def targets(asset_classes: list[str] | None) -> pd.DataFrame:
    """Universe to ingest, straight from instrument_master (the kite_token owner).
    No public.de_instrument lookup, no per-run NSE-segment symbol→token remap —
    stocks, ETFs and indices all carry their kite_token here."""
    q = (
        "select instrument_id::text instrument_id, asset_class, symbol, isin, kite_token "
        "from foundation_staging.instrument_master where kite_token is not null"
    )
    params: dict = {}
    if asset_classes:
        q += " and asset_class = any(:ac)"
        params["ac"] = asset_classes
    return _db.read_df(q, params)


def _last_dates(asset_class: str) -> dict[str, date]:
    """Per-instrument last stored date in the asset's table (the incremental floor)."""
    key = _KEYCOL[asset_class]
    df = _db.read_df(
        f"select {key} k, max(date) d from {STAGING_SCHEMA}.{_TABLE[asset_class]} group by 1"
    )
    return dict(zip(df["k"].astype(str), df["d"], strict=False))


def _rows(df: pd.DataFrame, ac: str, r) -> pd.DataFrame:
    """Build the upsert frame for one instrument. Kite candles are taken as already
    corp-action adjusted ⇒ adj == raw, factor 1 (indices carry no adj columns)."""
    base = {
        "date": df["date"],
        "open": df["open"],
        "high": df["high"],
        "low": df["low"],
        "close": df["close"],
        "volume": df["volume"].astype("Int64"),
        "source": SOURCE,
    }
    if ac == "index":
        return pd.DataFrame({"index_code": r.symbol, **base})
    if ac == "etf":
        return pd.DataFrame(
            {
                "ticker": r.symbol,
                "isin": r.isin,
                **base,
                "close_adj": df["close"],
                "adj_factor": 1.0,
            }
        )
    return pd.DataFrame(
        {
            "instrument_id": r.instrument_id,
            "symbol": r.symbol,
            **base,
            "open_adj": df["open"],
            "high_adj": df["high"],
            "low_adj": df["low"],
            "close_adj": df["close"],
            "adj_factor": 1.0,
            "series": "EQ",
        }
    )


def ingest(asset_classes=None, start: date | None = None, end: date | None = None) -> dict:
    """Pull daily candles from Kite for the instrument_master universe and write each
    asset class to its own table. When `start` is None the pull is incremental — each
    instrument starts a few days before its last stored date (full history if new)."""
    kite = kite_client()
    # EOD anchor (D11): the daily ingest stops at the last COMPLETE trading day; the
    # in-session current day is live-only (a separate intraday path pulls it). Pass an
    # explicit `end` (e.g. date.today() via --live) only for the live/intraday mechanism.
    end = end or _db.eod_cutoff()
    tgt = targets(asset_classes)
    written = {"stock": 0, "etf": 0, "index": 0}
    missing: list[str] = []
    for ac in sorted(tgt["asset_class"].unique()):
        floors = _last_dates(ac) if start is None else {}
        sub = tgt[tgt["asset_class"] == ac]
        for n, r in enumerate(sub.itertuples(index=False), 1):
            key = r.instrument_id if ac == "stock" else r.symbol
            st = start or (
                floors[str(key)] - timedelta(days=_INCR_BUFFER)
                if floors.get(str(key))
                else HIST_START
            )
            if st > end:
                continue
            df = fetch_history(kite, int(r.kite_token), st, end)
            if df.empty:
                missing.append(r.symbol)
                continue
            written[ac] += _db.upsert_df(
                f"{STAGING_SCHEMA}.{_TABLE[ac]}", _rows(df, ac, r), _PK[ac]
            )
            if n % 50 == 0:
                print(f"[kite] {ac} {n}/{len(sub)} written={written[ac]:,}", flush=True)
    print(f"[kite] COMPLETE written={written} missing={len(missing)}", flush=True)
    return {"written": written, "missing": missing}


def verify(symbol: str, start: date = HIST_START, end: date | None = None) -> dict:
    """Pull one symbol via its stored kite_token and report the cleanliness jump-check."""
    end = end or date.today()
    kite = kite_client()
    tok = _db.scalar(
        f"select kite_token from {STAGING_SCHEMA}.instrument_master where symbol = :s",
        {"s": symbol},
    )
    if not tok:
        return {"symbol": symbol, "error": "no kite_token in instrument_master"}
    df = fetch_history(kite, int(tok), start, end)
    c = pd.to_numeric(df["close"], errors="coerce").to_numpy()
    lr = np.abs(c[1:] / c[:-1] - 1) if len(c) > 1 else np.array([0.0])
    i = int(np.nanargmax(lr))
    max_jump = float(np.nanmax(lr))
    return {
        "symbol": symbol,
        "rows": len(df),
        "first": str(df["date"].min()),
        "last": str(df["date"].max()),
        "max_1d_jump_pct": round(max_jump * 100, 1),
        "worst_on": str(df["date"].to_numpy()[i + 1]),
        "clean_pass": bool(max_jump <= 0.50),  # harness threshold
    }


def main():
    ap = argparse.ArgumentParser(description="Ingest Kite daily OHLCV → staging (single source)")
    ap.add_argument("--verify", metavar="SYMBOL", help="pull one symbol and print the jump-check")
    ap.add_argument(
        "--asset", nargs="*", choices=["stock", "etf", "index"], help="limit asset classes"
    )
    ap.add_argument("--start", help="YYYY-MM-DD; omit for incremental (per-instrument last date)")
    args = ap.parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    if args.verify:
        print(verify(args.verify, start=start or HIST_START))
    else:
        print(ingest(asset_classes=args.asset, start=start))


if __name__ == "__main__":
    main()
