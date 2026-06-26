#!/usr/bin/env python3
"""Ingest Screener market cap + face value per stock -> foundation_staging.equity_marketcap.

The weighting source for roll-ups (D24/D21a follow-up): every in-DB candidate failed
(de_index_constituents weights NULL, tv_metrics.market_cap inconsistent, shares_outstanding
empty). Screener's Market Cap is reliable (RELIANCE ₹17.9L Cr, TCS ₹7.7L Cr — verified) and
we already have the warm-session fetcher. Shares = market_cap / our OHLCV close; free-float
cap = shares × price × (1 − promoter%). Rate-limited, resumable (skips already-fetched).

    python fetch_marketcap.py            # all stocks
    python fetch_marketcap.py --limit 50 # smoke test
"""

from __future__ import annotations

import argparse
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import _db
import pandas as pd
import requests

_H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,*/*",
    "Referer": "https://www.screener.in/",
}
_tls = threading.local()


def _session() -> requests.Session:
    """One warmed Session per thread (Screener strips data without warm cookies;
    a shared session across threads races, so each worker gets its own)."""
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(_H)
        try:
            s.get("https://www.screener.in/", timeout=20)  # warm cookies
        except Exception:
            pass
        _tls.s = s
    return s


M = "foundation_staging"
TGT = f"{M}.equity_marketcap"


def ensure_table() -> None:
    _db.exec_sql(f"""CREATE TABLE IF NOT EXISTS {TGT} (
        instrument_id uuid PRIMARY KEY, symbol text, market_cap_cr numeric,
        face_value numeric, fetched_at timestamptz)""")


def _topval(html: str, label: str) -> float | None:
    m = re.search(
        re.escape(label) + r'\s*</span>.*?<span class="number">\s*([0-9,]+\.?[0-9]*)', html, re.S
    )
    return float(m.group(1).replace(",", "")) if m else None


def _get(sym: str) -> str | None:
    s = _session()
    for path in (f"company/{sym}/consolidated/", f"company/{sym}/"):
        try:
            r = s.get(f"https://www.screener.in/{path}", timeout=25)
            if r.status_code == 200 and "Market Cap" in r.text:
                return r.text
        except Exception:
            pass
    return None


def _fetch_one(r) -> dict | None:
    html = _get(r["symbol"])
    mc = _topval(html, "Market Cap") if html else None
    if not mc:
        return None
    return {
        "instrument_id": str(r["instrument_id"]),
        "symbol": r["symbol"],
        "market_cap_cr": mc,
        "face_value": _topval(html, "Face Value"),
        "fetched_at": datetime.now(UTC),
    }


def run(limit: int | None, workers: int = 6) -> None:
    ensure_table()
    done = set(
        _db.read_df(f"SELECT symbol FROM {TGT} WHERE market_cap_cr IS NOT NULL")["symbol"].tolist()
    )
    uni = _db.read_df(
        f"SELECT instrument_id, symbol FROM {M}.instrument_master "
        "WHERE asset_class='stock' AND symbol IS NOT NULL ORDER BY symbol"
    )
    todo = [r for _, r in uni.iterrows() if r["symbol"] not in done]
    if limit:
        todo = todo[:limit]
    print(
        f"{len(done)} already done; fetching {len(todo)} (of {len(uni)}) on {workers} workers",
        flush=True,
    )
    batch, ok, miss, n = [], 0, 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(_fetch_one, todo):
            n += 1
            if res:
                batch.append(res)
                ok += 1
            else:
                miss += 1
            if len(batch) >= 100:
                _db.upsert_df(TGT, pd.DataFrame(batch), ["instrument_id"])
                batch = []
                print(f"  {n}/{len(todo)} ok={ok} miss={miss}", flush=True)
    if batch:
        _db.upsert_df(TGT, pd.DataFrame(batch), ["instrument_id"])
    print(
        f"DONE: ok={ok} miss={miss}; total in table="
        f"{_db.scalar(f'SELECT count(*) FROM {TGT} WHERE market_cap_cr IS NOT NULL')}",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    run(args.limit, args.workers)


if __name__ == "__main__":
    main()
