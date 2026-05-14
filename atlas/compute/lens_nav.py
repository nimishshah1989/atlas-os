"""Lens 1 — NAV Behavior (M4 Phase A).

Per ``docs/00_METHODOLOGY_LOCK.md`` §12.1 and
``docs/milestones/ATLAS_M4_MUTUAL_FUND_LENSES.md`` §4.

Treats each fund's NAV series as a price series. Computes:
- Returns at 1M/3M/6M/12M windows (longer than stocks' 1W/1M/3M)
- RS vs category benchmark at 1M/3M/6M
- Within-category percentile rank at 1M/3M/6M
- Realised vol (63-day annualised)
- Drawdown ratio vs benchmark (252-day rolling)
- nav_state: 6-state classification (Leader NAV → Laggard NAV)

Writes to ``atlas.atlas_fund_metrics_daily`` (raw metrics + nav_state).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

# 900 calendar-day lookback for rolling windows (≈620 trading days — enough
# for 252-day drawdown + warm-up buffer).
NAV_LOOKBACK_DAYS = 900

# Minimum trading days required to compute a valid row.
MIN_HISTORY_DAYS = 252

# Fund return windows per methodology §12.1 (longer than stock 1W/1M/3M).
FUND_WINDOWS: dict[str, int] = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

METRICS_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "nav_date",
    "nav",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "rs_1m_category",
    "rs_3m_category",
    "rs_6m_category",
    "rs_pctile_1m",
    "rs_pctile_3m",
    "rs_pctile_6m",
    "realized_vol_63",
    "drawdown_ratio_252",
    "nav_state",
    "compute_run_id",
)


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #


def load_fund_universe(engine: Engine) -> pd.DataFrame:
    """Load active funds with their category and benchmark mapping."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT
                f.mstar_id,
                f.category_name,
                f.benchmark_code,
                bm.source_table,
                bm.source_identifier
            FROM atlas.atlas_universe_funds f
            JOIN atlas.atlas_benchmark_master bm
                ON bm.benchmark_code = f.benchmark_code
            WHERE f.effective_to IS NULL
            ORDER BY f.mstar_id
            """,
            conn,
        )


def load_nav_history(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load NAV history for all funds in ``[start - lookback, end]``."""
    load_start = start_date - timedelta(days=NAV_LOOKBACK_DAYS)
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT mstar_id, nav_date AS date, nav AS close
            FROM public.de_mf_nav_daily
            WHERE nav_date BETWEEN %(start)s AND %(end)s
              AND nav IS NOT NULL
              AND nav > 0
            ORDER BY mstar_id, nav_date
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("nav_history_loaded", rows=len(df), funds=df["mstar_id"].nunique())
    return df


