"""Nightly CLI: per-stock hit-rate primitive."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.monitoring.hit_rate_engine import (
    compute_hit_rates_batch,
)
from atlas.intelligence.conviction.monitoring.persistence import (
    upsert_hit_rates_batch,
)

log = structlog.get_logger()


def _resolve_default_as_of(engine) -> date | None:
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
    p.add_argument("--as-of", help="YYYY-MM-DD; default LEAST(metrics, ohlcv)")
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--persist", action="store_true")
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

    log.info("hit_rate_cli_start", as_of=str(as_of), lookback=args.lookback)
    rows = compute_hit_rates_batch(engine, as_of=as_of, lookback_window=args.lookback)
    if not rows:
        print("No hit-rate rows produced (no conviction data in window).")
        return 0

    n_with_rate = sum(1 for r in rows if r.hit_rate is not None)
    print(f"Computed hit-rate for {len(rows)} instruments " f"({n_with_rate} with sufficient n).")

    if args.persist:
        n = upsert_hit_rates_batch(engine, rows)
        print(f"Persisted {n} rows.")
    else:
        print("(dry run — use --persist to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
