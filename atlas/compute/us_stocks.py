"""S&P 500 stock metric + state pipeline for us_atlas schema.

Mirrors atlas.compute.stocks (India) with three US-specific adaptations:
1. Four global benchmarks (ACWI, VT, EEM, GOLD) each × 5 timeframes = 20 RS cells.
2. Liquidity gate uses avg_volume_20 (shares) not INR-denominated traded value.
3. VT pctile is primary for classify_rs_state (VT = Total World; VT pctile
   measures how a stock ranks within the S&P 500 vs a global yardstick).
"""

# allow-large: 4-benchmark RS × 5 timeframes × percentile + state machinery

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.benchmarks import (
    materialize_benchmark_cache,
    persist_benchmark_cache,
)
from atlas.compute.gates import (
    add_history_gate,
    add_weinstein_gate,
)
from atlas.compute.primitives import (
    add_emas,
    add_extension_pct,
    add_max_drawdown,
    add_realized_vol,
    add_returns,
    add_rs_momentum,
    add_volume_primitives,
)
from atlas.compute.states import (
    apply_below_trend_conjunction,
    apply_suspension_overrides,
    classify_momentum_state,
    classify_risk_state,
    classify_rs_state,
    classify_volume_state,
)
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

_SCHEMA = "us_atlas"

# 4 global benchmarks used for RS (matches atlas_benchmark_master seeds in migration 055)
BENCHMARKS = ("ACWI", "VT", "EEM", "GOLD")
_RS_WINDOWS = ("1w", "1m", "3m", "6m", "12m")

# VT is the primary benchmark for RS state classification (Total World = universe anchor)
_PRIMARY_BENCHMARK = "VT"

METRICS_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    # Returns
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "ret_12m_1m",
    # EMAs + momentum ratios
    "ema_10_stock",
    "ema_20_stock",
    "ema_50_stock",
    "ema_200_stock",
    "ema_10_ratio",
    "ema_20_ratio",
    # Risk primitives
    "realized_vol_63",
    "vol_ratio_63",
    "max_drawdown_252",
    "extension_pct",
    "atr_21",
    "above_30w_ma",
    # Volume
    "avg_volume_20",
    "avg_volume_252",
    "volume_expansion",
    "effort_ratio_63",
    # RS vs ACWI
    "rs_1w_acwi",
    "rs_1m_acwi",
    "rs_3m_acwi",
    "rs_6m_acwi",
    "rs_12m_acwi",
    "rs_pctile_1w_acwi",
    "rs_pctile_1m_acwi",
    "rs_pctile_3m_acwi",
    "rs_pctile_6m_acwi",
    "rs_pctile_12m_acwi",
    # RS vs VT
    "rs_1w_vt",
    "rs_1m_vt",
    "rs_3m_vt",
    "rs_6m_vt",
    "rs_12m_vt",
    "rs_pctile_1w_vt",
    "rs_pctile_1m_vt",
    "rs_pctile_3m_vt",
    "rs_pctile_6m_vt",
    "rs_pctile_12m_vt",
    # RS vs EEM
    "rs_1w_eem",
    "rs_1m_eem",
    "rs_3m_eem",
    "rs_6m_eem",
    "rs_12m_eem",
    "rs_pctile_1w_eem",
    "rs_pctile_1m_eem",
    "rs_pctile_3m_eem",
    "rs_pctile_6m_eem",
    "rs_pctile_12m_eem",
    # RS vs GOLD
    "rs_1w_gold",
    "rs_1m_gold",
    "rs_3m_gold",
    "rs_6m_gold",
    "rs_12m_gold",
    "rs_pctile_1w_gold",
    "rs_pctile_1m_gold",
    "rs_pctile_3m_gold",
    "rs_pctile_6m_gold",
    "rs_pctile_12m_gold",
    # Consensus
    "rs_consensus_bullish",
    "rs_consensus_bearish",
    # Audit
    "compute_run_id",
)

STATES_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "rs_state",
    "momentum_state",
    "risk_state",
    "volume_state",
    "history_gate_pass",
    "liquidity_gate_pass",
    "weinstein_gate_pass",
    "stage1_base_qualifies",
    "above_30w_ma",
    "gics_sector",
    "tier",
    "compute_run_id",
)

# Normalized RS states — 4 benchmarks × 5 windows = 20 rows per stock per day
RS_STATES_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "benchmark",
    "timeframe",
    "rs_value",
    "rs_pctile",
    "rs_state",
)


