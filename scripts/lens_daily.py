#!/usr/bin/env python3
"""Atlas daily six-lens scoring — the step that was MISSING from the nightly.

Root cause of the lens-journal staleness (atlas_lens_scores_daily lagged the MVs):
run_pipeline() only ran via the manual historical backfill, never in cron. This thin
daily wrapper scores the latest NSE session so the journal advances every night.
Idempotent: run_pipeline upserts the date then purges that date's stale rows.

    python scripts/lens_daily.py                 # latest session
    python scripts/lens_daily.py --as-of 2026-06-24
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from atlas.lenses.pipeline import run_pipeline


def main() -> int:
    ap = argparse.ArgumentParser(description="Atlas daily six-lens scoring")
    ap.add_argument("--as-of", type=lambda s: date.fromisoformat(s), default=None,
                    help="NSE session to score (YYYY-MM-DD). Default: latest real session.")
    args = ap.parse_args()
    result = run_pipeline(as_of=args.as_of)
    print(f"lens_daily complete: {result}")
    # run_pipeline logs zero-scored without purging; treat 0 scored as a failure so cron alerts.
    scored = result.get("scored") if isinstance(result, dict) else None
    return 0 if (scored is None or scored > 0) else 1


if __name__ == "__main__":
    sys.exit(main())
