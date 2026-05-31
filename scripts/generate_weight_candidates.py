"""Nightly CLI: generate candidate weight-set proposals from rolling IC.

Usage:
    python scripts/generate_weight_candidates.py [--as-of YYYY-MM-DD] [--persist]

Should run AFTER ``scripts/recompute_signal_ic.py`` in the nightly
pipeline (the IC table must be populated for this run to find anything).

Exit codes:
    0 success (even if zero candidates were generated — that's normal)
    2 bad arguments
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog

from atlas.db import get_engine
from atlas.intelligence.conviction.optimization.candidate_generator import (
    generate_candidates,
)
from atlas.intelligence.conviction.optimization.persistence import insert_proposal

log = structlog.get_logger()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", help="YYYY-MM-DD; default = today")
    p.add_argument("--regime", default="all", help="regime filter (default: 'all')")
    p.add_argument("--persist", action="store_true", help="Write proposals to DB")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = get_engine()
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()

    log.info("candidate_gen_start", as_of=str(as_of), regime=args.regime)
    candidates = generate_candidates(engine, as_of=as_of, regime=args.regime)

    if not candidates:
        print("No candidates generated (no material change vs active weights).")
        return 0

    print(f"Generated {len(candidates)} candidate(s):")
    for c in candidates:
        print(f"  {c.tier:>18s}  Δ_ic={float(c.ic_delta or 0):+.4f}  top movers → {c.rationale}")

    if args.persist:
        n_inserted = 0
        for c in candidates:
            pid = insert_proposal(engine, c.to_payload())
            n_inserted += 1
            print(f"  inserted {pid} for tier {c.tier}")
        print(f"Persisted {n_inserted} proposals to atlas_weight_proposals.")
    else:
        print("(dry run — use --persist to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
