#!/usr/bin/env python3
"""Freshness guard — fail LOUD if any KEY production table hasn't reached the EOD.

The 26-June staleness went unnoticed because nothing asserted freshness. This gate
runs at the end of the daily orchestrator (and inside the Sunday QA): every table the
board renders must have data at the last complete EOD. Exit 1 (+ a one-line reason per
stale table) if not, so the orchestrator alerts. Reads the single schema only.

    python scripts/ops/freshness_guard.py --eod 2026-07-01
    python scripts/ops/freshness_guard.py            # defaults to _db.eod_cutoff()
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "foundation"))
import _db  # noqa: E402

M = "foundation_staging"

# (table, date_col, max_lag_trading_days) — most must be exactly at the EOD; a few
# feeds legitimately lag (delivery T+1, holdings weekly) so carry a tolerance.
KEY_TABLES = [
    ("ohlcv_stock", "date", 0),
    ("ohlcv_etf", "date", 0),
    ("index_prices", "date", 0),
    ("technical_daily", "date", 0),
    ("atlas_lens_scores_daily", "date", 0),
    ("sector_lens_daily", "date", 0),
    ("fund_rank_daily", "date", 0),
    ("atlas_index_metrics_daily", "date", 0),
    ("atlas_market_regime_daily", "date", 0),
    ("breadth_nifty500_daily", "date", 2),
    ("de_mf_nav_daily", "nav_date", 1),
    ("delivery_daily", "date", 2),
]


def check(eod: dt.date) -> list[str]:
    stale = []
    for table, col, lag in KEY_TABLES:
        mx = _db.scalar(f"select max({col}) from {M}.{table}")
        if mx is None:
            stale.append(f"{table}: EMPTY")
            continue
        behind = (eod - mx).days
        status = "OK" if behind <= lag else "STALE"
        print(f"  [{status}] {table:<28} max={mx} (eod={eod}, behind={behind}d, tol={lag})")
        if behind > lag:
            stale.append(f"{table} stale: max={mx}, {behind}d behind EOD {eod}")
    return stale


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert all KEY tables are fresh to the EOD")
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    args = ap.parse_args()
    eod = args.eod or _db.eod_cutoff()
    print(f"[freshness_guard] EOD={eod}")
    stale = check(eod)
    if stale:
        print(f"[freshness_guard] FAIL — {len(stale)} stale table(s):")
        for s in stale:
            print(f"    - {s}")
        return 1
    print("[freshness_guard] PASS — all KEY tables fresh to EOD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
