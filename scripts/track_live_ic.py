"""Nightly CLI: realized IC of every active composite weight set."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.monitoring.live_ic_tracker import (
    measure_all_active_versions,
)
from atlas.intelligence.conviction.monitoring.persistence import (
    upsert_live_perf_batch,
)

log = structlog.get_logger()


def _resolve_default_as_of(engine) -> date | None:
    sql = text("""
        SELECT LEAST(
          (SELECT MAX(date) FROM atlas.atlas_stock_metrics_daily),
          (SELECT MAX(date) FROM public.de_equity_ohlcv WHERE data_status IN ('raw', 'validated'))
        )
    """)
    with engine.connect() as c:
        return c.execute(sql).scalar()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", help="YYYY-MM-DD; default LEAST(metrics, ohlcv)")
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

    log.info("live_ic_cli_start", as_of=str(as_of), persist=args.persist)
    measurements = measure_all_active_versions(engine, as_of=as_of)
    if not measurements:
        log.warning("no_live_ic_measurements", as_of=str(as_of))
        return 0

    print(f"Computed live IC for {len(measurements)} active weight sets.")
    for m in measurements:
        pred = f"{m.predicted_holdout_ic:+.4f}" if m.predicted_holdout_ic else "—"
        ratio = f"{m.ic_ratio:+.2f}" if m.ic_ratio is not None else "—"
        print(
            f"  {m.tier:>18s}  realized={m.realized_ic:+.4f}  "
            f"predicted={pred:>8}  ratio={ratio:>6}  n={m.n_observations}"
        )

    if args.persist:
        n = upsert_live_perf_batch(engine, measurements)
        print(f"Persisted {n} rows.")
    else:
        print("(dry run — use --persist to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
