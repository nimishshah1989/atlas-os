"""Index metrics pipeline (M3 Phase A).

Per ``docs/00_METHODOLOGY_LOCK.md`` §9 and ``docs/02_DATABASE_SCHEMA.md`` §3.3.

Computes per-(index_code, date) metrics across the 75 NSE indices in the
curated universe (135 codes are available in ``public.de_index_prices``;
this module computes for every code present and lets the universe layer
filter which rows persist downstream).

Indices receive returns, RS-vs-Nifty500, EMA momentum, and three volatility
measures. They do **not** receive state classification (methodology §9):
indices are not tradable, so risk/momentum/volume states are not applied.

Pipeline shape mirrors :mod:`atlas.compute.stocks` — load all index prices
once, sort by ``(index_code, date)``, run primitives with
``group_col="index_code"``, merge Nifty 500 returns/EMAs onto each row to
build the RS columns, then bulk-upsert. No Python row loops.
"""

from __future__ import annotations

import time
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.primitives import (
    add_emas,
    add_realized_vol,
    add_returns,
)
from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()


NIFTY500_CODE = "NIFTY 500"
"""Index code used as the RS denominator. Must match
``public.de_index_prices.index_code`` exactly (verified via
``atlas/preflight.py`` benchmark check)."""

INDIA_VIX_CODE = "INDIA VIX"
"""Reference code for India VIX series. The schema has no VIX-special
columns (per docs/02_DATABASE_SCHEMA.md §3.3 — ``realized_vol_5d`` and
``vol_252_median`` are computed for *every* index, since the regime
classifier reads them off the ``NIFTY 500`` row)."""

# Methodology §9: 6 return windows, no skip-month variant for indices.
INDEX_WINDOWS: dict[str, int] = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

# RS-vs-Nifty500 windows per docs/02_DATABASE_SCHEMA.md §3.3 (3 windows only).
RS_WINDOWS: tuple[str, ...] = ("1w", "1m", "3m")


METRICS_COLUMNS: tuple[str, ...] = (
    "index_code",
    "date",
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "rs_1w_nifty500",
    "rs_1m_nifty500",
    "rs_3m_nifty500",
    "ema_10_index",
    "ema_20_index",
    "ema_10_ratio_nifty500",
    "ema_20_ratio_nifty500",
    "realized_vol_63",
    "realized_vol_5d",
    "vol_252_median",
    "compute_run_id",
)


# --------------------------------------------------------------------------- #
# Loaders                                                                     #
# --------------------------------------------------------------------------- #


def load_index_prices(
    engine: Engine,
    start_date: date,
    end_date: date,
    lookback_days: int = 900,
) -> pd.DataFrame:
    """Load all index OHLC rows in ``[start_date - lookback, end_date]``.

    The ``lookback_days`` buffer is calendar days (not trading days) and
    feeds rolling-window warm-up for 252-day metrics. 900 calendar days
    ≈ 620 trading days, matching the pattern in :mod:`atlas.compute.stocks`.

    Returns a DataFrame with columns ``index_code, date, open, high, low,
    close`` sorted by ``(index_code, date)``. Rows where ``close`` is
    NULL are dropped — JIP's ``de_index_prices`` occasionally has them
    on partial days and they corrupt rolling windows.
    """
    load_start = start_date - timedelta(days=lookback_days)
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT index_code, date, open, high, low, close
            FROM public.de_index_prices
            WHERE date BETWEEN %(start)s AND %(end)s
              AND close IS NOT NULL
            ORDER BY index_code, date
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )

    if df.empty:
        log.warning(
            "index_prices_empty",
            start=str(load_start),
            end=str(end_date),
        )
        return df

    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info(
        "index_prices_loaded",
        rows=len(df),
        codes=df["index_code"].nunique(),
        load_start=str(load_start),
        end=str(end_date),
    )
    return df


# --------------------------------------------------------------------------- #
# Pure computation                                                            #
# --------------------------------------------------------------------------- #