def load_benchmark_prices(
    engine: Engine,
    benchmark_codes: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load benchmark index prices for the given codes."""
    load_start = start_date - timedelta(days=NAV_LOOKBACK_DAYS)
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT index_code AS benchmark_code, date, close
            FROM public.de_index_prices
            WHERE index_code = ANY(%(codes)s)
              AND date BETWEEN %(start)s AND %(end)s
              AND close IS NOT NULL
            ORDER BY index_code, date
            """,
            conn,
            params={"codes": benchmark_codes, "start": load_start, "end": end_date},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# --------------------------------------------------------------------------- #
# Per-fund metric computation                                                  #
# --------------------------------------------------------------------------- #


def _rolling_max_drawdown(returns: pd.Series, window: int = 252) -> pd.Series:
    """Maximum drawdown over rolling window. Returns negative values (e.g. -0.15 = 15% drawdown).

    Fully vectorized via pandas rolling — no Python loop. Compounded equity
    curve ensures short-period arithmetic doesn't inflate results.
    """
    cum = (1 + returns.fillna(0)).cumprod()
    rolling_peak = cum.rolling(window, min_periods=1).max()
    drawdown = cum / rolling_peak - 1
    return drawdown.rolling(window, min_periods=1).min()


def compute_fund_nav_raw_metrics(
    nav_df: pd.DataFrame,
    bench_df: pd.DataFrame,
    fund: dict[str, Any],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Compute raw NAV-derived metrics for a single fund.

    Returns a DataFrame with METRICS_COLUMNS (minus nav_state and
    the percentile columns which are filled cross-sectionally later).
    Empty DataFrame if insufficient history.
    """
    mstar_id = fund["mstar_id"]
    fund_nav = nav_df[nav_df["mstar_id"] == mstar_id].copy()
    bench_code = fund.get("source_identifier") or fund.get("benchmark_code")
    fund_bench = bench_df[bench_df["benchmark_code"] == bench_code].copy()

    if fund_nav.empty or len(fund_nav) < MIN_HISTORY_DAYS:
        log.debug("nav_insufficient_history", mstar_id=mstar_id, rows=len(fund_nav))
        return pd.DataFrame()

    fund_nav = fund_nav.sort_values("date").set_index("date")
    fund_bench = fund_bench.sort_values("date").set_index("date")

    # Detect NAV gaps before forward-filling; methodology §3.3 forbids silent skips.
    nav_gaps = fund_nav["close"].isna().sum()
    if nav_gaps > 0:
        log.warning(
            "nav_gaps_detected_filling_forward",
            mstar_id=mstar_id,
            gap_count=int(nav_gaps),
            date_range=f"{fund_nav.index.min()} – {fund_nav.index.max()}",
        )
        fund_nav["close"] = fund_nav["close"].ffill()

    # Returns: fund NAV series
    for name, periods in FUND_WINDOWS.items():
        fund_nav[f"ret_{name}"] = fund_nav["close"].pct_change(periods=periods)

    # Daily return for vol + drawdown
    fund_nav["daily_ret"] = fund_nav["close"].pct_change()

    # Benchmark returns at same windows
    for name, periods in FUND_WINDOWS.items():
        fund_bench[f"bench_ret_{name}"] = fund_bench["close"].pct_change(periods=periods)

    # Price-relative RS: (1+fund)/(1+bench) - 1 per methodology §4
    # Keep NaN — data gaps must not become 0 (zero return silently distorts RS).
    merged = fund_nav.join(fund_bench[[f"bench_ret_{n}" for n in FUND_WINDOWS]], how="left")
    for name in ("1m", "3m", "6m"):
        f_ret = merged[f"ret_{name}"]  # keep NaN — gaps must not become 0
        b_ret = merged[f"bench_ret_{name}"]  # keep NaN — gaps must not become 0
        denom = 1 + b_ret
        denom = denom.where(denom.notna() & (denom != 0), np.nan)
        merged[f"rs_{name}_category"] = (1 + f_ret) / denom - 1
        na_count = int(merged[f"rs_{name}_category"].isna().sum())
        if na_count:
            log.debug("fund_rs_null_rows", window=name, null_rows=na_count)

    # Realised vol: 63-day annualised
    merged["realized_vol_63"] = merged["daily_ret"].rolling(63, min_periods=42).std() * np.sqrt(252)

    # Max drawdown over rolling 252-day window (stored as negative fraction)
    # e.g. -0.063 = fund drew down 6.3% peak-to-trough within the window.
    # _rolling_max_drawdown returns negative values directly (min of drawdown series).
    merged["drawdown_ratio_252"] = _rolling_max_drawdown(merged["daily_ret"])

    # Inf guard before write
    for col in merged.select_dtypes(include=[float]).columns:
        merged[col] = merged[col].replace([np.inf, -np.inf], np.nan)

    # Filter to target date range (post-warm-up)
    result = merged.loc[(merged.index >= start_date) & (merged.index <= end_date)].copy()

    if result.empty:
        return pd.DataFrame()

    result = result.reset_index().rename(columns={"date": "nav_date", "close": "nav"})
    result["mstar_id"] = mstar_id
    # Percentile + nav_state filled later cross-sectionally
    result["rs_pctile_1m"] = np.nan
    result["rs_pctile_3m"] = np.nan
    result["rs_pctile_6m"] = np.nan
    result["nav_state"] = None

    keep_cols = [
        "mstar_id",
        "nav_date",
        "nav",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "ret_12m",
        "rs_1m_category",
        "rs_3m_category",
        "rs_6m_category",
        "rs_pctile_1m",
        "rs_pctile_3m",
        "rs_pctile_6m",
        "realized_vol_63",
        "drawdown_ratio_252",
        "nav_state",
    ]
    return result[[c for c in keep_cols if c in result.columns]]


# --------------------------------------------------------------------------- #
# Cross-sectional within-category percentile ranking                           #
# --------------------------------------------------------------------------- #


def compute_within_category_percentiles(
    metrics_df: pd.DataFrame,
    fund_universe: pd.DataFrame,
) -> pd.DataFrame:
    """Percentile-rank each fund's RS within its category for each date+window.

    Per methodology §12.1: ranking is within category (e.g., Large Cap vs
    Large Cap), not across the entire fund universe.
    """
    df = metrics_df.merge(
        fund_universe[["mstar_id", "category_name"]],
        on="mstar_id",
        how="left",
    )

    for window in ("1m", "3m", "6m"):
        rs_col = f"rs_{window}_category"
        pctile_col = f"rs_pctile_{window}"
        if rs_col not in df.columns:
            continue
        df[pctile_col] = df.groupby(["nav_date", "category_name"])[rs_col].rank(
            method="average", pct=True, na_option="keep"
        )

    return df.drop(columns=["category_name"])


# --------------------------------------------------------------------------- #
# Lens 1 NAV state classifier                                                  #
# --------------------------------------------------------------------------- #


def classify_nav_state(
    metrics_df: pd.DataFrame,
    thresholds: dict[str, Any],
) -> pd.DataFrame:
    """Apply 6-state NAV classification per methodology §12.1.

    Uses 1M/3M/6M within-category percentile ranks. States ranked by
    strength (Laggard checked first, then Weak, then Leader/Strong/Emerging,
    otherwise Average).
    """
    # Thresholds stored as fractions (0.80 = 80th pctile) — do NOT divide by 100.
    top = float(thresholds.get("rs_quintile_top", 0.80))
    bot = float(thresholds.get("rs_quintile_bottom", 0.20))

    df = metrics_df.copy()
    p1 = df["rs_pctile_1m"]
    p3 = df["rs_pctile_3m"]
    p6 = df["rs_pctile_6m"]

    in_top_1 = p1 >= top
    in_top_3 = p3 >= top
    in_top_6 = p6 >= top
    in_bot_1 = p1 <= bot
    in_bot_3 = p3 <= bot
    in_bot_6 = p6 <= bot

    has_all = p1.notna() & p3.notna() & p6.notna()

    conditions = [
        has_all & in_bot_1 & in_bot_3 & in_bot_6,  # Laggard NAV
        has_all & (in_bot_1 | in_bot_3 | in_bot_6),  # Weak NAV
        has_all & in_top_1 & in_top_3 & in_top_6,  # Leader NAV
        has_all & in_top_3 & in_top_6 & ~in_top_1,  # Strong NAV
        has_all & in_top_1 & ~in_top_3 & ~in_top_6,  # Emerging NAV
    ]
    choices = ["Laggard NAV", "Weak NAV", "Leader NAV", "Strong NAV", "Emerging NAV"]

    df["nav_state"] = np.select(conditions, choices, default="Average NAV")
    # Rows with insufficient percentile data stay None
    df.loc[~has_all, "nav_state"] = None
    return df


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_lens1(
    start_date: date,
    end_date: date,
    run_id: uuid.UUID | None = None,
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute Lens 1 NAV metrics + nav_state for all funds in the date range.

    Returns a summary dict: ``{run_id, rows_written, funds_processed, errors}``.
    """
    engine = engine or get_engine()
    run_id = run_id or uuid.uuid4()
    t0 = __import__("time").time()

    if thresholds is None:
        thresholds = load_thresholds("atlas", engine)

    fund_universe = load_fund_universe(engine)
    if fund_universe.empty:
        log.warning("lens1_no_funds")
        return {"run_id": run_id, "rows_written": 0, "funds_processed": 0, "errors": []}

    log.info("lens1_start", funds=len(fund_universe), start=str(start_date), end=str(end_date))

    # Load all NAV data at once to avoid per-fund DB round trips
    nav_df = load_nav_history(engine, start_date, end_date)
    bench_codes = fund_universe["source_identifier"].dropna().unique().tolist()
    bench_df = load_benchmark_prices(engine, bench_codes, start_date, end_date)

    all_metrics: list[pd.DataFrame] = []
    errors: list[dict[str, Any]] = []
    total_funds = len(fund_universe)

    for _, fund in fund_universe.iterrows():
        try:
            fund_metrics = compute_fund_nav_raw_metrics(
                nav_df, bench_df, fund.to_dict(), start_date, end_date
            )
            if not fund_metrics.empty:
                all_metrics.append(fund_metrics)
        except Exception as exc:
            errors.append({"mstar_id": fund["mstar_id"], "error": str(exc)})
            log.error("lens1_fund_error", mstar_id=fund["mstar_id"], error=str(exc))

    error_rate = len(errors) / max(total_funds, 1)
    if error_rate > 0.10:
        raise RuntimeError(
            f"Fund lens failed for {len(errors)}/{total_funds} funds "
            f"({error_rate:.0%}). Aborting to prevent partial write. "
            f"First error: {errors[0]['error'] if errors else 'none'}"
        )
    if errors:
        log.warning("lens1_partial_errors", error_count=len(errors), total=total_funds)

    if not all_metrics:
        log.warning("lens1_no_metrics_computed")
        return {"run_id": run_id, "rows_written": 0, "funds_processed": 0, "errors": errors}

    combined = pd.concat(all_metrics, ignore_index=True)
    log.info("lens1_raw_metrics", rows=len(combined))

    # Cross-sectional within-category percentile ranking
    combined = compute_within_category_percentiles(combined, fund_universe)

    # NAV state classification
    combined = classify_nav_state(combined, thresholds)

    # Add compute_run_id
    combined["compute_run_id"] = str(run_id)

    # Write to atlas_fund_metrics_daily
    write_cols = [c for c in METRICS_COLUMNS if c in combined.columns]
    rows = df_to_pg_rows(combined[write_cols])
    rows_written = bulk_upsert(
        engine,
        "atlas.atlas_fund_metrics_daily",
        list(write_cols),
        rows,
        pk_columns=["mstar_id", "nav_date"],
    )

    elapsed = __import__("time").time() - t0
    log.info(
        "lens1_complete",
        rows_written=rows_written,
        funds=len(fund_universe),
        elapsed_s=round(elapsed, 1),
        errors=len(errors),
    )
    return {
        "run_id": run_id,
        "rows_written": rows_written,
        "funds_processed": len(fund_universe),
        "errors": errors,
    }
