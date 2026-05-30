#!/usr/bin/env python3
"""Backfill {stock,etf}_signal_calls.predicted_excess from the cell's
friction_adjusted_excess (audit item A1).

The decisions writer historically never wrote predicted_excess, so every call on
the live "Expected" column rendered an em-dash. The writer is now fixed
(atlas/decisions/cron.py) for NEW calls; this one-time, idempotent backfill
populates the EXISTING open calls (which the frontend already displays) by
joining each call to its cell definition.

predicted_excess = atlas_cell_definitions.friction_adjusted_excess — the cell's
validated friction-adjusted expected excess return (a cell-level prior, same
nature as confidence_unconditional). Idempotent: only fills rows where
predicted_excess IS NULL.

Usage (EC2, repo root, venv active):
    python scripts/ops/backfill_signal_call_predicted_excess.py
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
eng = create_engine(os.environ["ATLAS_DB_URL"])

# Plain string literals (no interpolation) — stocks + ETFs share the same shape.
_UPDATE = (
    " sc SET predicted_excess = cd.friction_adjusted_excess "
    "FROM atlas.atlas_cell_definitions cd WHERE sc.cell_id = cd.cell_id "
    "AND sc.predicted_excess IS NULL AND cd.friction_adjusted_excess IS NOT NULL"
)
JOBS = [
    (
        "atlas.atlas_signal_calls",
        "SELECT COUNT(*), COUNT(predicted_excess) FROM atlas.atlas_signal_calls",
        "UPDATE atlas.atlas_signal_calls" + _UPDATE,
    ),
    (
        "atlas.atlas_etf_signal_calls",
        "SELECT COUNT(*), COUNT(predicted_excess) FROM atlas.atlas_etf_signal_calls",
        "UPDATE atlas.atlas_etf_signal_calls" + _UPDATE,
    ),
]


def main() -> int:
    for label, count_sql, update_sql in JOBS:
        with eng.connect() as c:
            try:
                before = c.execute(text(count_sql)).one()
            except Exception as ex:
                print(f"  SKIP {label}: {str(ex)[:120]}")
                continue
        with eng.begin() as c:
            updated = c.execute(text(update_sql)).rowcount
        with eng.connect() as c:
            after = c.execute(text(count_sql)).one()
        print(
            f"{label}: before {before[1]}/{before[0]} had excess; "
            f"updated {updated}; after {after[1]}/{after[0]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
