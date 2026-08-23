#!/usr/bin/env python3
"""Ingest Screener market cap + face value per stock -> atlas_foundation.equity_marketcap.

The weighting source for roll-ups (D24/D21a follow-up): every in-DB candidate failed
(de_index_constituents weights NULL, tv_metrics.market_cap inconsistent, shares_outstanding
empty). Screener's Market Cap is reliable (RELIANCE ₹17.9L Cr, TCS ₹7.7L Cr — verified) and
we already have the warm-session fetcher. Shares = market_cap / our OHLCV close; free-float
cap = shares × price × (1 − promoter%). Rate-limited, and resumable within a run —
but a cap already fetched is re-scraped once it passes REFRESH_DAYS (see run()).

    python fetch_marketcap.py            # all stocks
    python fetch_marketcap.py --limit 50 # smoke test
"""

from __future__ import annotations

import argparse
import re
import threading
import time
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


M = "atlas_foundation"
TGT = f"{M}.equity_marketcap"

# Re-scrape a cap older than this. Data-hygiene cadence, not methodology: caps drift
# continuously, and ~80-280 re-scrapes a week at ~1 req/s costs a few minutes.
REFRESH_DAYS = 30


def ensure_table() -> None:
    _db.exec_sql(f"""CREATE TABLE IF NOT EXISTS {TGT} (
        instrument_id uuid PRIMARY KEY, symbol text, market_cap_cr numeric,
        face_value numeric, fetched_at timestamptz)""")


def _topval(html: str, label: str) -> float | None:
    m = re.search(
        re.escape(label) + r'\s*</span>.*?<span class="number">\s*([0-9,]+\.?[0-9]*)', html, re.S
    )
    return float(m.group(1).replace(",", "")) if m else None


_gate = threading.Lock()
_next_at = 0.0


def _throttle(gap: float = 1.0) -> None:
    """One request per `gap` seconds across every worker. Screener 429s on bursts
    (4 workers tripped it within 5 requests); sequential-at-1/s stays 200."""
    global _next_at
    with _gate:
        wait = _next_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _next_at = time.monotonic() + gap


def _fetch(url: str) -> requests.Response | None:
    """Retry through 429s. Without this a throttled name is indistinguishable from
    a name Screener does not carry, and gets silently recorded as a miss."""
    s = _session()
    for backoff in (0, 20, 60, 120):
        if backoff:
            time.sleep(backoff)
        _throttle()
        try:
            r = s.get(url, timeout=25)
        except requests.RequestException as e:
            print(f"  {url}: {e}", flush=True)
            continue
        if r.status_code != 429:
            return r
    print(f"  {url}: still 429 after 4 tries", flush=True)
    return None


def _get(sym: str) -> str | None:
    """Consolidated first, standalone fallback. A company with no consolidated
    financials still serves 200 with the ratio block rendered but empty
    (`<span class="number"></span>`), so the guard has to be a successful parse —
    a `"Market Cap" in text` guard accepts that stub and never falls back."""
    for path in (f"company/{sym}/consolidated/", f"company/{sym}/"):
        r = _fetch(f"https://www.screener.in/{path}")
        if r is not None and r.status_code == 200 and _topval(r.text, "Market Cap"):
            return r.text
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


def fill_renamed_symbols() -> list[str]:
    """Carry a fetched cap across an NSE symbol rename, matching on ISIN.

    A rename leaves instrument_master holding both tickers for one security (same ISIN):
    the old one carries the whole OHLCV history — so it is the row the pipeline actually
    scores — while Screener only serves the new one, and `company/<old>/` 404s. The old
    row is then silently capless, which would drop it into the micro cohort.
    (GUJGASLTD/GUJENERGY, ISIN INE844O01030: 5,617 bars on the old ticker, 0 on the new.)

    Market cap is an attribute of the security, so the ISIN join is identity, not
    inference. Fills only rows that have no cap — never overwrites a fetched value.
    """
    filled = _db.read_df(f"""
        INSERT INTO {TGT} (instrument_id, symbol, market_cap_cr, face_value, fetched_at)
        SELECT DISTINCT ON (gap.instrument_id)
               gap.instrument_id, gap.symbol, src.market_cap_cr, src.face_value,
               src.fetched_at
        FROM {M}.instrument_master gap
        JOIN {M}.instrument_master twin
          ON twin.isin = gap.isin AND twin.instrument_id <> gap.instrument_id
        JOIN {TGT} src
          ON src.instrument_id = twin.instrument_id AND src.market_cap_cr IS NOT NULL
        LEFT JOIN {TGT} own ON own.instrument_id = gap.instrument_id
        WHERE gap.asset_class = 'stock' AND gap.isin IS NOT NULL
          AND own.market_cap_cr IS NULL
        ORDER BY gap.instrument_id, src.fetched_at DESC NULLS LAST
        ON CONFLICT (instrument_id) DO UPDATE
          SET market_cap_cr = EXCLUDED.market_cap_cr,
              face_value    = EXCLUDED.face_value,
              fetched_at    = EXCLUDED.fetched_at
          WHERE {TGT}.market_cap_cr IS NULL
        RETURNING symbol""")["symbol"].tolist()
    print(f"renamed-symbol fill: {len(filled)} {sorted(filled)}", flush=True)
    return filled


def run(limit: int | None, workers: int = 6) -> None:
    ensure_table()
    # Skip only caps fetched RECENTLY. Resume-only (skip anything non-null) froze every
    # cap at whatever it was on first fetch: 280 rows were already >30 days old, 146 of
    # them prospective universe members. That was survivable while market cap was one
    # weighting input among many; it is not now that cap RANK decides which cohort a
    # stock's deciles and Leader badge are computed inside. A NULL fetched_at re-fetches
    # (NULL > x is NULL, so the row never counts as done).
    done = set(
        _db.read_df(
            f"SELECT symbol FROM {TGT} WHERE market_cap_cr IS NOT NULL "
            f"AND fetched_at > now() - interval '{REFRESH_DAYS} days'"
        )["symbol"].tolist()
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
    fill_renamed_symbols()
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
