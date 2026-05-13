# allow-large: unified pipeline — RS/regime/states share in-memory state; splitting adds coupling
"""Multi-universe ETF pipeline — 4-benchmark RS, full India-methodology state stack.

Supports ``global_atlas`` (30 country ETFs) and ``us_atlas`` (curated US ETFs).
Both universes are scored against ACWI, VT, EEM, and GOLD across 5 timeframes
(1w, 1m, 3m, 6m, 12m) = 20 RS cells per instrument per day.

RS states use the same textual labels as India (Leader/Strong/Average/Weak/Laggard)
derived from within-universe percentile ranks. Consensus = count of Q1/Q2 cells
(bullish) and Q4/Q5 cells (bearish) out of 20.

All India-methodology states are computed:
- RS state (Leader → Laggard via VT-primary pctile)
- Momentum state (Accelerating → Collapsing via EMA ratios)
- Risk state (Low → Below Trend via vol_ratio + extension)
- Volume state (Accumulation → Heavy Distribution via effort_ratio)
- History gate, liquidity gate, Weinstein gate
- Suspension overrides (INSUFFICIENT_HISTORY, ILLIQUID)

Regime derives from VT trend + breadth. No VIX — volatility state uses
VT's own 5-day realized vol vs its 252-day median.
"""

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
from atlas.compute.benchmarks import materialize_benchmark_cache, persist_benchmark_cache
from atlas.compute.gates import add_history_gate, add_weinstein_gate
from atlas.compute.primitives import (
    WINDOWS,
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

_VALID_SCHEMAS = frozenset({"global_atlas", "us_atlas"})
_BENCHMARKS = ["ACWI", "VT", "EEM", "GOLD"]
_TIMEFRAMES = ["1w", "1m", "3m", "6m", "12m"]

# Global Atlas: full primitive set + RS vs 4 benchmarks × 5 timeframes
GLOBAL_METRICS_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "ret_12m_1m",
    "ema_10_stock",
    "ema_20_stock",
    "ema_50_stock",
    "ema_200_stock",
    "ema_10_ratio",
    "ema_20_ratio",
    "realized_vol_63",
    "vol_ratio_63",
    "max_drawdown_252",
    "extension_pct",
    "above_30w_ma",
    "avg_volume_20",
    "volume_expansion",
    "effort_ratio_63",
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
    "rs_consensus_bullish",
    "rs_consensus_bearish",
)

# US Atlas ETFs: identical to global (vol_ratio_63 and others already in global now)
US_ETF_METRICS_COLUMNS: tuple[str, ...] = GLOBAL_METRICS_COLUMNS

_SCHEMA_METRICS_COLUMNS: dict[str, tuple[str, ...]] = {
    "global_atlas": GLOBAL_METRICS_COLUMNS,
    "us_atlas": US_ETF_METRICS_COLUMNS,
}

# Shared across both schemas — normalized state structure
RS_STATES_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "benchmark",
    "timeframe",
    "rs_value",
    "rs_pctile",
    "rs_state",
    "rs_quintile",
)

GLOBAL_STATES_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "rs_state",
    "momentum_state",
    "risk_state",
    "volume_state",
    "history_gate_pass",
    "liquidity_gate_pass",
    "weinstein_gate_pass",
    "compute_run_id",
)

REGIME_COLUMNS: tuple[str, ...] = (
    "date",
    "benchmark_close",
    "benchmark_ema_50",
    "benchmark_ema_200",
    "benchmark_ema_50_slope",
    "benchmark_ema_200_slope",
    "benchmark_above_ema_50",
    "benchmark_above_ema_200",
    "realized_vol_5d",
    "vol_252_median",
    "pct_countries_above_200dma",
    "pct_countries_above_50dma",
    "regime_state",
    "dislocation_flag",
)

# Public aliases for backward compat
METRICS_COLUMNS = GLOBAL_METRICS_COLUMNS


def _load_universe(engine: Engine, schema: str) -> pd.DataFrame:
    if schema not in _VALID_SCHEMAS:
        raise ValueError(f"_load_universe: schema must be one of {_VALID_SCHEMAS}, got {schema!r}")
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            f"SELECT ticker FROM {schema}.atlas_universe_etfs WHERE is_active = TRUE",  # noqa: S608 -- schema validated above
            conn,
        )


