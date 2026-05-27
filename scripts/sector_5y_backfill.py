"""5-year backfill of 8 new sector metric columns.

Fills ``rs_1w``, ``rs_1m``, ``rs_6m``, ``rs_12m``, ``pct_above_ema20``,
``pct_above_ema200``, ``pct_52wh``, and ``hhi`` in
``atlas.atlas_sector_metrics_daily``.

Processes one calendar year at a time to keep memory usage under control.
Loads a 252-day OHLCV lookback per year for the rolling 52-week high.

Usage (on EC2)::

    cd ~/atlas-os
    source .venv/bin/activate
    python scripts/sector_5y_backfill.py 2>&1 | tee /tmp/sector_5y.log

    # Optional year range override:
    python scripts/sector_5y_backfill.py --start-year 2020 --end-year 2023

Expected runtime: ~15-25 minutes for 10 years on t3.large.

Exit codes:
    0  — success (all years written, ≥ 95% coverage on every column)
    1  — partial failure (some years failed; log shows which)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import structlog
from psycopg2.extras import execute_values

from atlas.compute._session import open_compute_session
from atlas.compute.sectors import (
    compute_52wh_per_sector,
    compute_breadth_per_sector,
    compute_concentration_per_sector,
    compute_rs_windows,
    load_sector_stock_data,
)
from atlas.db import get_engine

log = structlog.get_logger()

# Historical start matches Config.HISTORICAL_START_DATE
HISTORICAL_START = date(2016, 4, 7)
OHLCV_LOOKBACK_DAYS = 260  # ~252 + buffer for trading gaps

# Columns to update — NOT the full row. We only touch the 8 new columns
# so existing rows keep their other values.
UPDATE_COLS = [
    "sector_name",
    "date",
    "rs_1w",
    "rs_1m",
    "rs_6m",
    "rs_12m",
    "pct_above_ema20",
    "pct_above_ema200",
    "pct_52wh",
    "hhi",
]


def load_nifty500_extended(
    engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load Nifty 500 returns including 6m and 12m from atlas_index_metrics_daily."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, ret_1w, ret_1m, ret_6m, ret_12m
            FROM atlas.atlas_index_metrics_daily
            WHERE index_code = 'NIFTY 500'
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY date
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.rename(
            columns={
                "ret_1w": "_n500_ret_1w",
                "ret_1m": "_n500_ret_1m",
                "ret_6m": "_n500_ret_6m",
                "ret_12m": "_n500_ret_12m",
            }
        )
    log.info("nifty500_extended_loaded", rows=len(df))
    return df


def load_stock_ret12m(
    engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load ret_12m from atlas_stock_metrics_daily for instruments in universe.

    load_sector_stock_data doesn't include ret_12m. This function loads
    just (instrument_id, date, ret_12m) to merge into the stock data frame.
    """
    # Include lookback buffer matching load_sector_stock_data's 900-day default
    load_start = start_date - timedelta(days=900)
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT m.instrument_id, m.date, m.ret_12m
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id = m.instrument_id
                AND u.effective_to IS NULL
            WHERE m.date BETWEEN %(start)s AND %(end)s
            ORDER BY m.instrument_id, m.date
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("stock_ret12m_loaded", rows=len(df))
    return df


