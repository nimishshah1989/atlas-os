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

import numpy as np
import pandas as pd

import _db
from harness import STAGING_SCHEMA

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

KITE_DAY_CHUNK = 2000            # Kite caps a 'day'-interval request at 2000 days
HIST_START = date(2016, 4, 7)
MIN_INTERVAL = 0.34              # ≥0.34s between request STARTS ≈ 2.9/s (Kite cap 3/s)
SOURCE = "KITE_HISTORICAL"

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


def token_map(kite, symbols: list[str]) -> dict[str, int]:
    """Map NSE tradingsymbol → instrument_token for the requested symbols."""
    want = set(symbols)
    out = {}
    for it in kite.instruments("NSE"):
        sym = it.get("tradingsymbol", "")
        if sym in want and it.get("instrument_token"):
            out[sym] = int(it["instrument_token"])
    return out


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


def _staging_rows(df: pd.DataFrame, iid: str, symbol: str) -> pd.DataFrame:
    # Kite candles are taken as already adjusted ⇒ adj == raw, factor 1.
    return pd.DataFrame({
        "instrument_id": iid, "symbol": symbol, "date": df["date"],
        "open": df["open"], "high": df["high"], "low": df["low"], "close": df["close"],
        "open_adj": df["open"], "high_adj": df["high"], "low_adj": df["low"],
        "close_adj": df["close"], "adj_factor": 1.0,
        "volume": df["volume"].astype("Int64"), "series": "EQ", "source": SOURCE,
    })


def _resolve_ids(symbols: list[str]) -> dict[str, str]:
    df = _db.read_df("select id, symbol from public.de_instrument where symbol = any(:s)",
                     {"s": symbols})
    return {r.symbol: str(r.id) for r in df.itertuples()}


def ingest(symbols: list[str], start: date = HIST_START, end: date | None = None) -> dict:
    end = end or date.today()
    kite = kite_client()
    tmap = token_map(kite, symbols)
    ids = _resolve_ids(symbols)
    written, missing = 0, []
    for sym in symbols:
        if sym not in tmap or sym not in ids:
            missing.append(sym)
            continue
        df = fetch_history(kite, tmap[sym], start, end)
        if df.empty:
            missing.append(sym)
            continue
        rows = _staging_rows(df, ids[sym], sym)
        written += _db.upsert_df(f"{STAGING_SCHEMA}.ohlcv_stock", rows,
                                 ["instrument_id", "date"])
    return {"symbols": len(symbols), "written": written, "missing": missing}


def verify(symbol: str, start: date = HIST_START, end: date | None = None) -> dict:
    """Pull one symbol and report the cleanliness jump-check — is Kite adjusted?"""
    end = end or date.today()
    kite = kite_client()
    tmap = token_map(kite, [symbol])
    if symbol not in tmap:
        return {"symbol": symbol, "error": "no instrument_token on NSE"}
    df = fetch_history(kite, tmap[symbol], start, end)
    c = pd.to_numeric(df["close"], errors="coerce").to_numpy()
    lr = np.abs(c[1:] / c[:-1] - 1) if len(c) > 1 else np.array([0.0])
    i = int(np.nanargmax(lr))
    max_jump = float(np.nanmax(lr))
    return {
        "symbol": symbol, "rows": len(df),
        "first": str(df["date"].min()), "last": str(df["date"].max()),
        "max_1d_jump_pct": round(max_jump * 100, 1),
        "worst_on": str(df["date"].to_numpy()[i + 1]),
        "clean_pass": bool(max_jump <= 0.50),  # harness threshold
    }


def main():
    ap = argparse.ArgumentParser(description="Ingest Kite historical OHLCV → staging")
    ap.add_argument("--verify", metavar="SYMBOL",
                    help="pull one symbol and print the jump-check (is Kite adjusted?)")
    ap.add_argument("--symbols", nargs="*", help="symbols to ingest")
    ap.add_argument("--start", default=str(HIST_START))
    args = ap.parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    if args.verify:
        print(verify(args.verify, start=start))
    elif args.symbols:
        print(ingest(args.symbols, start=start))
    else:
        ap.error("pass --verify SYMBOL or --symbols ...")


if __name__ == "__main__":
    main()
