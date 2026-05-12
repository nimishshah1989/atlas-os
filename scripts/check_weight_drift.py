"""Nightly CLI: detect drift on active weight sets, optionally revert.

Without ``--apply``, prints findings and exits 0.
With ``--apply``, executes the revert for every finding atomically.

The revert is disabled by default during the Stage 4c bootstrap window
(< 60 days of live-perf data); the script returns 0 with no findings
until enough history accumulates.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog

from atlas.db import get_engine
from atlas.intelligence.conviction.monitoring.drift_detector import (
    detect_drift,
    execute_revert,
)

log = structlog.get_logger()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", help="YYYY-MM-DD; default today")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Execute reverts for every finding (atomic per finding).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = get_engine()
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()

    log.info("drift_cli_start", as_of=str(as_of), apply=args.apply)
    findings = detect_drift(engine, as_of=as_of)
    if not findings:
        print("No drift findings — every active weight set is healthy.")
        return 0

    print(f"Drift findings: {len(findings)}")
    for f in findings:
        print(
            f"  {f.tier:>18s}  {f.n_days_below_threshold}/{f.n_days_window}d "
            f"below threshold  realized_avg={f.avg_realized_ic:+.4f}  "
            f"predicted={f.avg_predicted_ic:+.4f}  "
            f"restore_target={f.restore_target_version or '—'}"
        )

    if args.apply:
        n_done = 0
        for f in findings:
            rid = execute_revert(engine, f, triggered_by="auto-detector")
            if rid:
                n_done += 1
                print(f"  reverted {f.tier}: log id {rid}")
        print(f"Applied {n_done} reverts.")
    else:
        print("(dry run — use --apply to execute reverts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
