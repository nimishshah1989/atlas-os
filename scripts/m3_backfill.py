"""Atlas-M3 historical backfill entry point.

Runs Phase A (indices) → Phase B (sectors) → Phase C (market regime) in
order. Each phase reads metrics produced by the previous one, so order
matters.

Usage::

    python scripts/m3_backfill.py                       # all phases
    python scripts/m3_backfill.py --phase A             # indices only
    python scripts/m3_backfill.py --phase B             # sectors only
    python scripts/m3_backfill.py --phase C             # regime only
    python scripts/m3_backfill.py --start 2024-01-01 --end 2024-12-31

Per the M2 deploy pattern: target EC2 (``jsl-wealth-server``); local Mac
hits psycopg2 stalls on Supabase pooler at this volume.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute.indices import backfill_index_metrics  # noqa: E402
from atlas.compute.regime import backfill_regime  # noqa: E402
from atlas.compute.sectors import backfill_sector_metrics  # noqa: E402

log = structlog.get_logger()


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas-M3 historical backfill")
    parser.add_argument(
        "--phase",
        choices=["A", "B", "C", "all"],
        default="all",
        help="Run only one phase (A=indices, B=sectors, C=regime). Default: all.",
    )
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=None,
        help="Start date (YYYY-MM-DD). Defaults to HISTORICAL_START_DATE.",
    )
    parser.add_argument(
        "--end", type=_parse_date, default=None, help="End date (YYYY-MM-DD). Defaults to today."
    )
    args = parser.parse_args()

    overall_start = datetime.now()

    if args.phase in ("A", "all"):
        log.info("m3_backfill_phase_a_starting")
        rows = backfill_index_metrics(start_date=args.start, end_date=args.end)
        print(f"[Phase A indices] rows_written={rows}")

    if args.phase in ("B", "all"):
        log.info("m3_backfill_phase_b_starting")
        rows = backfill_sector_metrics(start_date=args.start, end_date=args.end)
        print(f"[Phase B sectors] rows_written={rows}")

    if args.phase in ("C", "all"):
        log.info("m3_backfill_phase_c_starting")
        rows = backfill_regime(start_date=args.start, end_date=args.end)
        print(f"[Phase C regime] rows_written={rows}")

    elapsed = (datetime.now() - overall_start).total_seconds() / 60
    print(f"[m3_backfill] complete in {elapsed:.1f} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
