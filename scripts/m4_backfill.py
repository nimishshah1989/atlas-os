#!/usr/bin/env python3
"""M4 historical backfill — fund three-lens compute.

Deploy to jsl-wealth-server and run:
    export ATLAS_DB_URL="postgresql+psycopg2://..."
    python3 m4_backfill.py [--start 2014-04-01] [--end 2026-05-08]
                           [--phase {all,lens1,lens2,lens3,states}]

Phases (default: all):
    lens1   — NAV metrics + nav_state for all funds × all trading days
    lens2   — Sector composition metrics for all historical disclosures
    lens3   — Holdings quality metrics for all historical disclosures
    states  — Three-tuple state assembly (requires lens1+lens2+lens3 done)
    all     — Run all four phases in order

Expected row counts:
    atlas_fund_metrics_daily  ~1.2M  (400 funds × 3,000 days)
    atlas_fund_lens_monthly   ~58K   (400 funds × 144 months)
    atlas_fund_states_daily   ~1.2M  (400 funds × 3,000 days)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from atlas.compute.funds import run_m4_backfill  # noqa: E402
from atlas.compute.lens_composition import run_lens2  # noqa: E402
from atlas.compute.lens_holdings import run_lens3  # noqa: E402
from atlas.compute.lens_nav import run_lens1  # noqa: E402
from atlas.db import get_engine, load_thresholds  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    p = argparse.ArgumentParser(description="M4 historical backfill")
    p.add_argument("--start", type=_parse_date, default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--end", type=_parse_date, default=None, help="End date YYYY-MM-DD")
    p.add_argument(
        "--phase",
        choices=["all", "lens1", "lens2", "lens3", "states"],
        default="all",
        help="Which phase to run (default: all)",
    )
    args = p.parse_args()

    engine = get_engine()
    thresholds = load_thresholds(engine)

    print(
        f"M4 backfill starting | phase={args.phase} | "
        f"start={args.start or 'default'} | end={args.end or 'today'}"
    )

    if args.phase == "all":
        result = run_m4_backfill(
            start_date=args.start,
            end_date=args.end,
            engine=engine,
        )
        print(f"Lens 1 rows: {result['lens1_rows']:,}")
        print(f"Lens 2 rows: {result['lens2_rows']:,}")
        print(f"Lens 3 rows: {result['lens3_rows']:,}")
        print(f"State rows:  {result['state_rows']:,}")
        print(f"Run ID: {result['run_id']}")

    elif args.phase == "lens1":
        start = args.start or _parse_date("2014-04-01")
        end = args.end or date.today()
        result = run_lens1(
            start_date=start,
            end_date=end,
            engine=engine,
            thresholds=thresholds,
        )
        print(f"Lens 1 rows written: {result['rows_written']:,}")
        print(f"Funds processed: {result['funds_processed']}")
        if result["errors"]:
            print(f"Errors: {len(result['errors'])}")
            for e in result["errors"][:5]:
                print(f"  {e}")

    elif args.phase == "lens2":
        result = run_lens2(
            start_date=args.start,
            end_date=args.end,
            engine=engine,
            thresholds=thresholds,
        )
        print(f"Lens 2 rows written: {result['rows_written']:,}")
        print(f"Disclosure dates processed: {result['disclosures_processed']}")

    elif args.phase == "lens3":
        result = run_lens3(
            start_date=args.start,
            end_date=args.end,
            engine=engine,
            thresholds=thresholds,
        )
        print(f"Lens 3 rows written: {result['rows_written']:,}")
        print(f"Disclosure dates processed: {result['disclosures_processed']}")

    elif args.phase == "states":
        import uuid

        from atlas.compute._session import bulk_upsert, df_to_pg_rows
        from atlas.compute.funds import (
            STATES_COLUMNS,
            apply_dislocation_override,
            assemble_fund_states,
        )

        start = args.start or _parse_date("2014-04-01")
        end = args.end or date.today()
        run_id = uuid.uuid4()
        df = assemble_fund_states(engine, start, end)
        if df.empty:
            print("No fund states assembled.")
            sys.exit(1)
        df = apply_dislocation_override(df, engine, start, end)
        df["compute_run_id"] = str(run_id)
        write_cols = [c for c in STATES_COLUMNS if c in df.columns]
        rows = df_to_pg_rows(df[write_cols])
        n = bulk_upsert(
            engine,
            "atlas.atlas_fund_states_daily",
            list(write_cols),
            rows,
            pk_columns=["mstar_id", "date"],
        )
        print(f"State rows written: {n:,}")

    print("Done.")


if __name__ == "__main__":
    main()
