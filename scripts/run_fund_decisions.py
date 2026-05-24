#!/usr/bin/env python3
"""Run the MF holdings decisions compute pipeline.

Usage:
    python scripts/run_fund_decisions.py
    python scripts/run_fund_decisions.py --mstar-id F00000WXYZ
    python scripts/run_fund_decisions.py --mstar-id F00000WXYZ --mstar-id F00001ABCD

Args:
    --mstar-id  Run for one or more specific funds. Omit to run for all funds.
"""

from __future__ import annotations

import argparse
import sys

import structlog

from atlas.compute.lens_decisions import run_lens_decisions
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MF holdings decisions compute pipeline")
    parser.add_argument(
        "--mstar-id",
        dest="mstar_ids",
        action="append",
        metavar="MSTAR_ID",
        help="Run for a specific fund (can be repeated). Omit for all funds.",
    )
    args = parser.parse_args()

    engine = get_engine()
    thresholds = load_thresholds("atlas", engine)

    log.info("run_fund_decisions_start", target_funds=args.mstar_ids)

    result = run_lens_decisions(
        engine=engine,
        thresholds=thresholds,
        target_funds=args.mstar_ids,
    )

    log.info(
        "run_fund_decisions_complete",
        funds_processed=result["funds_processed"],
        rows_written=result["rows_written"],
        errors=len(result["errors"]),
    )

    if result["errors"]:
        for err in result["errors"]:
            log.error("run_fund_decisions_fund_error", **err)
        sys.exit(1)


if __name__ == "__main__":
    main()
