#!/usr/bin/env python3
"""Compute + UPSERT atlas_etf_scorecard for an EXPLICIT snapshot_date.

scripts/etf_scorecard_expand.py only targets MAX(snapshot_date) already in the
table, so it cannot advance the scorecard to a fresh trading day. This thin
runner calls the same library entrypoint (atlas.inference.etf_scorecard) for a
date passed on the command line, then executes the ON CONFLICT UPSERT directly
against ATLAS_DB_URL.

Idempotent: the underlying emit_upsert_sql() uses
``ON CONFLICT (snapshot_date, instrument_id) DO UPDATE``.

NOTE (known limitation, out of scope for the data-layer chunk): the scorecard's
conviction input reads the legacy atlas_conviction_daily table; if that table is
stale, matrix_conviction_score degrades to its neutral default — identical
behaviour to the prior snapshot, so this run is consistent with history.

Usage (on EC2, repo root, venv active):
    python scripts/ops/run_etf_scorecard_for_date.py --date 2026-05-29
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=_parse_date, required=True, help="snapshot_date YYYY-MM-DD")
    args = p.parse_args()

    load_dotenv(".env")
    eng = create_engine(os.environ["ATLAS_DB_URL"])

    from atlas.inference.etf_scorecard import compute_etf_scorecard, emit_upsert_sql

    rows = compute_etf_scorecard(args.date, engine=eng)
    print(f"[run_etf_scorecard_for_date] {args.date}: computed {len(rows)} rows")
    if not rows:
        print("  no rows computed — aborting (check de_etf_ohlcv freshness for this date)")
        return 1

    sql = emit_upsert_sql(rows)
    if sql.strip().startswith("--"):
        print("  emit_upsert_sql produced no INSERT — aborting")
        return 1

    with eng.begin() as conn:
        conn.execute(text(sql))

    with eng.connect() as conn:
        mx = conn.execute(
            text(
                "SELECT MAX(snapshot_date)::text, COUNT(*) FROM atlas.atlas_etf_scorecard "
                "WHERE snapshot_date = :d"
            ),
            {"d": args.date},
        ).one()
    print(f"  AFTER: atlas_etf_scorecard rows@{args.date}={mx[1]} (max snapshot_date={mx[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
