"""Nightly CLI: compute conviction scores for the latest available date.

Usage:
    python scripts/compute_conviction.py [--as-of YYYY-MM-DD] [--persist]

Default ``--as-of`` anchors to the most-recent date where BOTH
``atlas_stock_metrics_daily`` AND ``public.de_equity_ohlcv`` (validated)
have data — the smaller of the two MAX(date) values. This protects
against the case where metrics has been computed on a stale OHLCV
snapshot.

Without ``--persist``, runs end-to-end and prints a per-tier summary
but writes nothing. With ``--persist``, UPSERTs both
``atlas_stock_conviction_daily`` and ``atlas_tier_membership_daily``.

Exit codes:
    0  success
    2  bad arguments
    3  no data available for the chosen as_of
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import structlog
from sqlalchemy import text

from atlas.db import get_engine
from atlas.intelligence.conviction.composer import compute_conviction_scores
from atlas.intelligence.conviction.persistence import (
    persist_conviction_batch,
    persist_tier_membership_batch,
)
from atlas.intelligence.conviction.tier_assignment import compute_tier_membership

log = structlog.get_logger()


def _resolve_default_as_of(engine) -> date | None:
    """Pick the most recent date present in BOTH metrics and validated OHLCV."""
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
    p.add_argument(
        "--as-of",
        help="YYYY-MM-DD; default = LEAST(MAX metrics, MAX validated OHLCV)",
    )
    p.add_argument(
        "--persist",
        action="store_true",
        help="Write results to DB (default is dry-run)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    engine = get_engine()

    if args.as_of:
        as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    else:
        resolved = _resolve_default_as_of(engine)
        if not resolved:
            log.error("no_anchor_date_available")
            return 3
        as_of = resolved

    log.info("conviction_cli_start", as_of=str(as_of), persist=args.persist)

    tier_df = compute_tier_membership(engine, as_of=as_of)
    if tier_df.empty:
        log.error("no_tier_data", as_of=str(as_of))
        return 3

    conviction_df = compute_conviction_scores(engine, as_of=as_of)
    if conviction_df.empty:
        log.error("no_conviction_data", as_of=str(as_of))
        return 3

    summary = (
        conviction_df.groupby(["tier", "confidence_label"])
        .agg(n=("conviction_score", "size"), mean_score=("conviction_score", "mean"))
        .reset_index()
    )
    print(summary.to_string(index=False))

    if args.persist:
        n_tier = persist_tier_membership_batch(engine, tier_df)
        n_conv = persist_conviction_batch(engine, conviction_df)
        log.info("conviction_persisted", n_tier=n_tier, n_conviction=n_conv)
        print(f"\nPersisted: {n_tier} tier rows, {n_conv} conviction rows")
    else:
        print("\n(dry run — use --persist to write)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
