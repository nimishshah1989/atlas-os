#!/usr/bin/env python3
"""Backfill rs_{1w,1m,3m}_nifty500 in atlas_stock_metrics_daily for a date.

WHY THIS EXISTS
---------------
The nifty500 relative-strength columns (rs_1w/1m/3m_nifty500) on
atlas_stock_metrics_daily are read by mv_stock_landscape (its date anchor is
``MAX(date) WHERE rs_3m_nifty500 IS NOT NULL``) and by mv_stock_list_v6.
They are NOT written by any daily writer — m2/run_stock_daily only persists
the cap-tier RS columns (rs_*_tier), and the nifty500 columns were populated
only by a historical backfill. So on every fresh trading day they come up
NULL, which freezes mv_stock_landscape at the last backfilled date.

This script reproduces the canonical relative-strength definition
(excess return vs the NIFTY 500 benchmark — see atlas.compute.benchmarks
``add_relative_strength``):

    rs_X_nifty500 = ret_X(stock) - ret_X(NIFTY 500)

verified to exact (0.000000) residual against the production values on
2026-05-27 for 743/747 stocks. The 4 exceptions (CUPID, METROPOLIS, ECLERX,
IRB) carried stale pre-corporate-action ret_3m in the historical backfill;
using current adjusted returns here is the *correct* RS per the financial
-domain rule "corporate actions change historical prices."

Idempotent: only fills rows where rs_3m_nifty500 IS NULL (re-running is a
no-op). Logs row counts before and after per data-engineering conventions.

Until this is wired into the nightly pipeline (Chunk C), run it after M2/M3
for the latest trading date, before refreshing the v6 MVs.

Usage (on EC2, repo root, venv active):
    python scripts/ops/backfill_stock_rs_nifty500.py --date 2026-05-29
    python scripts/ops/backfill_stock_rs_nifty500.py            # latest metrics date
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BENCHMARK_INDEX = "NIFTY 500"


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        help="Target date YYYY-MM-DD (default: latest atlas_stock_metrics_daily date)",
    )
    p.add_argument("--dry-run", action="store_true", help="Compute coverage but do not write")
    args = p.parse_args()

    load_dotenv(".env")
    eng = create_engine(os.environ["ATLAS_DB_URL"])

    with eng.connect() as c:
        target = (
            args.date
            or c.execute(text("SELECT MAX(date) FROM atlas.atlas_stock_metrics_daily")).scalar()
        )

        bench = c.execute(
            text(
                "SELECT ret_1w, ret_1m, ret_3m FROM atlas.atlas_index_metrics_daily "
                "WHERE index_code = :ix AND date = :d"
            ),
            {"ix": BENCHMARK_INDEX, "d": target},
        ).first()
        if bench is None:
            print(f"ABORT: no '{BENCHMARK_INDEX}' index metrics for {target} — cannot compute RS.")
            return 1

        before = c.execute(
            text(
                "SELECT COUNT(*) total, COUNT(rs_3m_nifty500) have_rs "
                "FROM atlas.atlas_stock_metrics_daily WHERE date = :d"
            ),
            {"d": target},
        ).one()

    print(
        f"[backfill_stock_rs_nifty500] date={target}  benchmark={BENCHMARK_INDEX} "
        f"ret_1w={bench[0]} ret_1m={bench[1]} ret_3m={bench[2]}"
    )
    print(f"  BEFORE: {before[0]} rows, {before[1]} with rs_3m_nifty500")

    if args.dry_run:
        print("  (dry-run — no write)")
        return 0

    update_sql = text("""
        UPDATE atlas.atlas_stock_metrics_daily m
        SET rs_1w_nifty500 = m.ret_1w - :b1w,
            rs_1m_nifty500 = m.ret_1m - :b1m,
            rs_3m_nifty500 = m.ret_3m - :b3m
        WHERE m.date = :d
          AND m.rs_3m_nifty500 IS NULL
          AND m.ret_3m IS NOT NULL
    """)
    with eng.begin() as c:
        res = c.execute(
            update_sql, {"b1w": bench[0], "b1m": bench[1], "b3m": bench[2], "d": target}
        )
        updated = res.rowcount

    with eng.connect() as c:
        after = c.execute(
            text(
                "SELECT COUNT(*) total, COUNT(rs_3m_nifty500) have_rs "
                "FROM atlas.atlas_stock_metrics_daily WHERE date = :d"
            ),
            {"d": target},
        ).one()

    print(f"  UPDATED: {updated} rows")
    print(f"  AFTER:  {after[0]} rows, {after[1]} with rs_3m_nifty500")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
