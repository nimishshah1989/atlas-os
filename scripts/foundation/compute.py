#!/usr/bin/env python3
"""Compute TA-Lib technicals from staging OHLCV → foundation_staging.technical_stock.

Reads adjusted closes from foundation_staging.ohlcv_stock and the N50/N500
benchmarks from foundation_staging.index_prices, computes the metrics axis target
(EMA 21/50/200, RSI14, returns, RS × 6 windows × 2 benchmarks, above-EMA flags)
via the canonical technicals module, and idempotently upserts the result.

This is the per-instrument compute grind the autonomous loop will run; it is
pure Python + TA-Lib and emits only small counts.
"""

from __future__ import annotations

import argparse
import uuid

import pandas as pd

import _db
import technicals as T
from harness import BENCHMARKS, STAGING_SCHEMA

_TECH_COLS = (
    ["ema_21", "ema_50", "ema_200", "rsi_14"]
    + [f"ret_{w}" for w in T.RETURN_WINDOWS]
    + [f"rs_{w}_{b}" for b in BENCHMARKS for w in T.RETURN_WINDOWS]
    + ["above_ema_21", "above_ema_50", "above_ema_200"]
)


def load_benchmarks() -> dict[str, pd.Series]:
    out = {}
    for suf, code in BENCHMARKS.items():
        df = _db.read_df(
            f"select date, close from {STAGING_SCHEMA}.index_prices "
            "where index_code = :c order by date", {"c": code})
        out[suf] = pd.Series(df["close"].astype(float).values,
                             index=pd.DatetimeIndex(pd.to_datetime(df["date"])))
    return out


def _instrument_ids(symbols: list[str] | None) -> list[tuple[str, str]]:
    where = "" if not symbols else "where symbol = any(:syms)"
    df = _db.read_df(
        f"select distinct instrument_id, symbol from {STAGING_SCHEMA}.ohlcv_stock {where}",
        {"syms": symbols} if symbols else None)
    return [(str(r.instrument_id), r.symbol) for r in df.itertuples()]


def compute_instrument(iid: str, benches: dict, run_id: str) -> int:
    px = _db.read_df(
        f"select date, close_adj from {STAGING_SCHEMA}.ohlcv_stock "
        "where instrument_id = cast(:i as uuid) order by date", {"i": iid})
    if len(px) < 2:
        return 0
    close = pd.Series(px["close_adj"].astype(float).values,
                      index=pd.DatetimeIndex(pd.to_datetime(px["date"])))
    tech = T.compute_price_technicals(close)
    for suf in BENCHMARKS:
        tech = tech.join(T.compute_relative_strength(close, benches[suf], suf))
    flags = T.above_ema_flags(close, tech)

    out = pd.DataFrame(index=close.index)
    out["instrument_id"] = iid
    out["date"] = [d.date() for d in close.index]
    for c in ["ema_21", "ema_50", "ema_200", "rsi_14"] + [f"ret_{w}" for w in T.RETURN_WINDOWS]:
        out[c] = tech[c].values
    for b in BENCHMARKS:
        for w in T.RETURN_WINDOWS:
            out[f"rs_{w}_{b}"] = tech[f"rs_{w}_{b}"].values
    for p in T.EMA_PERIODS:
        out[f"above_ema_{p}"] = flags[f"above_ema_{p}"].values
    out["compute_run_id"] = run_id
    # Clamp infinities and out-of-range values to None for DB (numeric(16,8))
    import numpy as np
    for c in _TECH_COLS:
        if c in out.columns:
            s = pd.to_numeric(out[c], errors="coerce")
            s = s.where(np.isfinite(s), other=np.nan)
            out[c] = s
    cols = ["instrument_id", "date"] + _TECH_COLS + ["compute_run_id"]
    out = out[cols].astype(object).where(pd.notna(out), None)
    return _db.upsert_df(f"{STAGING_SCHEMA}.technical_stock", out, ["instrument_id", "date"])


def compute_stocks(symbols: list[str] | None = None) -> dict:
    run_id = str(uuid.uuid4())
    benches = load_benchmarks()
    targets = _instrument_ids(symbols)
    n_rows = 0
    for iid, _sym in targets:
        n_rows += compute_instrument(iid, benches, run_id)
    return {"run_id": run_id, "instruments": len(targets), "rows_written": n_rows}


def main():
    ap = argparse.ArgumentParser(description="Compute TA-Lib technicals → staging")
    ap.add_argument("--symbols", nargs="*", help="restrict to these symbols")
    args = ap.parse_args()
    print(compute_stocks(args.symbols))


if __name__ == "__main__":
    main()
