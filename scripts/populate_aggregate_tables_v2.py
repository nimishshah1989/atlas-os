"""One-off backfill: populate atlas_sector_state_v2, atlas_fund_state_v2,
atlas_etf_state_v2 for all trading days from 2025-01-01 to today.

Usage:
    python scripts/populate_aggregate_tables_v2.py [--from YYYY-MM-DD] [--to YYYY-MM-DD]

Defaults:
    --from  2025-01-01
    --to    today (UTC)

The script is safe to re-run: all three writers use ON CONFLICT DO UPDATE.

Expected runtime on t3.large:
    ~5 min for sector (750 stocks × ~330 trading days via SQL join — heavy)
    ~1 min for fund (3,506 lens rows — small)
    ~2 min for ETF (279,897 etf_states_daily rows — medium)

Do NOT run this during market hours — sector query will hit atlas_stock_state_daily
(276K rows) and may contend with nightly compute. Schedule after 22:00 IST.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import structlog
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Allow running from repo root without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlas.intelligence.aggregations.etf import (
    aggregate_etf_states,
    load_etf_holdings_panel,
)
from atlas.intelligence.aggregations.fund import (
    aggregate_fund_composition,
    load_fund_holdings_panel,
)
from atlas.intelligence.aggregations.persistence import (
    persist_etf_state_v2,
    persist_fund_state_v2,
    persist_sector_state_v2,
)
from atlas.intelligence.aggregations.sector import (
    aggregate_sector_states,
    load_stock_panel,
)

load_dotenv()
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))
log = structlog.get_logger()


def _trading_days(start: date, end: date, engine) -> list[date]:
    """Return all dates in [start, end] that have stock state rows."""
    with engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT DISTINCT date FROM atlas.atlas_stock_state_daily
                WHERE date BETWEEN :start AND :end
                  AND classifier_version = 'v2.0-validated'
                ORDER BY date
            """),
            {"start": start, "end": end},
        )
        return [r[0] for r in rows]


def run_sector_backfill(engine, start: date, end: date) -> None:
    """Sector: load full date range in one query, split by day in Python."""
    log.info("sector_backfill.start", start=str(start), end=str(end))
    panel = load_stock_panel(engine, as_of_date=None)
    # Filter to range
    panel = panel[(panel["date"] >= start) & (panel["date"] <= end)]
    before = len(panel)
    agg = aggregate_sector_states(panel)
    log.info(
        "sector_backfill.agg",
        input_rows=before,
        output_rows=len(agg),
    )
    n = persist_sector_state_v2(engine, agg)
    log.info("sector_backfill.done", upserted=n)


def run_fund_backfill(engine, start: date, end: date) -> None:
    """Fund: load full lens table, filter in Python, aggregate all at once."""
    log.info("fund_backfill.start", start=str(start), end=str(end))
    panel = load_fund_holdings_panel(engine, as_of_date=None)
    before = len(panel)
    panel = panel[(panel["date"] >= start) & (panel["date"] <= end)]
    log.info("fund_backfill.panel_loaded", total_rows=before, in_range=len(panel))
    agg = aggregate_fund_composition(panel)
    n = persist_fund_state_v2(engine, agg)
    log.info("fund_backfill.done", upserted=n)


def run_etf_backfill(engine, start: date, end: date) -> None:
    """ETF: load full etf_states_daily for range, aggregate, persist."""
    log.info("etf_backfill.start", start=str(start), end=str(end))
    panel = load_etf_holdings_panel(engine, as_of_date=None)
    before = len(panel)
    panel = panel[(panel["date"] >= start) & (panel["date"] <= end)]
    log.info("etf_backfill.panel_loaded", total_rows=before, in_range=len(panel))
    agg = aggregate_etf_states(panel)
    n = persist_etf_state_v2(engine, agg)
    log.info("etf_backfill.done", upserted=n)


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate v2 aggregate tables.")
    parser.add_argument(
        "--from",
        dest="from_date",
        default="2025-01-01",
        help="Start date YYYY-MM-DD (default 2025-01-01)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=str(date.today()),
        help="End date YYYY-MM-DD (default today)",
    )
    parser.add_argument(
        "--only",
        choices=["sector", "fund", "etf"],
        default=None,
        help="Run only one aggregator",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        log.error("ATLAS_DB_URL not set")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)

    log.info("backfill.begin", start=str(start), end=str(end), only=args.only)

    try:
        if args.only in (None, "sector"):
            run_sector_backfill(engine, start, end)
        if args.only in (None, "fund"):
            run_fund_backfill(engine, start, end)
        if args.only in (None, "etf"):
            run_etf_backfill(engine, start, end)
    except Exception:
        log.exception("backfill.error")
        sys.exit(1)

    log.info("backfill.complete")


if __name__ == "__main__":
    main()
