"""Macro ingest orchestrator — backfill and incremental modes.

Runs all 5 macro ingest sources and derives brent_inr.
Designed to be called from EC2 cron via pg_cron wrapper or directly:

    python -m atlas.ingest.macro.runner --mode=backfill --start=2016-01-01
    python -m atlas.ingest.macro.runner --mode=incremental

Sources orchestrated:
  1. FRED: us_10y_yield, india_10y_yield, brent_usd (temp), risk_free_91d
  2. NSE bhavcopy: fii_cash_equity_flow_cr, dii_flow
  3. MOSPI CPI (bundled): cpi_yoy
  4. NSE VIX: vix_9d
  5. Derived: brent_inr = brent_usd × atlas_macro_daily.usdinr (SQL UPDATE)

brent_inr derivation:
  brent_usd is ingested temporarily via FRED (DCOILBRENTEU), stored in a
  staging step, then crossed with the existing usdinr column already in
  atlas_macro_daily (populated by the main atlas compute pipeline).

  SQL: UPDATE atlas.atlas_macro_daily
       SET brent_inr = brent_usd_stage * usdinr
       WHERE brent_usd_stage IS NOT NULL AND usdinr IS NOT NULL;

  After derivation, brent_usd column (if staging) is left as-is.
  Note: brent_usd is NOT a column in atlas_macro_daily by default;
  the runner uses atlas_macro_daily.brent_inr as the final target.
  The FRED brent_usd values are held in Python memory and crossed with
  usdinr from the DB before writing brent_inr directly.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine
from atlas.ingest.macro import (
    fred_ingest,
    mospi_cpi_ingest,
    nse_bhavcopy_ingest,
    nse_vix_ingest,
)

log = structlog.get_logger(__name__)

_DEFAULT_BACKFILL_START = "2016-01-01"
_INCREMENTAL_LOOKBACK_DAYS = 7


def _derive_brent_inr(
    brent_usd_df: pd.DataFrame,
    engine: Engine,
    start: str,
) -> int:
    """Compute brent_inr = brent_usd × usdinr and upsert.

    brent_usd_df has columns ["date", "value"] (from FRED DCOILBRENTEU).
    usdinr is fetched from atlas_macro_daily for the matching dates.

    Args:
        brent_usd_df: FRED Brent USD DataFrame (["date", "value"]).
        engine:       SQLAlchemy engine.
        start:        Earliest date to process.

    Returns:
        Number of brent_inr rows upserted.
    """
    if brent_usd_df.empty:
        log.warning("brent_inr_derive_skipped", reason="brent_usd_empty")
        return 0

    # Build brent_usd lookup dict: date → float
    brent_lookup: dict[str, float] = {}
    for _, row in brent_usd_df.iterrows():
        dt = str(row["date"])
        if dt >= start:
            brent_lookup[dt] = float(row["value"])

    if not brent_lookup:
        log.warning("brent_inr_derive_skipped", reason="no_brent_usd_after_start")
        return 0

    # Fetch usdinr from DB for the date range
    dates = sorted(brent_lookup.keys())
    date_start = dates[0]
    date_end = dates[-1]

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT date, usdinr FROM atlas.atlas_macro_daily"
                " WHERE date >= :start AND date <= :end AND usdinr IS NOT NULL"
            ),
            {"start": date_start, "end": date_end},
        ).fetchall()

    usdinr_lookup: dict[str, Decimal] = {str(r[0]): Decimal(str(r[1])) for r in rows}

    log.info(
        "brent_inr_derive_inputs",
        brent_usd_dates=len(brent_lookup),
        usdinr_dates=len(usdinr_lookup),
    )

    # Compute brent_inr for dates where both exist
    upserted = 0
    with engine.begin() as conn:
        for dt, brent_usd in brent_lookup.items():
            usdinr = usdinr_lookup.get(dt)
            if usdinr is None:
                continue  # No FX rate for this date — skip

            brent_inr = Decimal(str(round(brent_usd, 4))) * usdinr
            conn.execute(
                text(
                    "INSERT INTO atlas.atlas_macro_daily (date, brent_inr) VALUES (:d, :v)"
                    " ON CONFLICT (date) DO UPDATE SET brent_inr = EXCLUDED.brent_inr"
                ),
                {"d": dt, "v": brent_inr.quantize(Decimal("0.0001"))},
            )
            upserted += 1

    log.info("brent_inr_upserted", rows=upserted)
    return upserted


def run_backfill(
    start: str = _DEFAULT_BACKFILL_START,
    engine: Engine | None = None,
    fii_dii_csv_path: str | None = None,
    vix_csv_path: str | None = None,
) -> dict[str, int]:
    """Run full historical backfill of all 8 macro columns.

    Args:
        start:            Earliest date for backfill (ISO "YYYY-MM-DD").
        engine:           Optional engine override.
        fii_dii_csv_path: Override NSE FII/DII CSV path (for testing).
        vix_csv_path:     Override NSE VIX CSV path (for testing).

    Returns:
        Dict mapping source/column name → rows upserted.
    """
    eng = engine or get_engine()
    today = date.today().isoformat()
    results: dict[str, int] = {}

    log.info("macro_backfill_start", start=start, end=today)

    # 1. FRED — us_10y_yield, india_10y_yield, brent_usd, risk_free_91d
    log.info("macro_step", step=1, name="FRED")
    brent_usd_df: pd.DataFrame = pd.DataFrame(columns=["date", "value"])
    try:
        fred_results = fred_ingest.run_all(start=start, engine=eng)
        results.update(fred_results)
        # Also fetch brent_usd raw for derivation (separate from upsert cols)
        import os

        if os.environ.get("FRED_API_KEY"):
            brent_usd_df = fred_ingest.fetch_series("DCOILBRENTEU", start, today)
            log.info("brent_usd_fetched", rows=len(brent_usd_df))
    except Exception as exc:
        log.error("fred_step_error", error=str(exc))

    # 2. NSE FII/DII bhavcopy
    log.info("macro_step", step=2, name="NSE_FII_DII")
    try:
        fii_count = nse_bhavcopy_ingest.run_all(start=start, engine=eng, csv_path=fii_dii_csv_path)
        results["fii_dii"] = fii_count
    except Exception as exc:
        log.error("nse_bhavcopy_step_error", error=str(exc))
        results["fii_dii"] = 0

    # 3. MOSPI CPI (bundled data — no network call)
    log.info("macro_step", step=3, name="MOSPI_CPI")
    try:
        cpi_count = mospi_cpi_ingest.run_all(engine=eng)
        results["cpi_yoy"] = cpi_count
    except Exception as exc:
        log.error("mospi_cpi_step_error", error=str(exc))
        results["cpi_yoy"] = 0

    # 4. NSE VIX
    log.info("macro_step", step=4, name="NSE_VIX")
    try:
        vix_count = nse_vix_ingest.run_all(start=start, engine=eng, csv_path=vix_csv_path)
        results["vix_9d"] = vix_count
    except Exception as exc:
        log.error("nse_vix_step_error", error=str(exc))
        results["vix_9d"] = 0

    # 5. Derived: brent_inr = brent_usd × usdinr
    log.info("macro_step", step=5, name="BRENT_INR_DERIVE")
    try:
        brent_inr_count = _derive_brent_inr(brent_usd_df, eng, start)
        results["brent_inr"] = brent_inr_count
    except Exception as exc:
        log.error("brent_inr_step_error", error=str(exc))
        results["brent_inr"] = 0

    log.info("macro_backfill_complete", results=results)
    return results


def run_incremental(
    lookback_days: int = _INCREMENTAL_LOOKBACK_DAYS,
    engine: Engine | None = None,
) -> dict[str, int]:
    """Run incremental update for the last N days.

    Designed for nightly cron execution. Fetches only recent data.
    NSE FII/DII and VIX always download the full file (NSE archive format);
    only recent rows are upserted.

    Args:
        lookback_days: Number of days of recent data to process.
        engine:        Optional engine override.

    Returns:
        Dict mapping source/column name → rows upserted.
    """
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    log.info("macro_incremental_start", start=start, lookback_days=lookback_days)
    return run_backfill(start=start, engine=engine)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Atlas macro ingest orchestrator (backfill + incremental)."
    )
    p.add_argument(
        "--mode",
        choices=["backfill", "incremental"],
        required=True,
        help="backfill: full history from --start. incremental: last 7 days.",
    )
    p.add_argument(
        "--start",
        default=_DEFAULT_BACKFILL_START,
        help=f"Start date for backfill (ISO YYYY-MM-DD). Default: {_DEFAULT_BACKFILL_START}",
    )
    args = p.parse_args()

    if args.mode == "backfill":
        result = run_backfill(start=args.start)
    else:
        result = run_incremental()

    print("\n=== Macro Ingest Results ===")
    for key, count in sorted(result.items()):
        print(f"  {key:<30s} {count:>6d} rows")
    print("===========================\n")

    # Exit non-zero if all sources returned 0 (indicates total failure)
    total = sum(result.values())
    if total == 0:
        print("WARNING: All sources returned 0 rows. Check logs.", file=sys.stderr)
        sys.exit(1)
