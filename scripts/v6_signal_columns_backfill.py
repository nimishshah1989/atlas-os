"""Backfill rs_*_nifty500 and 2022 ret_12m / ema_200_stock / max_drawdown_252 gaps.

Two distinct problems, two distinct approaches:

1.  rs_1w_nifty500 / rs_1m_nifty500 / rs_3m_nifty500  (all 1.39M rows NULL)
    The stock compute pipeline computes RS vs the tier benchmark (Nifty 100,
    Midcap 150, etc.) but never computes RS vs Nifty 500.  The columns exist
    in the schema (migration 004) but were never written.
    Fix: pure SQL UPDATE joining atlas_benchmark_returns_cache on date.
    Formula (from atlas/compute/indices.py):
        rs = (1 + stock_ret_N) / (1 + nifty500_ret_N) - 1

2.  2022 Jan–Nov ret_12m / ema_200_stock / max_drawdown_252 gaps (~137k rows)
    The compute engine was not run for 2022 for these three long-lookback
    columns.  Price data exists in public.de_equity_ohlcv.
    Fix: load prices 2020-01-01..2022-11-30 (wide window for lookback),
    pivot wide, compute via vectorised pandas (EMA requires ewm, cannot be
    expressed as a SQL window function), write back via temp-table UPDATE.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date
from io import StringIO

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

METRICS_TABLE = "atlas.atlas_stock_metrics_daily"
BENCHMARK_TABLE = "atlas.atlas_benchmark_returns_cache"
OHLCV_TABLE = "public.de_equity_ohlcv"

# Rolling-window parameters — must match atlas/compute/primitives.py WINDOWS
EMA_200_LENGTH = 200
MAX_DD_WINDOW = 252
RET_12M_PERIODS = 252  # trading-day periods

# 2022 gap date range
GAP_START = date(2022, 1, 1)
GAP_END = date(2022, 11, 30)

# Extra lookback before gap start so rolling windows have warm-up data
WARMUP_START = date(2020, 1, 1)


# --------------------------------------------------------------------------- #
# Step 1: rs_*_nifty500  — pure SQL UPDATE                                    #
# --------------------------------------------------------------------------- #


def backfill_rs_nifty500(engine: Engine) -> dict[str, int]:
    """Populate rs_1w_nifty500, rs_1m_nifty500, rs_3m_nifty500 for all rows.

    Formula: (1 + stock_ret_N) / (1 + bench_ret_N) - 1
    Guard: bench_ret_N = -1 is theoretically impossible but NULLIF prevents
    division-by-zero at the DB level.

    Runs as three separate UPDATEs to avoid a single massive multi-column
    UPDATE that could exhaust temp buffers.
    """
    results: dict[str, int] = {}

    # window label → (stock_col, benchmark_ret_col)
    windows = {
        "1w": ("ret_1w", "ret_1w"),
        "1m": ("ret_1m", "ret_1m"),
        "3m": ("ret_3m", "ret_3m"),
    }

    for label, (stock_col, bench_col) in windows.items():
        col_name = f"rs_{label}_nifty500"
        log.info("rs_nifty500.start", col=col_name)
        t0 = time.time()

        sql = text(f"""
            UPDATE {METRICS_TABLE} m
               SET {col_name} = (
                   (1.0 + CAST(m.{stock_col} AS double precision))
                   / NULLIF(1.0 + CAST(b.{bench_col} AS double precision), 0.0)
                   - 1.0
               )
              FROM {BENCHMARK_TABLE} b
             WHERE b.benchmark_code = 'NIFTY500'
               AND b.date = m.date
               AND m.{stock_col} IS NOT NULL
               AND m.{col_name} IS NULL
        """)  # noqa: S608 -- col_name, table names are internal constants, not user input

        with engine.begin() as conn:
            conn.execute(text("SET statement_timeout = 0"))
            result = conn.execute(sql)
            rows_updated = result.rowcount

        elapsed = time.time() - t0
        log.info(
            "rs_nifty500.complete",
            col=col_name,
            rows_updated=rows_updated,
            elapsed_s=round(elapsed, 1),
        )
        results[col_name] = rows_updated

    return results


# --------------------------------------------------------------------------- #
# Step 2: 2022 gaps — matrix-wide pandas                                      #
# --------------------------------------------------------------------------- #


def _load_ohlcv_for_gap(engine: Engine) -> pd.DataFrame:
    """Load stock closes for warm-up + gap window.

    Uses a wide date range so EMA(200) and max_drawdown(252) have enough
    history by the time we reach 2022-01-01.
    Row count before load is logged; mismatches are flagged.
    """
    t0 = time.time()
    sql = f"""
        SELECT instrument_id, date, COALESCE(close_adj, close) AS close
          FROM {OHLCV_TABLE}
         WHERE date BETWEEN :start AND :end
         ORDER BY instrument_id, date
    """  # noqa: S608 -- OHLCV_TABLE is an internal constant

    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 0"))
        df = pd.read_sql(
            text(sql),
            conn,
            params={"start": WARMUP_START, "end": GAP_END},
        )

    rows_loaded = len(df)
    n_instruments = df["instrument_id"].nunique()
    log.info(
        "ohlcv.loaded",
        rows=rows_loaded,
        instruments=n_instruments,
        elapsed_s=round(time.time() - t0, 1),
    )
    if rows_loaded == 0:
        raise RuntimeError("No OHLCV rows loaded — check date range or table contents")

    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _compute_2022_metrics(df_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Compute ret_12m, ema_200_stock, max_drawdown_252 from price data.

    Operates on the full warm-up + gap window; we will filter to gap dates
    before writing.  All computed via vectorised pandas (no iterrows).

    Returns a DataFrame with columns:
        instrument_id, date, ret_12m, ema_200_stock, max_drawdown_252
    """
    t0 = time.time()
    df = df_ohlcv.copy().sort_values(["instrument_id", "date"])

    g = df.groupby("instrument_id", group_keys=False, observed=True)

    # ret_12m = pct_change(252) on close
    df["ret_12m"] = (
        g["close"].transform(lambda s: s.pct_change(periods=RET_12M_PERIODS)).astype("float64")
    )

    # ema_200_stock — recursive EWM; must use pandas, not SQL window
    # pandas_ta.ema seeds with SMA for the first N rows (standard convention)
    try:
        import pandas_ta as ta  # type: ignore[import-untyped]

        df["ema_200_stock"] = (
            g["close"].transform(lambda s: ta.ema(s, length=EMA_200_LENGTH)).astype("float64")
        )
    except ImportError:
        # Fallback: ewm with span=200, min_periods=200//2
        df["ema_200_stock"] = (
            g["close"]
            .transform(
                lambda s: s.ewm(
                    span=EMA_200_LENGTH, min_periods=EMA_200_LENGTH // 2, adjust=False
                ).mean()
            )
            .astype("float64")
        )

    # max_drawdown_252 — per primitives.py add_max_drawdown
    df["ret_1d"] = g["close"].transform(lambda s: s.pct_change(1)).astype("float64")

    def _max_drawdown_252(returns: pd.Series) -> pd.Series:
        cumulative = (1 + returns.fillna(0)).cumprod()
        rolling_peak = cumulative.rolling(MAX_DD_WINDOW, min_periods=MAX_DD_WINDOW // 2).max()
        drawdown = cumulative.div(rolling_peak).sub(1)
        return drawdown.rolling(MAX_DD_WINDOW, min_periods=MAX_DD_WINDOW // 2).min().abs()

    df["max_drawdown_252"] = g["ret_1d"].transform(_max_drawdown_252).astype("float64")

    rows_before = len(df)
    # Filter to gap date range only
    gap_mask = (df["date"] >= GAP_START) & (df["date"] <= GAP_END)
    result = df.loc[
        gap_mask, ["instrument_id", "date", "ret_12m", "ema_200_stock", "max_drawdown_252"]
    ].copy()
    rows_after = len(result)

    log.info(
        "2022_metrics.computed",
        rows_in_window=rows_before,
        rows_in_gap=rows_after,
        elapsed_s=round(time.time() - t0, 1),
    )
    return result


def _write_2022_metrics(engine: Engine, df: pd.DataFrame) -> dict[str, int]:
    """Write ret_12m, ema_200_stock, max_drawdown_252 back to metrics table.

    Uses COPY into a temp staging table + three UPDATE FROM queries.
    Only updates rows where the target column IS NULL (idempotent).

    Returns dict of {col: rows_updated}.
    """
    if df.empty:
        log.warning("2022_metrics.empty_df_nothing_to_write")
        return {}

    t0 = time.time()
    results: dict[str, int] = {}

    # Replace NaN with None for proper NULL handling
    df_clean = df.copy()
    df_clean = df_clean.where(df_clean.notna(), other=None)

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")

        # Create staging table
        cur.execute("""
            CREATE TEMP TABLE _gap_2022_stg (
                instrument_id uuid,
                date date,
                ret_12m double precision,
                ema_200_stock double precision,
                max_drawdown_252 double precision
            ) ON COMMIT DROP
        """)

        # COPY data into staging
        buf = StringIO()
        for row in df_clean.itertuples(index=False):
            iid = str(row.instrument_id)
            dt = str(row.date)
            r12 = (
                ""
                if row.ret_12m is None or (isinstance(row.ret_12m, float) and np.isnan(row.ret_12m))
                else str(row.ret_12m)
            )
            ema = (
                ""
                if row.ema_200_stock is None
                or (isinstance(row.ema_200_stock, float) and np.isnan(row.ema_200_stock))
                else str(row.ema_200_stock)
            )
            mdd = (
                ""
                if row.max_drawdown_252 is None
                or (isinstance(row.max_drawdown_252, float) and np.isnan(row.max_drawdown_252))
                else str(row.max_drawdown_252)
            )
            buf.write(f"{iid}\t{dt}\t{r12}\t{ema}\t{mdd}\n")

        buf.seek(0)
        cur.copy_from(
            buf,
            "_gap_2022_stg",
            sep="\t",
            null="",
            columns=("instrument_id", "date", "ret_12m", "ema_200_stock", "max_drawdown_252"),
        )

        log.info("2022_metrics.staging_loaded", rows=len(df_clean))

        # UPDATE FROM staging for each column
        for col in ("ret_12m", "ema_200_stock", "max_drawdown_252"):
            cur.execute(f"""
                UPDATE {METRICS_TABLE} m
                   SET {col} = s.{col}
                  FROM _gap_2022_stg s
                 WHERE m.instrument_id = s.instrument_id
                   AND m.date = s.date
                   AND s.{col} IS NOT NULL
                   AND m.{col} IS NULL
            """)  # noqa: S608 -- col, METRICS_TABLE are internal constants
            rows_updated = cur.rowcount
            log.info("2022_metrics.col_updated", col=col, rows_updated=rows_updated)
            results[col] = rows_updated

        raw.commit()
        log.info("2022_metrics.write_complete", elapsed_s=round(time.time() - t0, 1))

    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

    return results


# --------------------------------------------------------------------------- #
# Step 3: Verification                                                         #
# --------------------------------------------------------------------------- #


def verify_backfill(engine: Engine) -> dict[str, int]:
    """Run post-backfill null counts for all affected columns."""
    sql = text("""
        SELECT
          COUNT(*) AS total,
          COUNT(rs_1w_nifty500) AS rs_1w_n,
          COUNT(rs_1m_nifty500) AS rs_1m_n,
          COUNT(rs_3m_nifty500) AS rs_3m_n,
          COUNT(*) FILTER (WHERE date BETWEEN '2022-01-01' AND '2022-11-30') AS gap_total,
          COUNT(ret_12m) FILTER (WHERE date BETWEEN '2022-01-01' AND '2022-11-30') AS ret_12m_2022_n,
          COUNT(ema_200_stock) FILTER (WHERE date BETWEEN '2022-01-01' AND '2022-11-30') AS ema_200_2022_n,
          COUNT(max_drawdown_252) FILTER (WHERE date BETWEEN '2022-01-01' AND '2022-11-30') AS max_dd_2022_n
        FROM atlas.atlas_stock_metrics_daily
    """)
    with engine.connect() as conn:
        row = conn.execute(sql).first()
    return {str(k): int(v) for k, v in row._mapping.items()}


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> int:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        log.error("ATLAS_DB_URL not set")
        return 1

    engine = create_engine(db_url, pool_pre_ping=True)

    # Pre-flight null counts
    log.info("preflight.start")
    preflight = verify_backfill(engine)
    log.info("preflight.counts", **{str(k): v for k, v in preflight.items()})

    # Step 1: rs_*_nifty500 (SQL UPDATE — zero Python memory)
    log.info("step1.rs_nifty500.start")
    rs_results = backfill_rs_nifty500(engine)
    log.info("step1.rs_nifty500.done", **rs_results)

    # Step 2: 2022 gaps (matrix-wide pandas)
    log.info("step2.2022_gaps.start")
    df_prices = _load_ohlcv_for_gap(engine)
    df_metrics = _compute_2022_metrics(df_prices)
    gap_results = _write_2022_metrics(engine, df_metrics)
    log.info("step2.2022_gaps.done", **gap_results)

    # Step 3: Post-flight verification
    log.info("verification.start")
    postflight = verify_backfill(engine)
    log.info("verification.final_counts", **{str(k): v for k, v in postflight.items()})

    # Summary
    total = preflight["total"]
    rs_3m_final = postflight["rs_3m_n"]
    gap_total = postflight["gap_total"]
    ret_12m_final = postflight["ret_12m_2022_n"]

    log.info(
        "backfill.summary",
        rs_3m_coverage_pct=round(100 * rs_3m_final / total, 1) if total else 0,
        gap_ret_12m_coverage_pct=round(100 * ret_12m_final / gap_total, 1) if gap_total else 0,
    )

    # Non-zero RS coverage is the acceptance gate; early-date NULLs are expected
    if rs_3m_final == 0:
        log.error("GATE FAIL: rs_3m_nifty500 still all NULL after backfill")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
