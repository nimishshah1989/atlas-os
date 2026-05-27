"""Macro ingest orchestrator — backfill and incremental modes.

Runs all 5 macro ingest sources and derives brent_inr.
Designed to be called from EC2 cron via pg_cron wrapper or directly:

    python -m atlas.ingest.macro.runner --mode=backfill --start=2016-01-01
    python -m atlas.ingest.macro.runner --mode=incremental

Sources orchestrated:
  1. FRED: us_10y_yield, india_10y_yield, risk_free_91d
  2. NSE FII/DII: fii_cash_equity_flow_cr, dii_flow (today only — NSE archives 404)
  2b. Monthly FII/DII bundled: fii_cash_equity_flow_cr + dii_flow via SEBI/NSE monthly
      net-flow data (2016-01 onward). Carry-forward to all daily rows in each month.
  3. MOSPI CPI (bundled): cpi_yoy
  4. Yahoo Finance ^INDIAVIX: vix_9d (NSE archives URL 404; Yahoo Finance is the source)
  5. Derived: brent_inr = brent_usd × atlas_macro_daily.usdinr (in-memory, no DB col)
  6. Forward-fill: india_10y_yield and risk_free_91d are monthly FRED series.
     After upserting monthly values, forward-fill propagates each value to all
     subsequent daily rows until the next monthly value.

brent_inr derivation:
  brent_usd is fetched from FRED DCOILBRENTEU and held in Python memory only.
  brent_usd is NOT a column in atlas_macro_daily — no DB write for brent_usd.
  The runner crosses brent_usd (in-memory) × usdinr (from DB) and writes brent_inr.

Forward-fill for monthly series:
  FRED india_10y_yield and risk_free_91d are monthly. atlas_macro_daily has daily rows.
  After each monthly upsert, _forward_fill_monthly_col() propagates the last known
  value to NULL rows via SQL correlated subquery. This gives ≥95% coverage for both cols.
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
    fii_dii_monthly_ingest,
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


def _forward_fill_monthly_col(
    col: str,
    engine: Engine,
    start: str = "2016-01-01",
) -> int:
    """Forward-fill a monthly column to all daily rows in atlas_macro_daily.

    Monthly FRED series (india_10y_yield, risk_free_91d) are upserted to
    atlas_macro_daily on the first calendar day of each month. This leaves
    all other daily rows NULL. This function fills each NULL row with the
    most recent non-NULL value on or before that date.

    Strategy: correlated subquery — for each NULL row, SELECT the latest
    non-NULL value from rows with date <= current row's date.

    Args:
        col:    Column name (must be one of the monthly FRED cols to prevent
                accidental use on daily series).
        engine: SQLAlchemy engine.
        start:  Earliest date to forward-fill from.

    Returns:
        Number of rows updated.

    SQL pattern:
        UPDATE atlas.atlas_macro_daily t
        SET col = (
            SELECT m.col FROM atlas.atlas_macro_daily m
            WHERE m.col IS NOT NULL AND m.date <= t.date
            ORDER BY m.date DESC
            LIMIT 1
        )
        WHERE t.col IS NULL AND t.date >= start_date
    """
    monthly_cols = frozenset({"india_10y_yield", "risk_free_91d", "cpi_yoy"})
    if col not in monthly_cols:
        raise ValueError(
            f"_forward_fill_monthly_col: col {col!r} not in monthly-safe set {monthly_cols}"
        )

    sql = f"""
        UPDATE atlas.atlas_macro_daily t
        SET {col} = (
            SELECT m.{col} FROM atlas.atlas_macro_daily m
            WHERE m.{col} IS NOT NULL AND m.date <= t.date
            ORDER BY m.date DESC
            LIMIT 1
        )
        WHERE t.{col} IS NULL AND t.date >= :start
    """  # noqa: S608 — col validated against frozenset above

    with engine.begin() as conn:
        result = conn.execute(text(sql), {"start": start})
        rows_updated = result.rowcount

    log.info(
        "forward_fill_monthly_col_done",
        col=col,
        start=start,
        rows_updated=rows_updated,
    )
    return rows_updated


def _forward_fill_any_col(
    col: str,
    engine: Engine,
    start: str = "2016-01-01",
) -> int:
    """Forward-fill any macro column to cover weekends/holidays and data gaps.

    Identical SQL pattern to _forward_fill_monthly_col but without col
    restriction — accepts all macro columns. Used for:
      - vix_9d: Yahoo Finance only has trading days; fill weekends
      - us_10y_yield: FRED only has trading days; fill weekends
      - brent_inr: FRED Brent is 5-day; fill weekends
      - cpi_yoy: fill months with no new CPI release yet

    Col is validated against an explicit safe-set to prevent SQL injection.

    Args:
        col:    Column name (must be in the safe-set of macro columns).
        engine: SQLAlchemy engine.
        start:  Earliest date to forward-fill from.

    Returns:
        Number of rows updated.
    """
    safe_cols = frozenset(
        {
            "us_10y_yield",
            "india_10y_yield",
            "risk_free_91d",
            "cpi_yoy",
            "vix_9d",
            "brent_inr",
            "fii_cash_equity_flow_cr",
            "dii_flow",
        }
    )
    if col not in safe_cols:
        raise ValueError(f"_forward_fill_any_col: col {col!r} not in safe macro set {safe_cols}")

    sql = f"""
        UPDATE atlas.atlas_macro_daily t
        SET {col} = (
            SELECT m.{col} FROM atlas.atlas_macro_daily m
            WHERE m.{col} IS NOT NULL AND m.date <= t.date
            ORDER BY m.date DESC
            LIMIT 1
        )
        WHERE t.{col} IS NULL AND t.date >= :start
    """  # noqa: S608 — col validated against frozenset above

    with engine.begin() as conn:
        result = conn.execute(text(sql), {"start": start})
        rows_updated = result.rowcount

    log.info(
        "forward_fill_any_col_done",
        col=col,
        start=start,
        rows_updated=rows_updated,
    )
    return rows_updated


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
        Includes "fii_dii_monthly" key for bundled monthly FII/DII rows processed.
    """
    eng = engine or get_engine()
    today = date.today().isoformat()
    results: dict[str, int] = {}

    log.info("macro_backfill_start", start=start, end=today)

    # 1. FRED — us_10y_yield, india_10y_yield, risk_free_91d
    #    (brent_usd is fetched separately for in-memory derivation; NOT in SERIES_MAP)
    log.info("macro_step", step=1, name="FRED")
    brent_usd_df: pd.DataFrame = pd.DataFrame(columns=["date", "value"])
    try:
        import os

        fred_results = fred_ingest.run_all(start=start, engine=eng)
        results.update(fred_results)
        # Fetch brent_usd raw (in-memory only) for brent_inr derivation
        if os.environ.get("FRED_API_KEY"):
            brent_usd_df = fred_ingest.fetch_series("DCOILBRENTEU", start, today)
            log.info("brent_usd_fetched", rows=len(brent_usd_df))
    except Exception as exc:
        log.error("fred_step_error", error=str(exc))

    # 1b. Forward-fill monthly FRED series to daily rows
    #     india_10y_yield and risk_free_91d are monthly; must fill daily gaps
    log.info("macro_step", step="1b", name="FORWARD_FILL_MONTHLY")
    for monthly_col in ("india_10y_yield", "risk_free_91d"):
        try:
            ff_count = _forward_fill_monthly_col(monthly_col, eng, start)
            results[f"ffill_{monthly_col}"] = ff_count
        except Exception as exc:
            log.error("forward_fill_error", col=monthly_col, error=str(exc))
            results[f"ffill_{monthly_col}"] = 0

    # 2. NSE FII/DII (historical BLOCKED — today only via React API)
    log.info(
        "macro_step",
        step=2,
        name="NSE_FII_DII",
        note="historical_blocked_404_see_nse_bhavcopy_ingest_docstring",
    )
    try:
        fii_count = nse_bhavcopy_ingest.run_all(start=start, engine=eng, csv_path=fii_dii_csv_path)
        results["fii_dii"] = fii_count
    except Exception as exc:
        log.error("nse_bhavcopy_step_error", error=str(exc))
        results["fii_dii"] = 0

    # 2b. Monthly FII/DII bundled data (SEBI/NSE public reports, carry-forward to daily)
    #     Fills fii_cash_equity_flow_cr + dii_flow from 2016-01 via monthly net flows.
    #     Forward-fill in step 6 propagates to any remaining NULL rows within each month.
    log.info("macro_step", step="2b", name="FII_DII_MONTHLY_BUNDLED")
    try:
        fii_monthly_count = fii_dii_monthly_ingest.run_all(engine=eng)
        results["fii_dii_monthly"] = fii_monthly_count
    except Exception as exc:
        log.error("fii_dii_monthly_step_error", error=str(exc))
        results["fii_dii_monthly"] = 0

    # 3. MOSPI CPI (bundled data — no network call; carry-forward done inside module)
    log.info("macro_step", step=3, name="MOSPI_CPI")
    try:
        cpi_count = mospi_cpi_ingest.run_all(engine=eng)
        results["cpi_yoy"] = cpi_count
    except Exception as exc:
        log.error("mospi_cpi_step_error", error=str(exc))
        results["cpi_yoy"] = 0

    # 4. NSE VIX via Yahoo Finance ^INDIAVIX (NSE archives 404 as of 2026-05-27)
    log.info("macro_step", step=4, name="YAHOO_VIX")
    try:
        vix_count = nse_vix_ingest.run_all(start=start, engine=eng, csv_path=vix_csv_path)
        results["vix_9d"] = vix_count
    except Exception as exc:
        log.error("nse_vix_step_error", error=str(exc))
        results["vix_9d"] = 0

    # 5. Derived: brent_inr = brent_usd (in-memory) × usdinr (from DB)
    log.info("macro_step", step=5, name="BRENT_INR_DERIVE")
    try:
        brent_inr_count = _derive_brent_inr(brent_usd_df, eng, start)
        results["brent_inr"] = brent_inr_count
    except Exception as exc:
        log.error("brent_inr_step_error", error=str(exc))
        results["brent_inr"] = 0

    # 6. Forward-fill trading-day columns to cover weekends/holidays.
    #    FRED and Yahoo Finance only publish on trading days; atlas_macro_daily
    #    has calendar-daily rows. Forward-fill propagates last known value.
    #    Also covers CPI gaps (months with no new release).
    log.info("macro_step", step=6, name="FORWARD_FILL_TRADING_DAY_GAPS")
    for daily_col in (
        "us_10y_yield",
        "cpi_yoy",
        "vix_9d",
        "brent_inr",
        "fii_cash_equity_flow_cr",
        "dii_flow",
    ):
        try:
            ff_count = _forward_fill_any_col(daily_col, eng, start)
            results[f"ffill_{daily_col}"] = ff_count
        except Exception as exc:
            log.error("forward_fill_daily_error", col=daily_col, error=str(exc))
            results[f"ffill_{daily_col}"] = 0

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