def load_sector_master(engine) -> pd.DataFrame:
    """Load active sector master."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            "SELECT sector_name FROM atlas.atlas_sector_master WHERE is_active = TRUE",
            conn,
        )
    return df


def load_ohlcv_rolling_max(
    engine,
    start_date: date,
    end_date: date,
    instrument_ids: list[str],
) -> pd.DataFrame:
    """Load 252-day rolling max of close_adj per instrument.

    Uses a SQL window function to compute the rolling max server-side —
    avoids loading the full OHLCV table into Python.

    Returns DataFrame with columns: instrument_id, date, rolling_max_252.
    Only rows in [start_date, end_date] are returned (lookback done in SQL).
    """
    if not instrument_ids:
        return pd.DataFrame(columns=["instrument_id", "date", "rolling_max_252"])

    # We need at least OHLCV_LOOKBACK_DAYS before start to warm up the window.
    ohlcv_start = start_date - timedelta(days=OHLCV_LOOKBACK_DAYS)

    query = """
        WITH windowed AS (
            SELECT
                instrument_id,
                date,
                MAX(COALESCE(close_adj, close)) OVER (
                    PARTITION BY instrument_id
                    ORDER BY date
                    ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                ) AS rolling_max_252
            FROM public.de_equity_ohlcv
            WHERE date BETWEEN %(ohlcv_start)s AND %(end)s
              AND instrument_id = ANY(%(ids)s)
        )
        SELECT instrument_id, date, rolling_max_252
        FROM windowed
        WHERE date BETWEEN %(start)s AND %(end)s
        ORDER BY instrument_id, date
    """

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            query,
            conn,
            params={
                "ohlcv_start": ohlcv_start,
                "start": start_date,
                "end": end_date,
                "ids": instrument_ids,
            },
        )

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info(
        "ohlcv_rolling_max_loaded",
        rows=len(df),
        instruments=df["instrument_id"].nunique() if not df.empty else 0,
    )
    return df


def compute_sector_new_cols_for_year(
    stock_data: pd.DataFrame,
    nifty500_df: pd.DataFrame,
    rolling_max_df: pd.DataFrame,
    write_start: date,
    write_end: date,
) -> pd.DataFrame:
    """Compute all 8 new columns for a batch of dates.

    Args:
        stock_data: Output of load_sector_stock_data — long-form per (instrument, date).
        nifty500_df: Nifty 500 extended returns (incl. 6m/12m).
        rolling_max_df: Per-instrument 252-day rolling max from OHLCV.
        write_start / write_end: Date range to include in output.

    Returns:
        DataFrame with columns matching UPDATE_COLS.
    """
    # Filter to write window only
    work = stock_data[
        (stock_data["date"] >= write_start) & (stock_data["date"] <= write_end)
    ].copy()

    if work.empty:
        log.warning("no_stock_data_for_window", start=str(write_start), end=str(write_end))
        return pd.DataFrame(columns=UPDATE_COLS)

    row_before = len(work)
    log.info("batch_stock_data", rows=row_before, sectors=work["sector_name"].nunique())

    # ---- close_approx -------------------------------------------------------
    # Reconstruct if not present (should be in load_sector_stock_data output).
    if "close_approx" not in work.columns:
        ema200 = pd.to_numeric(work.get("ema_200_stock"), errors="coerce")
        ext = pd.to_numeric(work.get("extension_pct"), errors="coerce")
        work["close_approx"] = ema200 * (1.0 + ext)

    # ---- 1. Bottom-up sector returns (for RS windows) ----------------------
    # We need weighted-mean of ret_1w/1m/6m/12m per sector/date.
    metric_cols = ("ret_1w", "ret_1m", "ret_6m", "ret_12m")
    vol = pd.to_numeric(work.get("avg_volume_20"), errors="coerce")
    close = pd.to_numeric(work.get("close_approx"), errors="coerce")
    weight = (vol * close).where((vol > 0) & (close > 0), other=np.nan)
    work["_weight"] = weight

    aggregated: dict[str, pd.Series] = {}
    for metric in metric_cols:
        v = pd.to_numeric(work[metric], errors="coerce")
        w = work["_weight"]
        valid_mask = v.notna() & w.notna()
        wv = (v * w).where(valid_mask, other=0.0)
        ww = w.where(valid_mask, other=0.0)
        num = wv.groupby([work["sector_name"], work["date"]], observed=True).sum()
        den = ww.groupby([work["sector_name"], work["date"]], observed=True).sum()
        wm = num / den.where(den > 0, other=np.nan)
        eq_mean = v.groupby([work["sector_name"], work["date"]], observed=True).mean()
        aggregated[f"bottomup_{metric}"] = wm.fillna(eq_mean)

    sector_returns = pd.DataFrame(aggregated).reset_index()
    sector_returns.columns = ["sector_name", "date", *list(aggregated.keys())]

    # ---- 2. RS windows ------------------------------------------------------
    rs_df = compute_rs_windows(sector_returns, nifty500_df)

    # ---- 3. EMA breadth -----------------------------------------------------
    breadth_df = compute_breadth_per_sector(work)

    # ---- 4. 52-week high proximity ------------------------------------------
    # Merge rolling_max_252 onto work frame
    if not rolling_max_df.empty:
        work_with_max = work.merge(
            rolling_max_df[["instrument_id", "date", "rolling_max_252"]],
            on=["instrument_id", "date"],
            how="left",
        )
    else:
        work_with_max = work.copy()
        work_with_max["rolling_max_252"] = np.nan

    pct52wh_df = compute_52wh_per_sector(work_with_max)

    # ---- 5. HHI concentration -----------------------------------------------
    hhi_df = compute_concentration_per_sector(work)

    # ---- Merge all into one sector x date frame ----------------------------
    keys = ["sector_name", "date"]
    result = (
        rs_df.merge(breadth_df, on=keys, how="outer")
        .merge(pct52wh_df, on=keys, how="outer")
        .merge(hhi_df, on=keys, how="outer")
    )

    if result.empty:
        return pd.DataFrame(columns=UPDATE_COLS)

    result = result.replace([np.inf, -np.inf], np.nan)
    row_after = len(result)
    log.info("batch_result", rows=row_after, sectors=result["sector_name"].nunique())

    return result[UPDATE_COLS]


def _update_new_cols(engine, df: pd.DataFrame) -> int:
    """UPDATE the 8 new columns on existing atlas_sector_metrics_daily rows.

    Uses a temporary table + UPDATE ... FROM so we only touch existing rows
    and don't violate NOT NULL on compute_run_id (which is not in UPDATE_COLS).

    Returns number of rows updated.
    """
    if df.empty:
        return 0

    # Build the SET clause dynamically from UPDATE_COLS minus the PK.
    data_cols = [c for c in UPDATE_COLS if c not in ("sector_name", "date")]
    set_clause = ", ".join(f"{c} = tmp.{c}" for c in data_cols)

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")

        # Create temp table matching the update shape
        col_defs = ", ".join(
            f"{c} DOUBLE PRECISION" if c not in ("sector_name",) else f"{c} TEXT"
            for c in UPDATE_COLS
            if c != "date"
        )
        cur.execute(
            f"CREATE TEMP TABLE _sector_new_cols ("
            f"sector_name TEXT, date DATE, {col_defs.replace('sector_name TEXT, ', '')})"
        )

        # Bulk-copy the result DataFrame into the temp table
        col_csv = ", ".join(UPDATE_COLS)
        rows = []
        for row in (
            df.astype(object).where(df.notna(), other=None).itertuples(index=False, name=None)
        ):
            rows.append(row)
        execute_values(
            cur,
            f"INSERT INTO _sector_new_cols ({col_csv}) VALUES %s",  # noqa: S608
            rows,
            page_size=3000,
        )

        # UPDATE target from temp table
        cur.execute(
            f"UPDATE atlas.atlas_sector_metrics_daily t "  # noqa: S608
            f"SET {set_clause} "
            f"FROM _sector_new_cols tmp "
            f"WHERE t.sector_name = tmp.sector_name AND t.date = tmp.date"
        )
        n_updated = cur.rowcount
        cur.execute("DROP TABLE IF EXISTS _sector_new_cols")
        raw.commit()

        log.info("partial_update_complete", rows_updated=n_updated)
        return n_updated
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def run_year_batch(
    engine,
    year: int,
    sector_master: pd.DataFrame,
) -> tuple[int, bool]:
    """Run backfill for one calendar year.

    Returns (rows_written, success).
    """
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    # Don't go past today
    today = date.today()
    if year_start > today:
        log.info("year_in_future_skip", year=year)
        return 0, True
    year_end = min(year_end, today)
    if year_start < HISTORICAL_START:
        year_start = HISTORICAL_START

    t0 = time.time()
    log.info("year_batch_start", year=year, start=str(year_start), end=str(year_end))

    try:
        # Load stock data (with lookback buffer for warm-up)
        stock_data = load_sector_stock_data(engine, start_date=year_start, end_date=year_end)
        if stock_data.empty:
            log.warning("year_batch_no_stock_data", year=year)
            return 0, True

        # Merge ret_12m (not included in load_sector_stock_data)
        ret12m_df = load_stock_ret12m(engine, year_start, year_end)
        if not ret12m_df.empty:
            stock_data = stock_data.merge(
                ret12m_df,
                on=["instrument_id", "date"],
                how="left",
            )
        else:
            stock_data["ret_12m"] = float("nan")

        # Get unique instrument IDs for OHLCV rolling max
        instrument_ids = stock_data["instrument_id"].unique().tolist()

        # Load extended Nifty 500 returns (ret_6m/12m)
        # Load with some buffer before year_start for RS windows
        n500_start = year_start - timedelta(days=30)
        nifty500_df = load_nifty500_extended(engine, n500_start, year_end)

        # Load OHLCV rolling max
        rolling_max_df = load_ohlcv_rolling_max(engine, year_start, year_end, instrument_ids)

        # Compute all 8 new columns
        result_df = compute_sector_new_cols_for_year(
            stock_data,
            nifty500_df,
            rolling_max_df,
            write_start=year_start,
            write_end=year_end,
        )

        if result_df.empty:
            log.warning("year_batch_no_results", year=year)
            return 0, True

        # UPDATE existing rows (not upsert — new rows are owned by the main pipeline).
        # We use a temporary table + UPDATE ... FROM pattern so partial column
        # updates don't violate the NOT NULL constraint on compute_run_id.
        n_written = _update_new_cols(engine, result_df)

        elapsed = round(time.time() - t0, 1)
        log.info(
            "year_batch_complete",
            year=year,
            rows_written=n_written,
            elapsed_sec=elapsed,
        )
        return n_written, True

    except Exception as exc:
        elapsed = round(time.time() - t0, 1)
        log.error(
            "year_batch_failed",
            year=year,
            error=str(exc),
            elapsed_sec=elapsed,
        )
        return 0, False


def verify_coverage(engine) -> dict[str, float]:
    """Query coverage of the 8 new columns post-backfill."""
    query = """
        SELECT
            1.0 * COUNT(rs_1w) / COUNT(*) AS cov_rs_1w,
            1.0 * COUNT(rs_1m) / COUNT(*) AS cov_rs_1m,
            1.0 * COUNT(rs_6m) / COUNT(*) AS cov_rs_6m,
            1.0 * COUNT(rs_12m) / COUNT(*) AS cov_rs_12m,
            1.0 * COUNT(pct_above_ema20) / COUNT(*) AS cov_ema20,
            1.0 * COUNT(pct_above_ema200) / COUNT(*) AS cov_ema200,
            1.0 * COUNT(pct_52wh) / COUNT(*) AS cov_52wh,
            1.0 * COUNT(hhi) / COUNT(*) AS cov_hhi
        FROM atlas.atlas_sector_metrics_daily
        WHERE date >= '2016-04-07'
    """
    with open_compute_session(engine) as conn:
        row = pd.read_sql(query, conn).iloc[0]
    coverage = {col: float(row[col]) for col in row.index}
    return coverage


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--start-year",
        type=int,
        default=HISTORICAL_START.year,
        help=f"First year to process (default: {HISTORICAL_START.year})",
    )
    p.add_argument(
        "--end-year",
        type=int,
        default=date.today().year,
        help=f"Last year to process (default: {date.today().year})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    engine = get_engine()
    sector_master = load_sector_master(engine)

    log.info(
        "backfill_start",
        start_year=args.start_year,
        end_year=args.end_year,
        sectors=len(sector_master),
    )

    total_written = 0
    failed_years: list[int] = []

    for year in range(args.start_year, args.end_year + 1):
        n_rows, success = run_year_batch(engine, year, sector_master)
        total_written += n_rows
        if not success:
            failed_years.append(year)

    log.info(
        "backfill_complete",
        total_rows_written=total_written,
        failed_years=failed_years,
    )

    if failed_years:
        log.error("some_years_failed", failed_years=failed_years)
        return 1

    # Verify coverage
    log.info("verifying_coverage")
    coverage = verify_coverage(engine)
    all_pass = True
    for col, cov in coverage.items():
        status = "PASS" if cov >= 0.95 else "FAIL"
        log.info("coverage_check", column=col, coverage=round(cov, 4), status=status)
        if cov < 0.95:
            all_pass = False

    if not all_pass:
        log.error("coverage_below_threshold", coverage=coverage)
        return 1

    log.info("backfill_success", total_rows=total_written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