def _add_vol_252_median(
    df: pd.DataFrame,
    *,
    group_col: str = "index_code",
    return_col: str = "ret_1d",
    window: int = 252,
    annualization_factor: int = 252,
    out_col: str = "vol_252_median",
) -> pd.DataFrame:
    """Rolling 252-day median of annualised daily-vol equivalent.

    Per the dislocation override (methodology §11 / schema §3.3 commentary):
    ``vol_252_median`` is the trailing-year median of |ret_1d| * sqrt(252).
    The regime classifier compares ``realized_vol_5d`` against this median to
    decide whether vol is anomalously elevated.
    """
    out = df.copy().sort_values([group_col, "date"])
    daily_vol = out[return_col].abs() * np.sqrt(annualization_factor)
    out[out_col] = (
        daily_vol.groupby(out[group_col], group_keys=False)
        .transform(lambda s: s.rolling(window, min_periods=window // 2).median())
        .astype("float64")
    )
    return out


def _merge_nifty500_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Append ``_nifty500_ret_<w>`` columns by date for the RS denominators.

    Pivots Nifty500 rows out, joins on ``date``. Rows whose date has no
    Nifty500 print get NaN — RS will follow as NaN automatically.
    """
    nifty = df.loc[df["index_code"] == NIFTY500_CODE, ["date"]].copy()
    if nifty.empty:
        log.warning(
            "nifty500_missing_in_input",
            note="rs_*_nifty500 columns will be all-NaN",
        )
        out = df.copy()
        for w in RS_WINDOWS:
            out[f"_nifty500_ret_{w}"] = np.nan
        out["_nifty500_ema_10"] = np.nan
        out["_nifty500_ema_20"] = np.nan
        return out

    cols = (
        ["date"]
        + [f"ret_{w}" for w in RS_WINDOWS]
        + [
            "ema_10_index",
            "ema_20_index",
        ]
    )
    nifty_subset = df.loc[df["index_code"] == NIFTY500_CODE, cols].rename(
        columns={
            **{f"ret_{w}": f"_nifty500_ret_{w}" for w in RS_WINDOWS},
            "ema_10_index": "_nifty500_ema_10",
            "ema_20_index": "_nifty500_ema_20",
        }
    )
    return df.merge(nifty_subset, on="date", how="left")


def compute_index_metrics(df_prices: pd.DataFrame) -> pd.DataFrame:
    """Run the full index pipeline on a price frame.

    Pure function: takes loaded prices, returns a DataFrame with all the
    columns in :data:`METRICS_COLUMNS` minus ``compute_run_id`` (the
    orchestrator stamps that). No DB I/O.

    Empty input returns an empty frame with the expected columns so the
    downstream upsert path never crashes on zero rows.
    """
    expected_cols = [c for c in METRICS_COLUMNS if c != "compute_run_id"]
    if df_prices.empty:
        return pd.DataFrame(columns=expected_cols)

    df = df_prices.copy().sort_values(["index_code", "date"]).reset_index(drop=True)

    # Phase 1 — per-index primitives. group_col MUST be "index_code".
    df = add_returns(
        df,
        group_col="index_code",
        price_col="close",
        windows=INDEX_WINDOWS,
    )
    df = add_emas(
        df,
        group_col="index_code",
        price_col="close",
        lengths=(10, 20),
        suffix="index",
    )
    df = add_realized_vol(
        df,
        group_col="index_code",
        return_col="ret_1d",
        window=63,
        out_col="realized_vol_63",
    )
    df = add_realized_vol(
        df,
        group_col="index_code",
        return_col="ret_1d",
        window=5,
        out_col="realized_vol_5d",
    )
    df = _add_vol_252_median(df, group_col="index_code", return_col="ret_1d")

    # Phase 2 — Nifty500 merge + RS columns. RS = index_return / nifty500_return
    # per the prompt's methodology brief; when the denominator is 0 or NaN, RS
    # is NaN (no division-by-zero blow-up; np.divide handles it).
    df = _merge_nifty500_returns(df)

    # Price-relative RS: (1 + index_ret) / (1 + nifty500_ret) - 1.
    # Simple ratio ret_i/ret_b inverts sign when the benchmark return is
    # negative (a sector up 30% when Nifty500 is down 1% would get a large
    # negative RS with simple ratio). Price-relative formula is sign-consistent.
    for w in RS_WINDOWS:
        ret_col = f"ret_{w}"
        denom = df[f"_nifty500_ret_{w}"].astype("float64")
        bench_price_rel = 1.0 + denom
        with np.errstate(divide="ignore", invalid="ignore"):
            rs = np.where(
                denom.notna() & (bench_price_rel.abs() > 1e-9),
                (1.0 + df[ret_col].astype("float64")) / bench_price_rel - 1.0,
                np.nan,
            )
        df[f"rs_{w}_nifty500"] = rs.astype("float64")

    # EMA ratios vs Nifty500 EMAs. Guard against zero/NaN denominator (EMA
    # warm-up rows can be NaN; a zero-close index would produce inf without this).
    for n in (10, 20):
        idx_col = f"ema_{n}_index"
        bench_col = f"_nifty500_ema_{n}"
        denom = df[bench_col].replace(0, np.nan)
        df[f"ema_{n}_ratio_nifty500"] = df[idx_col] / denom

    # Drop scratch columns; keep schema-aligned ones.
    df = df.drop(columns=[c for c in df.columns if c.startswith("_nifty500_")])

    # Final guard: any remaining inf (e.g. from edge-case zero EMA during early
    # history) becomes NaN so NUMERIC columns don't overflow on write.
    df = df.replace([np.inf, -np.inf], np.nan)

    # Reindex to the schema column order (minus compute_run_id, which the
    # orchestrator stamps just before write).
    return df.reindex(columns=expected_cols)


# --------------------------------------------------------------------------- #
# Orchestrators                                                               #
# --------------------------------------------------------------------------- #


def _write_metrics(
    engine: Engine,
    df: pd.DataFrame,
    run_id: uuid.UUID,
) -> int:
    """Bulk-upsert the metrics frame. Stamps ``compute_run_id`` in place."""
    if df.empty:
        return 0
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(METRICS_COLUMNS))
    return bulk_upsert(
        engine,
        table="atlas.atlas_index_metrics_daily",
        columns=list(METRICS_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["index_code", "date"],
    )


def backfill_index_metrics(
    engine: Engine | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    """Full historical backfill for all indices in ``de_index_prices``.

    Default range: ``Config.HISTORICAL_START_DATE`` → today.

    Returns the number of rows written (post-warm-up filter).
    """
    eng = engine or get_engine()
    run_id = uuid.uuid4()
    started = time.time()

    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()

    log.info(
        "index_backfill_start",
        run_id=str(run_id),
        start=str(start),
        end=str(end),
    )

    prices = load_index_prices(eng, start_date=start, end_date=end)
    metrics = compute_index_metrics(prices)

    # Drop warm-up rows (those before start_date) before writing — they were
    # only loaded to feed rolling windows.
    metrics = metrics.loc[metrics["date"] >= start].copy()

    rows = _write_metrics(eng, metrics, run_id)
    log.info(
        "index_backfill_complete",
        run_id=str(run_id),
        rows_written=rows,
        duration_sec=round(time.time() - started, 1),
    )
    return rows


def run_daily_index_metrics(engine: Engine | None = None) -> int:
    """Incremental run for the last 5 trading days.

    Loads ``[today - 5cal_days - 900cal_days, today]``, computes the full
    pipeline, but persists only rows for the most recent 5-trading-day
    window. The 900-day buffer keeps 252d rolling windows hot.
    """
    eng = engine or get_engine()
    today = date.today()
    # 5 trading days ≈ 7 calendar days; round up to 10 to absorb holidays.
    window_start = today - timedelta(days=10)

    log.info(
        "index_daily_start",
        window_start=str(window_start),
        end=str(today),
    )

    prices = load_index_prices(eng, start_date=window_start, end_date=today)
    metrics = compute_index_metrics(prices)
    metrics = metrics.loc[metrics["date"] >= window_start].copy()

    run_id = uuid.uuid4()
    rows = _write_metrics(eng, metrics, run_id)
    log.info("index_daily_complete", run_id=str(run_id), rows_written=rows)
    return rows


__all__ = [
    "INDEX_WINDOWS",
    "INDIA_VIX_CODE",
    "METRICS_COLUMNS",
    "NIFTY500_CODE",
    "RS_WINDOWS",
    "backfill_index_metrics",
    "compute_index_metrics",
    "load_index_prices",
    "run_daily_index_metrics",
]
