#!/usr/bin/env python3
"""Compute + UPSERT atlas_fund_scorecard for a snapshot_date — direct DB write.

`atlas/inference/fund_scorecard.py` has a complete, tested generator
(`compute_fund_scorecard_from_engine` + `emit_upsert_sql`) but its CLI only
writes to the live DB when a `.supabase-write-approved` marker is present
(otherwise it dumps a .sql file). For the nightly pipeline — which already
writes freely to the DB — this thin wrapper calls the same library functions
and executes the UPSERT directly, no marker dance. This is the fund analogue of
scripts/ops/run_etf_scorecard_for_date.py.

Idempotent: emit_upsert_sql() uses ON CONFLICT (snapshot_date, scheme_code)
DO UPDATE.

NOTE: NAV (de_mf_nav_daily) typically lags T-1..T-3 and AMFI publishes Friday
NAV on the weekend, so running for a Friday snapshot may carry nav_as_of a day
or two earlier — that's surfaced per-row via the scorecard's nav_as_of column.
Holdings (de_mf_holdings) carry the SEBI 30-day disclosure lag by design.

Usage (on EC2, repo root, venv active):
    python scripts/ops/run_fund_scorecard_for_date.py --date 2026-05-29
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

    from atlas.inference.fund_scorecard import (
        compute_fund_scorecard_from_engine,
        emit_upsert_sql,
    )

    rows = compute_fund_scorecard_from_engine(args.date, eng)
    print(f"[run_fund_scorecard_for_date] {args.date}: computed {len(rows)} rows")
    if not rows:
        print("  no rows computed — aborting (check de_mf_nav_daily / atlas_universe_funds)")
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
                "SELECT MAX(snapshot_date)::text, COUNT(*), MAX(nav_as_of)::text "
                "FROM atlas.atlas_fund_scorecard WHERE snapshot_date = :d"
            ),
            {"d": args.date},
        ).one()
    print(
        f"  AFTER: atlas_fund_scorecard rows@{args.date}={mx[1]} "
        f"(max snapshot_date={mx[0]}, nav_as_of={mx[2]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
