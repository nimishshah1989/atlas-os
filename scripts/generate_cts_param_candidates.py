"""Generate CTS threshold calibration proposals. Run nightly.

Waits for >=30 days of fwd_ret data before generating proposals (no-op otherwise).
"""

from __future__ import annotations

import argparse
from datetime import date

import structlog

from atlas.db import get_engine, load_thresholds
from atlas.intelligence.cts.auto_calibration.param_candidates import generate_proposals
from atlas.intelligence.cts.auto_calibration.persistence import insert_proposals

log = structlog.get_logger()


def run(as_of_date: date, *, persist: bool) -> None:
    engine = get_engine()
    thresholds = load_thresholds(engine=engine)
    proposals = generate_proposals(engine, as_of_date, thresholds)
    log.info("cts_proposals_generated", count=len(proposals))
    if proposals and persist:
        insert_proposals(engine, proposals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), persist=args.persist)
