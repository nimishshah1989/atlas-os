"""Atlas-M2 daily incremental run.

Computes T-1 metrics + states for stocks and ETFs. Runs nightly from EC2
cron at 21:00 IST (after JIP T-1 ingest completes). Budget: ≤8 minutes total.

Usage::

    python scripts/m2_daily.py                # T-1 (yesterday)
    python scripts/m2_daily.py --date 2026-05-05
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.compute.etfs import run_etf_daily  # noqa: E402
from atlas.compute.stocks import run_stock_daily  # noqa: E402

log = structlog.get_logger()


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas-M2 daily incremental run")
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=date.today() - timedelta(days=1),
        help="Target date (YYYY-MM-DD). Defaults to yesterday.",
    )
    args = parser.parse_args()

    log.info("m2_daily_starting", target_date=str(args.date))

    stock_result = run_stock_daily(args.date)
    print(f"[stocks] {stock_result}")

    etf_result = run_etf_daily(args.date)
    print(f"[etfs] {etf_result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
