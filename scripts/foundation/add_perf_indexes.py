#!/usr/bin/env python3
"""Speed fix: add the missing date indexes that force every v4 decile/liquidity query into a
full seq-scan of multi-million-row tables (the 30-50s page loads).

Root cause (EXPLAIN-confirmed 2026-06-24): atlas_lens_scores_daily PK is (instrument_id, date),
so `max(date)` / `WHERE date = <latest>` scans all 3.9M rows (~10s each; the ETF detail pays it
twice → ~50s). ohlcv_stock has no date index, so the stocks-list 30-day turnover scan is a full
1.6 GB scan.

Both indexes are ADDITIVE (no data change) and built CONCURRENTLY (reads + writes continue), on
atlas_foundation tables (v4's own). IF NOT EXISTS = idempotent.
"""

from __future__ import annotations

import time

import _db
import psycopg2

INDEXES = [
    ("ix_fs_lens_class_date", "atlas_foundation.atlas_lens_scores_daily", "(asset_class, date)"),
    ("ix_fs_ohlcv_stock_date", "atlas_foundation.ohlcv_stock", "(date)"),
]


def main() -> None:
    # Direct psycopg2 autocommit connection — CREATE INDEX CONCURRENTLY can't run in a txn block.
    conn = psycopg2.connect(_db.db_url().replace("postgresql+psycopg2://", "postgresql://"))
    conn.autocommit = True
    try:
        cur = conn.cursor()
        for name, tbl, cols in INDEXES:
            t0 = time.time()
            print(f"creating {name} on {tbl} {cols} …", flush=True)
            cur.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {tbl} {cols}")
            print(f"  done in {time.time() - t0:.0f}s", flush=True)
        cur.close()
    finally:
        conn.close()
    print("indexes ready.")


if __name__ == "__main__":
    main()
