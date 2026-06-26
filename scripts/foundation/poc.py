#!/usr/bin/env python3
"""Thin PoC: prove the clean pipeline end-to-end on ~10 symbols → harness green.

Pipeline shape (docs/atlas-data-foundation.md §3, §7.3):
    NSE Bhavcopy (real download) ─┐
                                  ├─► staging RAW+ADJ OHLCV ─► TA-Lib technicals ─► harness
    deep history (seed) ──────────┘

To stay THIN we do NOT re-download 10y of Bhavcopy (that is the loop's token-free
grind). Instead:
  1. Seed deep adjusted history (2016→T-1) for the PoC symbols + N50/N500 indices
     from the existing de_* tables (themselves Bhavcopy-derived).
  2. ACTUALLY download + parse + ingest the latest real Bhavcopy day from NSE,
     writing genuinely Bhavcopy-sourced rows for that day.
  3. Reconcile the freshly-ingested day against de_* (parse correctness).
  4. Compute TA-Lib technicals over the full series.
  5. Run the harness on the staging profile → green.

PoC symbols are chosen as already-clean, full-depth Nifty-50 names so that GREEN
reflects pipeline correctness — NOT a claim that all live data is clean (the
baseline showed 0/500). Corp-action back-adjustment for dirty names is the loop's
job (the harness jump-check gates it).
"""

from __future__ import annotations

from datetime import date

import _db
import compute
import ingest_bhavcopy as ing
import pandas as pd
from harness import STAGING_SCHEMA

POC_SYMBOLS = [
    "HCLTECH",
    "SUNPHARMA",
    "BHARTIARTL",
    "INDIGO",
    "POWERGRID",
    "CIPLA",
    "HINDUNILVR",
    "ASIANPAINT",
    "COALINDIA",
    "TECHM",
]
SEED_START = "2016-04-07"
SEED_END = "2026-06-17"  # T-1; the latest day comes from real Bhavcopy
LATEST_DAY = date(2026, 6, 18)  # most recent NSE trading day with Bhavcopy
BENCH_CODES = ["NIFTY 50", "NIFTY 500"]


def step(msg: str):
    print(f"\033[36m▶ {msg}\033[0m")


def seed_indices() -> int:
    step(f"seed index history {SEED_START}..{SEED_END} (N50/N500) from de_index_prices")
    df = _db.read_df(
        "select index_code, date, open, high, low, close, volume "
        "from public.de_index_prices "
        "where index_code = any(:codes) and date between :a and :b",
        {"codes": BENCH_CODES, "a": SEED_START, "b": SEED_END},
    )
    df["source"] = "seed:de_index_prices"
    n = _db.upsert_df(f"{STAGING_SCHEMA}.index_prices", df, ["index_code", "date"])
    print(f"  indices seeded: {n} rows")
    return n


def _poc_instrument_ids() -> dict[str, str]:
    df = _db.read_df(
        "select id, symbol from public.de_instrument where symbol = any(:syms)",
        {"syms": POC_SYMBOLS},
    )
    return {r.symbol: str(r.id) for r in df.itertuples()}


def seed_stocks() -> int:
    step(f"seed stock history {SEED_START}..{SEED_END} for {len(POC_SYMBOLS)} symbols")
    ids = list(_poc_instrument_ids().values())
    # Pull by instrument_id (uuid array) — the symbol-join plan scans the whole
    # year-partitioned table and trips the 2-min pooler timeout.
    df = _db.read_df(
        "select o.instrument_id, o.symbol, o.date, o.open, o.high, o.low, o.close, "
        "       o.open_adj, o.high_adj, o.low_adj, o.close_adj, o.volume, o.trades "
        "from public.de_equity_ohlcv o "
        "where o.instrument_id = any(cast(:ids as uuid[])) and o.date between :a and :b",
        {"ids": ids, "a": SEED_START, "b": SEED_END},
    )
    df["instrument_id"] = df["instrument_id"].astype(str)
    close = pd.to_numeric(df["close"], errors="coerce")
    cadj = pd.to_numeric(df["close_adj"], errors="coerce")
    df["adj_factor"] = (cadj / close).where(close > 0, 1.0)
    df["series"] = "EQ"
    df["source"] = "seed:de_equity_ohlcv"
    n = _db.upsert_df(f"{STAGING_SCHEMA}.ohlcv_stock", df, ["instrument_id", "date"])
    print(f"  stocks seeded: {n} rows across {df['symbol'].nunique()} symbols")
    return n


def ingest_real_day() -> dict:
    step(f"download + ingest REAL NSE Bhavcopy for {LATEST_DAY} (the one-day PoC ingest)")
    res = ing.ingest_day(LATEST_DAY, only_symbols=POC_SYMBOLS)
    print(f"  {res}")
    return res


def reconcile_latest() -> dict:
    step(f"reconcile ingested {LATEST_DAY} close vs de_* (parse correctness)")
    stg = _db.read_df(
        f"select symbol, close from {STAGING_SCHEMA}.ohlcv_stock "
        "where date = :d and symbol = any(:syms)",
        {"d": LATEST_DAY, "syms": POC_SYMBOLS},
    )
    de = _db.read_df(
        "select i.symbol, o.close from public.de_equity_ohlcv o "
        "join public.de_instrument i on i.id=o.instrument_id "
        "where o.date = :d and i.symbol = any(:syms)",
        {"d": LATEST_DAY, "syms": POC_SYMBOLS},
    )
    m = stg.merge(de, on="symbol", suffixes=("_bhav", "_de"))
    m["abs_diff"] = (m["close_bhav"].astype(float) - m["close_de"].astype(float)).abs()
    worst = float(m["abs_diff"].max()) if len(m) else None
    print(f"  matched {len(m)} symbols; max |bhavcopy − de_*| close diff = {worst}")
    for r in m.sort_values("abs_diff", ascending=False).head(3).itertuples():
        print(f"    {r.symbol:<12} bhav={r.close_bhav}  de={r.close_de}  Δ={r.abs_diff}")
    return {"matched": len(m), "max_abs_diff": worst}


def run_compute() -> dict:
    step("compute TA-Lib technicals (EMA 21/50/200, RSI14, returns, RS ×6×2) → staging")
    res = compute.compute_stocks(POC_SYMBOLS)
    print(f"  {res}")
    return res


def main():
    print("=" * 64)
    print(" ATLAS DATA FOUNDATION — THIN PoC")
    print("=" * 64)
    seed_indices()
    seed_stocks()
    ingest_real_day()
    reconcile_latest()
    run_compute()
    step("run harness on staging profile (the definition of done)")
    print()
    from harness import run as harness_run

    harness_run("staging", symbols=POC_SYMBOLS, limit=None, metrics_sample=None)


if __name__ == "__main__":
    main()