def _load_universe(engine: Engine) -> pd.DataFrame:
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            "SELECT ticker, tier, gics_sector "
            "FROM us_atlas.atlas_universe_stocks WHERE is_active = TRUE",
            conn,
        )


def _load_ohlcv(
    engine: Engine,
    *,
    tickers: list[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT ticker, date, open, high, low, close, volume
            FROM us_atlas.stock_ohlcv
            WHERE ticker = ANY(%(tickers)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY ticker, date
            """,
            conn,
            params={"tickers": tickers, "start": start, "end": end},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _build_benchmark_wide(benchmark_cache: pd.DataFrame) -> pd.DataFrame:
    """Pivot benchmark_cache into one wide row per date.

    Returns columns: date, ret_{w}_{bench}, ema_10_{bench}, ema_20_{bench},
    realized_vol_63_{bench} for each benchmark in BENCHMARKS.
    """
    parts: list[pd.DataFrame] = []
    for bench in BENCHMARKS:
        label = bench.lower()
        sub = benchmark_cache.loc[benchmark_cache["benchmark_code"] == bench].copy()
        if sub.empty:
            continue
        rename: dict[str, str] = {}
        for w in _RS_WINDOWS:
            rename[f"ret_{w}"] = f"ret_{w}_{label}"
        rename["ret_1d"] = f"ret_1d_{label}"
        rename["ema_10_benchmark"] = f"ema_10_{label}"
        rename["ema_20_benchmark"] = f"ema_20_{label}"
        rename["realized_vol_63"] = f"realized_vol_63_{label}"
        sub = sub.rename(columns=rename)
        keep = ["date"] + [c for c in sub.columns if c.endswith(f"_{label}")]
        parts.append(sub[keep].set_index("date"))

    if not parts:
        return pd.DataFrame()
    wide = pd.concat(parts, axis=1).reset_index()
    return wide


def _compute_rs(
    df: pd.DataFrame,
    benchmark_wide: pd.DataFrame,
    *,
    overweight_pctile: float,
    underweight_pctile: float,
) -> pd.DataFrame:
    """Compute RS vs each of the 4 benchmarks × 5 windows, then percentile ranks.

    RS = stock_ret_{w} - bench_ret_{w} (excess return, same convention as India).
    Percentile is within-universe ranking per date per (benchmark, timeframe).
    """
    out = df.merge(benchmark_wide, on="date", how="left")

    for bench in BENCHMARKS:
        label = bench.lower()
        for w in _RS_WINDOWS:
            stock_col = f"ret_{w}"
            bench_col = f"ret_{w}_{label}"
            rs_col = f"rs_{w}_{label}"
            pctile_col = f"rs_pctile_{w}_{label}"
            if stock_col in out.columns and bench_col in out.columns:
                out[rs_col] = out[stock_col] - out[bench_col]
            else:
                out[rs_col] = pd.NA
            # Percentile: rank within date (min_count guard: at least 10 stocks)
            if rs_col in out.columns:
                grp = out.groupby("date", observed=True)[rs_col]
                ranks = grp.rank(method="min", na_option="keep")
                counts = grp.transform("count")
                out[pctile_col] = (ranks / counts).where(counts >= 10)
            else:
                out[pctile_col] = pd.NA

    # Consensus score: count of 20 (bench × window) cells that are bullish/bearish
    bullish_cells: list[pd.Series] = []
    bearish_cells: list[pd.Series] = []
    for bench in BENCHMARKS:
        label = bench.lower()
        for w in _RS_WINDOWS:
            pctile_col = f"rs_pctile_{w}_{label}"
            if pctile_col in out.columns:
                bullish_cells.append((out[pctile_col] >= overweight_pctile).astype(int))
                bearish_cells.append((out[pctile_col] <= underweight_pctile).astype(int))

    if bullish_cells:
        out["rs_consensus_bullish"] = sum(bullish_cells)
        out["rs_consensus_bearish"] = sum(bearish_cells)
    else:
        out["rs_consensus_bullish"] = pd.NA
        out["rs_consensus_bearish"] = pd.NA

    return out


def _classify_states(df: pd.DataFrame, thresholds: Mapping[str, Decimal]) -> pd.DataFrame:
    """Apply full India state stack: RS → momentum → risk → volume → overrides."""
    out = add_history_gate(df, group_col="ticker")
    out = add_weinstein_gate(out, group_col="ticker", price_col="close")

    vol_floor = float(thresholds.get("liquidity_gate_min_avg_vol", Decimal("500000")))
    out["liquidity_gate_pass"] = out["avg_volume_20"].fillna(0) >= vol_floor

    out["stage1_base_qualifies"] = False

    # VT pctile as primary RS universe ranking (mirrors NIFTY 500 pctile in India)
    out["rs_pctile_1w"] = out.get("rs_pctile_1w_vt", pd.NA)
    out["rs_pctile_1m"] = out.get("rs_pctile_1m_vt", pd.NA)
    out["rs_pctile_3m"] = out.get("rs_pctile_3m_vt", pd.NA)
    out = classify_rs_state(out, thresholds)
    out = out.drop(columns=["rs_pctile_1w", "rs_pctile_1m", "rs_pctile_3m"], errors="ignore")

    out = classify_momentum_state(out, thresholds)
    out = classify_risk_state(out, thresholds)
    out = classify_volume_state(out, thresholds)
    out = apply_below_trend_conjunction(out)
    out = apply_suspension_overrides(out, market_dislocation=None)
    return out


def _to_rs_states_long(
    df: pd.DataFrame,
    *,
    overweight_pctile: float,
    underweight_pctile: float,
) -> list[tuple]:
    """Explode wide RS columns into 20 rows per (ticker, date) for atlas_stock_rs_states."""
    rows: list[tuple] = []
    for _, row in df.iterrows():
        ticker = row["ticker"]
        dt = row["date"]
        for bench in BENCHMARKS:
            label = bench.lower()
            for w in _RS_WINDOWS:
                rs_val = row.get(f"rs_{w}_{label}", None)
                pctile = row.get(f"rs_pctile_{w}_{label}", None)
                if pctile is not None and not (isinstance(pctile, float) and np.isnan(pctile)):
                    p = float(pctile)
                    rs_state = "Neutral"
                    if p >= overweight_pctile:
                        rs_state = "Overweight"
                    elif p <= underweight_pctile:
                        rs_state = "Underweight"
                else:
                    rs_state = None
                rows.append((ticker, dt, label, w, rs_val, pctile, rs_state))
    return rows


def _write_metrics(engine: Engine, df: pd.DataFrame, run_id: uuid.UUID) -> int:
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(METRICS_COLUMNS))
    return bulk_upsert(
        engine,
        table="us_atlas.atlas_stock_metrics_daily",
        columns=list(METRICS_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["ticker", "date"],
    )


def _write_states(engine: Engine, df: pd.DataFrame, run_id: uuid.UUID) -> int:
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(STATES_COLUMNS))
    required = ["rs_state", "momentum_state", "risk_state", "history_gate_pass"]
    payload = payload.dropna(subset=required)
    return bulk_upsert(
        engine,
        table="us_atlas.atlas_stock_states_daily",
        columns=list(STATES_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["ticker", "date"],
    )


def _write_rs_states(engine: Engine, rows: list[tuple]) -> int:
    if not rows:
        return 0
    return bulk_upsert(
        engine,
        table="us_atlas.atlas_stock_rs_states",
        columns=list(RS_STATES_COLUMNS),
        rows=rows,
        pk_columns=["ticker", "date", "benchmark", "timeframe"],
    )


def run_us_stocks_backfill(
    *,
    start: date | None = None,
    end: date | None = None,
    engine: Engine | None = None,
) -> dict[str, object]:
    eng = engine or get_engine()
    run_id = uuid.uuid4()
    started = time.time()
    start = start or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end or date.today()

    universe = _load_universe(eng)
    log.info("universe_loaded", rows=len(universe), schema=_SCHEMA)
    if universe.empty:
        log.warning("empty_universe", schema=_SCHEMA)
        return {"run_id": str(run_id), "metric_rows": 0, "state_rows": 0, "rs_state_rows": 0}

    thresholds = load_thresholds(schema=_SCHEMA, engine=eng)
    overweight_pctile = float(thresholds.get("rs_overweight_pctile", Decimal("0.70")))
    underweight_pctile = float(thresholds.get("rs_underweight_pctile", Decimal("0.30")))

    benchmark_cache = materialize_benchmark_cache(eng, start=start, end=end, schema=_SCHEMA)
    persist_benchmark_cache(eng, benchmark_cache, schema=_SCHEMA)
    log.info("benchmark_cache_ready", benchmarks=benchmark_cache["benchmark_code"].nunique())

    benchmark_wide = _build_benchmark_wide(benchmark_cache)

    # VT EMAs for add_rs_momentum (stock EMA10/20 ratio vs VT EMA10/20 ratio)
    vt_emas = benchmark_cache.loc[
        benchmark_cache["benchmark_code"] == _PRIMARY_BENCHMARK,
        [
            "date",
            "ema_10_benchmark",
            "ema_20_benchmark",
            "realized_vol_63",
        ],
    ].rename(
        columns={
            "ema_10_benchmark": "ema_10_benchmark",
            "ema_20_benchmark": "ema_20_benchmark",
            "realized_vol_63": "realized_vol_63_benchmark",
        }
    )

    ohlcv = _load_ohlcv(eng, tickers=universe["ticker"].tolist(), start=start, end=end)
    log.info("ohlcv_loaded", rows=len(ohlcv))
    if ohlcv.empty:
        log.warning("no_ohlcv", schema=_SCHEMA)
        return {"run_id": str(run_id), "metric_rows": 0, "state_rows": 0, "rs_state_rows": 0}

    # --- Primitives ---
    df = ohlcv.merge(universe[["ticker", "tier", "gics_sector"]], on="ticker", how="left")
    df = add_returns(df, group_col="ticker", price_col="close")
    df = add_emas(
        df, group_col="ticker", price_col="close", lengths=(10, 20, 50, 200), suffix="stock"
    )
    df = add_realized_vol(df, group_col="ticker", return_col="ret_1d", window=63)
    df = add_max_drawdown(df, group_col="ticker", return_col="ret_1d", window=252)
    df = add_extension_pct(df, ema_col="ema_200_stock")
    df = add_volume_primitives(df, group_col="ticker", event_dates=None)

    # Gates (weinstein + history added in _classify_states; above_30w_ma produced here)
    df = add_weinstein_gate(df, group_col="ticker", price_col="close")

    # Vol ratio vs VT (stock vol / VT vol)
    df = df.merge(vt_emas, on="date", how="left")
    df["vol_ratio_63"] = df["realized_vol_63"] / df["realized_vol_63_benchmark"].replace(0, pd.NA)

    # Momentum ratios (EMA10/EMA20 stock vs EMA10/EMA20 VT)
    df = add_rs_momentum(df, group_col="ticker")

    # drawdown_ratio_252 — negate max_drawdown (which is stored as negative)
    df["max_drawdown_252"] = -df["max_drawdown_252"] if "max_drawdown_252" in df.columns else pd.NA

    # ret_12m_1m: not computed by add_returns default WINDOWS — leave as NA
    df["ret_12m_1m"] = pd.NA
    # atr_21: not yet implemented — leave as NA
    df["atr_21"] = pd.NA

    # --- RS vs 4 benchmarks ---
    df = _compute_rs(
        df,
        benchmark_wide,
        overweight_pctile=overweight_pctile,
        underweight_pctile=underweight_pctile,
    )

    # --- State classification ---
    df = _classify_states(df, thresholds)

    # --- Write ---
    metric_rows = _write_metrics(eng, df, run_id)
    log.info("metrics_written", rows=metric_rows)

    state_rows = _write_states(eng, df, run_id)
    log.info("states_written", rows=state_rows)

    rs_long = _to_rs_states_long(
        df.loc[df["date"] == df["date"].max()],  # latest date only (backfill writes daily slices)
        overweight_pctile=overweight_pctile,
        underweight_pctile=underweight_pctile,
    )
    rs_state_rows = _write_rs_states(eng, rs_long)
    log.info("rs_states_written", rows=rs_state_rows)

    elapsed = round(time.time() - started, 1)
    log.info(
        "us_stocks_backfill_complete",
        run_id=str(run_id),
        metric_rows=metric_rows,
        state_rows=state_rows,
        rs_state_rows=rs_state_rows,
        elapsed_sec=elapsed,
    )
    return {
        "run_id": str(run_id),
        "metric_rows": metric_rows,
        "state_rows": state_rows,
        "rs_state_rows": rs_state_rows,
        "elapsed_sec": elapsed,
    }


def run_us_stocks_daily(
    target_date: date,
    *,
    lookback_days: int = 400,
    engine: Engine | None = None,
) -> dict[str, object]:
    return run_us_stocks_backfill(
        start=target_date - timedelta(days=lookback_days),
        end=target_date,
        engine=engine,
    )


__all__ = [
    "METRICS_COLUMNS",
    "RS_STATES_COLUMNS",
    "STATES_COLUMNS",
    "run_us_stocks_backfill",
    "run_us_stocks_daily",
]
