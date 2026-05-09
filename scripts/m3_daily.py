"""Atlas-M3 daily incremental run.

Runs the most recent ~10-day window through indices → sectors → regime.
Designed for the same nightly cron slot as M2 (``scripts/m2_daily.py``).
Each phase persists its own rows; downstream phases read the freshly-written
metrics from the previous phase.

Usage::

    python scripts/m3_daily.py
    python scripts/m3_daily.py --phase B
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute.indices import run_daily_index_metrics  # noqa: E402
from atlas.compute.regime import run_daily_regime  # noqa: E402
from atlas.compute.sectors import run_daily_sector_metrics  # noqa: E402
from atlas.health.runs import safe_finish, safe_record  # noqa: E402

log = structlog.get_logger()


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas-M3 daily incremental run")
    parser.add_argument(
        "--phase",
        choices=["A", "B", "C", "all"],
        default="all",
        help="Run only one phase (A=indices, B=sectors, C=regime). Default: all.",
    )
    args = parser.parse_args()

    overall_start = datetime.now()
    run_id = safe_record("m3_daily", milestone="M3", phase=args.phase)
    total_rows = 0

    try:
        if args.phase in ("A", "all"):
            log.info("m3_daily_phase_a_starting")
            rows = run_daily_index_metrics()
            print(f"[Phase A indices] rows_written={rows}")
            total_rows += rows

        if args.phase in ("B", "all"):
            log.info("m3_daily_phase_b_starting")
            rows = run_daily_sector_metrics()
            print(f"[Phase B sectors] rows_written={rows}")
            total_rows += rows

        if args.phase in ("C", "all"):
            log.info("m3_daily_phase_c_starting")
            rows = run_daily_regime()
            print(f"[Phase C regime] rows_written={rows}")
            total_rows += rows
    except Exception as exc:
        safe_finish(run_id, status="failed", rows_written=total_rows, error=exc)
        raise

    safe_finish(run_id, status="success", rows_written=total_rows)
    elapsed = (datetime.now() - overall_start).total_seconds() / 60
    print(f"[m3_daily] complete in {elapsed:.1f} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