def _load_ohlcv(
    engine: Engine,
    *,
    tickers: list[str],
    start: date,
    end: date,
    schema: str,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    if schema not in _VALID_SCHEMAS:
        raise ValueError(f"_load_ohlcv: schema must be one of {_VALID_SCHEMAS}, got {schema!r}")
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            f"""
            SELECT ticker, date, open, high, low, close, volume
            FROM {schema}.stock_ohlcv
            WHERE ticker = ANY(%(tickers)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY ticker, date
            """,  # noqa: S608 -- schema validated above
            conn,
            params={"tickers": tickers, "start": start, "end": end},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _add_primitives(
    df: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
) -> pd.DataFrame:
    """Full India-methodology primitive stack for global/US ETFs.

    Computes: returns, EMAs, realized_vol, max_drawdown, RS momentum
    (EMA ratios + 20d high/low flags), extension_pct, above_30w_ma,
    volume_expansion + effort_ratio_63, vol_ratio_63 vs VT.
    """
    df = add_returns(df, group_col="ticker", price_col="close", windows=WINDOWS)
    df = add_emas(
        df, group_col="ticker", price_col="close", lengths=(10, 20, 50, 200), suffix="stock"
    )
    df = add_realized_vol(df, group_col="ticker", return_col="ret_1d", window=63)
    df = add_max_drawdown(df, group_col="ticker", return_col="ret_1d", window=252)

    # Merge VT EMAs so add_rs_momentum can compute ema_20_ratio (benchmark trend)
    vt_emas = benchmark_cache.loc[
        benchmark_cache["benchmark_code"] == "VT",
        ["date", "ema_10_benchmark", "ema_20_benchmark"],
    ]
    if not vt_emas.empty:
        df = df.merge(vt_emas, on="date", how="left")
        df = add_rs_momentum(df, group_col="ticker")
        df = df.drop(columns=["ema_10_benchmark", "ema_20_benchmark"], errors="ignore")
    else:
        log.warning("vt_emas_missing_fallback_to_price_ratios")
        df["ema_10_ratio"] = df["close"] / df["ema_10_stock"].replace(0, pd.NA) - 1
        df["ema_20_ratio"] = df["close"] / df["ema_20_stock"].replace(0, pd.NA) - 1
        df["ema_10_at_20d_high"] = False
        df["ema_10_at_20d_low"] = False

    # above_30w_ma computed by add_weinstein_gate (called later) but set as bool here
    # for primitives; the gate overwrites with the slope-qualified version
    sma_150 = df.groupby("ticker", group_keys=False, observed=True)["close"].transform(
        lambda s: s.rolling(150, min_periods=75).mean()
    )
    df["above_30w_ma"] = df["close"] > sma_150

    if "ema_200_stock" in df.columns:
        df = add_extension_pct(df, price_col="close", ema_col="ema_200_stock")

    # Volume primitives: avg_volume_20, volume_expansion, effort_ratio_63
    df = add_volume_primitives(df, group_col="ticker", event_dates=set())

    # vol_ratio_63: ETF 63d realized vol / VT 63d realized vol
    vt_vol = benchmark_cache.loc[
        benchmark_cache["benchmark_code"] == "VT", ["date", "realized_vol_63"]
    ].rename(columns={"realized_vol_63": "_vt_vol"})
    if not vt_vol.empty:
        df = df.merge(vt_vol, on="date", how="left")
        df["vol_ratio_63"] = df["realized_vol_63"] / df["_vt_vol"].replace(0, pd.NA)
        df = df.drop(columns=["_vt_vol"])
    else:
        df["vol_ratio_63"] = pd.NA

    return df


def _compute_rs_for_benchmark(
    df: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
    bench_code: str,
) -> pd.DataFrame:
    """Add rs_value and rs_pctile columns for one benchmark across all timeframes."""
    bench_label = bench_code.lower()
    bench = benchmark_cache.loc[benchmark_cache["benchmark_code"] == bench_code]

    if bench.empty:
        log.warning("benchmark_missing_in_cache", bench_code=bench_code)
        for tf in _TIMEFRAMES:
            df[f"rs_{tf}_{bench_label}"] = pd.NA
            df[f"rs_pctile_{tf}_{bench_label}"] = pd.NA
        return df

    bench_ret_cols = [f"ret_{tf}" for tf in _TIMEFRAMES if f"ret_{tf}" in bench.columns]
    bench_subset = bench[["date", *bench_ret_cols]].rename(
        columns={f"ret_{tf}": f"_br_{bench_label}_{tf}" for tf in _TIMEFRAMES}
    )
    df = df.merge(bench_subset, on="date", how="left")

    for tf in _TIMEFRAMES:
        ret_col = f"ret_{tf}"
        bench_tmp = f"_br_{bench_label}_{tf}"
        rs_col = f"rs_{tf}_{bench_label}"
        pctile_col = f"rs_pctile_{tf}_{bench_label}"

        if ret_col in df.columns and bench_tmp in df.columns:
            df[rs_col] = df[ret_col] - df[bench_tmp]
        else:
            df[rs_col] = pd.NA

        grp = df.groupby("date", observed=True)[rs_col]
        n_valid = grp.transform("count")
        df[pctile_col] = grp.rank(method="dense", ascending=True, pct=True).where(n_valid >= 5)

    df = df.drop(columns=[c for c in df.columns if c.startswith(f"_br_{bench_label}_")])
    return df


def _compute_consensus(
    df: pd.DataFrame,
    thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Count bullish (top 40%) and bearish (bottom 40%) RS cells per instrument."""
    q2_min = float(thresholds.get("rs_q2_min_pctile", Decimal("0.60")))
    q4_max = float(thresholds.get("rs_q4_max_pctile", Decimal("0.40")))

    pctile_cols = [
        f"rs_pctile_{tf}_{b.lower()}"
        for b in _BENCHMARKS
        for tf in _TIMEFRAMES
        if f"rs_pctile_{tf}_{b.lower()}" in df.columns
    ]

    out = df.copy()
    if pctile_cols:
        out["rs_consensus_bullish"] = out[pctile_cols].ge(q2_min).sum(axis=1).astype("Int64")
        out["rs_consensus_bearish"] = out[pctile_cols].lt(q4_max).sum(axis=1).astype("Int64")
    else:
        out["rs_consensus_bullish"] = pd.NA
        out["rs_consensus_bearish"] = pd.NA

    return out


def _classify_states(
    df: pd.DataFrame,
    thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Apply the full India state stack to global/US ETFs.

    Uses VT pctiles as the primary RS universe ranking (same logic as India's
    single benchmark, applied here to the VT-relative percentile).
    Liquidity gate uses avg_volume_20 shares floor (not INR-denominated traded value).
    """
    # Gates
    df = add_history_gate(df, group_col="ticker")
    df = add_weinstein_gate(df, group_col="ticker", price_col="close")

    # Liquidity: avg daily volume (shares) vs threshold
    vol_floor = float(thresholds.get("liquidity_gate_min_avg_vol", Decimal("10000")))
    df["liquidity_gate_pass"] = df["avg_volume_20"].fillna(0) >= vol_floor

    # Stage 1 base: not meaningful for country/sector ETFs
    df["stage1_base_qualifies"] = False

    # RS state: use VT pctiles as primary within-universe ranking
    df["rs_pctile_1w"] = df.get("rs_pctile_1w_vt", pd.NA)
    df["rs_pctile_1m"] = df.get("rs_pctile_1m_vt", pd.NA)
    df["rs_pctile_3m"] = df.get("rs_pctile_3m_vt", pd.NA)
    df = classify_rs_state(df, thresholds)
    df = df.drop(columns=["rs_pctile_1w", "rs_pctile_1m", "rs_pctile_3m"], errors="ignore")

    # Momentum, risk, volume states (same classifiers as India)
    df = classify_momentum_state(df, thresholds)
    df = classify_risk_state(df, thresholds)
    df = classify_volume_state(df, thresholds)

    # Conjunction rule: Below Trend forces rs_state → Average
    df = apply_below_trend_conjunction(df)

    # Suspension overrides: INSUFFICIENT_HISTORY, ILLIQUID
    df = apply_suspension_overrides(df, market_dislocation=None)

    return df


def _to_rs_states_long(
    df: pd.DataFrame,
    thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Melt wide RS columns into (ticker, date, benchmark, timeframe) long format.

    rs_state uses India-methodology textual labels (Leader/Strong/Average/Weak/Laggard)
    derived from within-universe percentile quintiles.
    """
    q1_min = float(thresholds.get("rs_q1_min_pctile", Decimal("0.80")))
    q2_min = float(thresholds.get("rs_q2_min_pctile", Decimal("0.60")))
    q4_max = float(thresholds.get("rs_q4_max_pctile", Decimal("0.40")))
    q5_max = float(thresholds.get("rs_q5_max_pctile", Decimal("0.20")))

    rows: list[pd.DataFrame] = []
    for bench_code in _BENCHMARKS:
        bench_label = bench_code.lower()
        for tf in _TIMEFRAMES:
            rs_col = f"rs_{tf}_{bench_label}"
            pctile_col = f"rs_pctile_{tf}_{bench_label}"
            if rs_col not in df.columns:
                continue

            chunk = df[["ticker", "date", rs_col, pctile_col]].copy()
            chunk = chunk.rename(  # type: ignore[call-overload]
                columns={rs_col: "rs_value", pctile_col: "rs_pctile"}
            )
            chunk["benchmark"] = bench_label
            chunk["timeframe"] = tf

            p = chunk["rs_pctile"]
            quintile_arr = np.select(
                [p < q5_max, p < q4_max, p < q2_min, p < q1_min],
                [5, 4, 3, 2],
                default=1,
            )
            chunk["rs_quintile"] = pd.array(quintile_arr, dtype="Int64")
            chunk.loc[p.isna(), "rs_quintile"] = pd.NA
            _label_map: dict[int, str] = {
                1: "Leader",
                2: "Strong",
                3: "Average",
                4: "Weak",
                5: "Laggard",
            }
            chunk["rs_state"] = chunk["rs_quintile"].map(_label_map)  # type: ignore[arg-type]
            rows.append(chunk)

    if not rows:
        return pd.DataFrame(columns=RS_STATES_COLUMNS)  # type: ignore[call-overload]

    long = pd.concat(rows, ignore_index=True)
    long = long.dropna(subset=["rs_value"])
    return long.reindex(columns=list(RS_STATES_COLUMNS))


def _compute_regime(
    benchmark_cache: pd.DataFrame,
    etf_metrics: pd.DataFrame,
    thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """VT-based regime — no VIX; uses VT 5d realized vol vs 252d median."""
    vt = benchmark_cache.loc[benchmark_cache["benchmark_code"] == "VT"].sort_values("date").copy()

    if vt.empty:
        log.warning("vt_benchmark_missing_for_regime")
        return pd.DataFrame(columns=list(REGIME_COLUMNS))  # type: ignore[call-overload]

    regime = vt[["date", "close"]].rename(columns={"close": "benchmark_close"}).copy()  # type: ignore[call-overload]

    for col, alias in [
        ("ema_50_benchmark", "benchmark_ema_50"),
        ("ema_200_benchmark", "benchmark_ema_200"),
    ]:
        regime[alias] = vt[col].values if col in vt.columns else pd.NA

    for ema_col, slope_col in [
        ("benchmark_ema_50", "benchmark_ema_50_slope"),
        ("benchmark_ema_200", "benchmark_ema_200_slope"),
    ]:
        regime[slope_col] = regime[ema_col].pct_change(5)

    regime["benchmark_above_ema_50"] = regime["benchmark_close"] > regime["benchmark_ema_50"]
    regime["benchmark_above_ema_200"] = regime["benchmark_close"] > regime["benchmark_ema_200"]

    if "ret_1d" in vt.columns:
        vt_rets = vt.set_index("date")["ret_1d"].astype("float64")
        vol_5d = vt_rets.rolling(5, min_periods=3).std() * (252**0.5)
        vol_252_median = vol_5d.rolling(252, min_periods=63).median()
        regime = regime.set_index("date")
        regime["realized_vol_5d"] = vol_5d
        regime["vol_252_median"] = vol_252_median
        regime = regime.reset_index()
    else:
        regime["realized_vol_5d"] = pd.NA
        regime["vol_252_median"] = pd.NA

    if "ema_200_stock" in etf_metrics.columns and "ema_50_stock" in etf_metrics.columns:
        _bm = etf_metrics[["date", "close", "ema_200_stock", "ema_50_stock"]].copy()

        v200 = _bm[_bm["ema_200_stock"].notna()]  # type: ignore[index]
        above_200_flag = (v200["close"] > v200["ema_200_stock"]).astype(int)  # type: ignore[union-attr]
        agg200 = above_200_flag.groupby(v200["date"]).agg(["sum", "count"])  # type: ignore[union-attr]
        agg200["pct_countries_above_200dma"] = agg200["sum"] / agg200["count"].clip(lower=1)
        breadth_200 = agg200[["pct_countries_above_200dma"]].reset_index()

        v50 = _bm[_bm["ema_50_stock"].notna()]  # type: ignore[index]
        above_50_flag = (v50["close"] > v50["ema_50_stock"]).astype(int)  # type: ignore[union-attr]
        agg50 = above_50_flag.groupby(v50["date"]).agg(["sum", "count"])  # type: ignore[union-attr]
        agg50["pct_countries_above_50dma"] = agg50["sum"] / agg50["count"].clip(lower=1)
        breadth_50 = agg50[["pct_countries_above_50dma"]].reset_index()

        regime = regime.merge(breadth_200, on="date", how="left")
        regime = regime.merge(breadth_50, on="date", how="left")
    else:
        regime["pct_countries_above_200dma"] = pd.NA
        regime["pct_countries_above_50dma"] = pd.NA

    healthy_min = float(thresholds.get("breadth_healthy_min", Decimal("0.60")))
    caution_min = float(thresholds.get("breadth_caution_min", Decimal("0.40")))
    disloc_mult = float(thresholds.get("dislocation_vol_multiplier", Decimal("2.0")))

    above_200 = regime["benchmark_above_ema_200"].fillna(False)
    above_50 = regime["benchmark_above_ema_50"].fillna(False)
    breadth = regime["pct_countries_above_200dma"].fillna(0.0)

    regime["dislocation_flag"] = (
        regime["realized_vol_5d"] > disloc_mult * regime["vol_252_median"]
    ).fillna(False)

    # Conservative-first: most restrictive state matched first
    regime["regime_state"] = np.select(
        [
            (~above_200) & (breadth < caution_min),
            (~above_200) | (breadth < caution_min),
            above_50 & above_200 & (breadth >= healthy_min),
        ],
        ["Weak", "Caution", "Strong"],
        default="Healthy",
    )

    return regime.reindex(columns=list(REGIME_COLUMNS))


def _write_metrics(engine: Engine, df: pd.DataFrame, schema: str) -> int:
    cols = _SCHEMA_METRICS_COLUMNS.get(schema, GLOBAL_METRICS_COLUMNS)
    payload = df.copy().reindex(columns=list(cols))
    if payload.empty:
        return 0
    return bulk_upsert(
        engine,
        table=f"{schema}.atlas_etf_metrics_daily",
        columns=list(cols),
        rows=df_to_pg_rows(payload),
        pk_columns=["ticker", "date"],
    )


def _write_rs_states(engine: Engine, long_df: pd.DataFrame, schema: str) -> int:
    if long_df.empty:
        return 0
    return bulk_upsert(
        engine,
        table=f"{schema}.atlas_etf_rs_states",
        columns=list(RS_STATES_COLUMNS),
        rows=df_to_pg_rows(long_df.reindex(columns=list(RS_STATES_COLUMNS))),
        pk_columns=["ticker", "date", "benchmark", "timeframe"],
    )


def _write_states(engine: Engine, df: pd.DataFrame, schema: str, run_id: uuid.UUID) -> int:
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    required = [
        "rs_state",
        "momentum_state",
        "risk_state",
        "history_gate_pass",
        "liquidity_gate_pass",
        "weinstein_gate_pass",
    ]
    payload = df.reindex(columns=list(GLOBAL_STATES_COLUMNS)).dropna(subset=required)
    if payload.empty:
        return 0
    return bulk_upsert(
        engine,
        table=f"{schema}.atlas_etf_states_daily",
        columns=list(GLOBAL_STATES_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["ticker", "date"],
    )


def _write_regime(engine: Engine, regime_df: pd.DataFrame, schema: str) -> int:
    if regime_df.empty:
        return 0
    return bulk_upsert(
        engine,
        table=f"{schema}.atlas_market_regime_daily",
        columns=list(REGIME_COLUMNS),
        rows=df_to_pg_rows(regime_df.reindex(columns=list(REGIME_COLUMNS))),
        pk_columns=["date"],
    )


def _run_pipeline(
    engine: Engine,
    *,
    schema: str,
    start: date,
    end: date,
    write_only_date: date | None = None,
) -> dict[str, object]:
    """Core pipeline shared by backfill and daily modes."""
    if schema not in _VALID_SCHEMAS:
        raise ValueError(f"_run_pipeline: schema must be one of {_VALID_SCHEMAS}, got {schema!r}")

    run_id = uuid.uuid4()
    t0 = time.time()
    mode = "daily" if write_only_date else "backfill"

    log.info(
        f"{schema}_{mode}_start",
        run_id=str(run_id),
        start=str(start),
        end=str(end),
    )

    universe = _load_universe(engine, schema=schema)
    thresholds = load_thresholds(schema=schema, engine=engine)
    log.info("universe_loaded", count=len(universe), schema=schema)

    benchmark_cache = materialize_benchmark_cache(engine, start=start, end=end, schema=schema)
    persist_benchmark_cache(engine, benchmark_cache, schema=schema)

    ohlcv = _load_ohlcv(
        engine, tickers=universe["ticker"].tolist(), start=start, end=end, schema=schema
    )
    log.info("ohlcv_loaded", rows=len(ohlcv))

    df = _add_primitives(ohlcv, benchmark_cache)

    for bench_code in _BENCHMARKS:
        df = _compute_rs_for_benchmark(df, benchmark_cache, bench_code)

    df = _compute_consensus(df, thresholds)
    df = _classify_states(df, thresholds)

    # Filter to write_only_date if incremental
    write_df = df.loc[df["date"] == write_only_date] if write_only_date else df

    metrics_rows = _write_metrics(engine, write_df, schema=schema)
    log.info("metrics_written", rows=metrics_rows)

    rs_long = _to_rs_states_long(write_df, thresholds)
    rs_rows = _write_rs_states(engine, rs_long, schema=schema)
    log.info("rs_states_written", rows=rs_rows)

    states_rows = _write_states(engine, write_df, schema=schema, run_id=run_id)
    log.info("states_written", rows=states_rows)

    # Regime: always computed over full range; write only target date if incremental
    regime_df = _compute_regime(benchmark_cache, df, thresholds)
    if write_only_date:
        regime_df = regime_df.loc[regime_df["date"] == write_only_date]
    regime_rows = _write_regime(engine, regime_df, schema=schema)
    log.info("regime_written", rows=regime_rows)

    elapsed = round(time.time() - t0, 1)
    log.info(
        f"{schema}_{mode}_complete",
        run_id=str(run_id),
        metrics_rows=metrics_rows,
        rs_rows=rs_rows,
        states_rows=states_rows,
        regime_rows=regime_rows,
        elapsed_sec=elapsed,
    )
    return {
        "run_id": str(run_id),
        "metrics_rows": metrics_rows,
        "rs_rows": rs_rows,
        "states_rows": states_rows,
        "regime_rows": regime_rows,
        "elapsed_sec": elapsed,
    }


# --------------------------------------------------------------------------- #
# Public API — Global Atlas                                                    #
# --------------------------------------------------------------------------- #


def run_global_backfill(
    *,
    start: date | None = None,
    end: date | None = None,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Full historical backfill for Global Atlas (30 country ETFs)."""
    eng = engine or get_engine()
    _start = start or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    _end = end or date.today()
    return _run_pipeline(eng, schema="global_atlas", start=_start, end=_end)


def run_global_daily(
    target_date: date,
    *,
    lookback_days: int = 400,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Incremental daily run for Global Atlas — writes only ``target_date`` rows."""
    eng = engine or get_engine()
    start = target_date - timedelta(days=lookback_days)
    return _run_pipeline(
        eng, schema="global_atlas", start=start, end=target_date, write_only_date=target_date
    )


# --------------------------------------------------------------------------- #
# Public API — US Atlas ETFs                                                   #
# --------------------------------------------------------------------------- #


def run_us_etf_backfill(
    *,
    start: date | None = None,
    end: date | None = None,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Full historical backfill for US Atlas ETFs."""
    eng = engine or get_engine()
    _start = start or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    _end = end or date.today()
    return _run_pipeline(eng, schema="us_atlas", start=_start, end=_end)


def run_us_etf_daily(
    target_date: date,
    *,
    lookback_days: int = 400,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Incremental daily run for US Atlas ETFs — writes only ``target_date`` rows."""
    eng = engine or get_engine()
    start = target_date - timedelta(days=lookback_days)
    return _run_pipeline(
        eng, schema="us_atlas", start=start, end=target_date, write_only_date=target_date
    )


__all__ = [
    "GLOBAL_METRICS_COLUMNS",
    "GLOBAL_STATES_COLUMNS",
    "REGIME_COLUMNS",
    "RS_STATES_COLUMNS",
    "US_ETF_METRICS_COLUMNS",
    "run_global_backfill",
    "run_global_daily",
    "run_us_etf_backfill",
    "run_us_etf_daily",
]
