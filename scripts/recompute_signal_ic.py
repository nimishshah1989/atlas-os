"""Nightly CLI: compute rolling out-of-sample IC per (tier, signal).

Usage:
    python scripts/recompute_signal_ic.py [--as-of YYYY-MM-DD] [--persist]
    python scripts/recompute_signal_ic.py [--lookback 90] [--horizon 21]

Default ``--as-of`` anchors to ``LEAST(metrics_max, ohlcv_max)`` so we
never compute IC over a window where data does not exist (matches the
Stage 3 conviction CLI anchoring).

Exit codes:
    0 success
    2 bad arguments
    3 no anchor date available
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

import structlog
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.optimization.ic_monitor import (
    DEFAULT_FORWARD_HORIZON,
    DEFAULT_LOOKBACK_DAYS,
    measure_all_tiers,
)
from atlas.intelligence.conviction.optimization.persistence import upsert_ic_batch

log = structlog.get_logger()


def _resolve_default_as_of(engine):
    sql = text("""
        SELECT LEAST(
          (SELECT MAX(date) FROM atlas.atlas_stock_metrics_daily),
          (SELECT MAX(date) FROM public.de_equity_ohlcv WHERE data_status = 'validated')
        )
    """)
    with engine.connect() as c:
        return c.execute(sql).scalar()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", help="YYYY-MM-DD; default = LEAST(metrics, ohlcv)")
    p.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Lookback window in calendar days",
    )
    p.add_argument(
        "--horizon",
        type=int,
        default=DEFAULT_FORWARD_HORIZON,
        help="Forward-return horizon in trading days",
    )
    p.add_argument("--persist", action="store_true", help="Write results to DB")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = get_engine()

    if args.as_of:
        as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    else:
        resolved = _resolve_default_as_of(engine)
        if not resolved:
            log.error("no_anchor_date")
            return 3
        as_of = resolved

    log.info(
        "ic_monitor_start",
        as_of=str(as_of),
        lookback=args.lookback,
        horizon=args.horizon,
    )
    measurements = measure_all_tiers(
        engine,
        as_of=as_of,
        lookback_days=args.lookback,
        forward_horizon=args.horizon,
    )
    if not measurements:
        log.warning("ic_monitor_no_measurements", as_of=str(as_of))
        return 0

    print(
        f"Computed {len(measurements)} IC measurements across "
        f"{len({m.tier for m in measurements})} tiers."
    )
    for m in measurements[:10]:
        print(
            f"  {m.tier:>18s}  {m.signal_name:<18s}  "
            f"IC={m.ic:+.4f}  t={m.t_stat or 0:+.2f}  n={m.n_observations}"
        )
    if len(measurements) > 10:
        print(f"  ... and {len(measurements) - 10} more")

    if args.persist:
        n = upsert_ic_batch(engine, measurements)
        print(f"Persisted {n} rows to atlas_signal_ic_rolling.")
    else:
        print("(dry run — use --persist to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
