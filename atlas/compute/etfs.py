"""ETF metric + state pipeline (M2).

Same shape as :mod:`atlas.compute.stocks` with three ETF-specific tweaks per
methodology §8.1:

1. No within-tier percentile ranking — ETFs aren't tiered.
2. Volume primitive is computed but informational only (volume_state may be
   NULL in ``atlas_etf_states_daily`` per schema 005).
3. Benchmark depends on theme: Broad → NIFTY 500, Sectoral → linked sector
   index, Thematic → NIFTY 500.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.benchmarks import (
    add_relative_strength,
    add_vol_ratio,
    materialize_benchmark_cache,
    persist_benchmark_cache,
)
from atlas.compute.gates import (
    add_history_gate,
    add_liquidity_gate,
    add_weinstein_gate,
)
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
    classify_volume_state,
)
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()


THEME_BENCHMARK = {
    "Broad": "NIFTY500",
    "Sectoral": None,  # resolved per ETF via linked_sector → sector benchmark
    "Thematic": "NIFTY500",
    "International": "MSCIWORLD",
    "Gold": "GOLD",
    "Silver": "NIFTY500",  # No dedicated silver benchmark; NIFTY500 used as baseline
}
"""Methodology §8.1 theme → default benchmark mapping. Sectoral is filled in
per-ETF using ``atlas_universe_etfs.linked_sector``."""


METRICS_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "rs_1w_benchmark",
    "rs_1m_benchmark",
    "rs_3m_benchmark",
    "rs_pctile_1w",
    "rs_pctile_1m",
    "rs_pctile_3m",
    "ema_10_etf",
    "ema_20_etf",
    "ema_10_benchmark",
    "ema_20_benchmark",
    "ema_10_ratio",
    "ema_20_ratio",
    "ema_10_at_20d_high",
    "ema_10_at_20d_low",
    "extension_pct",
    "ema_200_etf",
    "vol_ratio_63",
    "realized_vol_63",
    "drawdown_ratio_252",
    "volume_expansion",
    "avg_volume_20",
    "effort_ratio_63",
    "above_30w_ma",
    "weinstein_gate_pass",
    "rs_1w_benchmark_gold",
    "rs_1m_benchmark_gold",
    "rs_3m_benchmark_gold",
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
    "theme",
    "linked_sector",
    "compute_run_id",
)


def _load_universe(engine: Engine) -> pd.DataFrame:
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT ticker, theme, linked_sector
            FROM atlas.atlas_universe_etfs
            WHERE effective_to IS NULL
            """,
            conn,
        )


def _load_ohlcv(
    engine: Engine,
    *,
    tickers: Iterable[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    tickers_list = list(tickers)
    if not tickers_list:
        return pd.DataFrame()
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT ticker, date, open, high, low, close, volume
            FROM public.de_etf_ohlcv
            WHERE ticker = ANY(%(tickers)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY ticker, date
            """,
            conn,
            params={"tickers": tickers_list, "start": start, "end": end},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _resolve_benchmark_code(
    universe: pd.DataFrame,
    sector_to_benchmark: dict[str, str],
    *,
    sectoral_fallback: str = "NIFTY500",
) -> pd.DataFrame:
    """Add ``benchmark_code`` per ETF using theme + linked_sector.

    v0 sectoral fallback: if a sectoral ETF's ``linked_sector`` has no matching
    Atlas benchmark (which is the v0 reality — see ``_load_sector_benchmark_map``),
    fall back to ``NIFTY500`` so the ETF still gets a usable benchmark for RS.
    """
    out = universe.copy()
    out["benchmark_code"] = out["theme"].map(THEME_BENCHMARK)  # type: ignore[arg-type]
    sectoral = out["theme"] == "Sectoral"
    if sector_to_benchmark:
        out.loc[sectoral, "benchmark_code"] = out.loc[sectoral, "linked_sector"].map(
            sector_to_benchmark
        )
    out["benchmark_code"] = out["benchmark_code"].fillna(sectoral_fallback)
    return out


def _load_sector_benchmark_map(engine: Engine) -> dict[str, str]:
    """Linked-sector → benchmark_code via ``atlas_sector_master``.

    v0 reality: ``atlas_sector_master`` carries ``primary_nse_index`` (the
    NSE-published index name, e.g. ``'NIFTY BANK'``), not a benchmark_code
    that resolves inside ``atlas_benchmark_master``. The 10 benchmarks
    populated by M1 don't include sector indices yet, so there's no usable
    mapping. Returns ``{}`` for v0; sectoral ETFs fall back to ``NIFTY500``
    via :func:`_resolve_benchmark_code`. Tracked in
    ``prds/00_INFRA_DECISIONS.md`` for a v1 follow-up that seeds sector
    indices into ``atlas_benchmark_master``.
    """
    return {}


def _merge_benchmark(
    etfs: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
) -> pd.DataFrame:
    """Merge per-ETF benchmark return/EMA columns by date.

    Suffixes the benchmark columns to avoid colliding with ETF own EMAs.
    """
    bench_cols = ["benchmark_code", "date"] + [
        c
        for c in benchmark_cache.columns
        if c.startswith(("ret_", "ema_", "realized_vol_", "max_drawdown_"))
    ]
    bench = benchmark_cache[bench_cols].copy()
    rename = {f"ret_{n}": f"ret_{n}_benchmark" for n in WINDOWS}
    rename["ret_1d"] = "ret_1d_benchmark"
    rename["realized_vol_63"] = "realized_vol_63_benchmark"
    rename["max_drawdown_252"] = "max_drawdown_252_bench"
    rename.update({f"ema_{n}_benchmark": f"ema_{n}_benchmark" for n in (10, 20, 50, 200)})
    bench = bench.rename(columns=rename)  # type: ignore[call-overload]

    return etfs.merge(bench, on=["benchmark_code", "date"], how="left")


def _compute_etf_metrics(
    ohlcv: pd.DataFrame,
    *,
    universe_with_benchmark: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
    event_dates: set,
    thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Pure-function ETF compute — primitives → states."""
    df = ohlcv.merge(
        universe_with_benchmark[["ticker", "theme", "linked_sector", "benchmark_code"]],
        on="ticker",
        how="left",
    )

    df = add_returns(df, group_col="ticker", price_col="close")
    df = add_emas(df, group_col="ticker", price_col="close", lengths=(10, 20, 200), suffix="etf")
    df = add_realized_vol(df, group_col="ticker", return_col="ret_1d", window=63)
    df = add_max_drawdown(df, group_col="ticker", return_col="ret_1d", window=252)
    df = add_extension_pct(df, ema_col="ema_200_etf")
    df = add_volume_primitives(df, group_col="ticker", event_dates=event_dates)

    df = add_history_gate(df, group_col="ticker")
    df = add_liquidity_gate(df, group_col="ticker")
    df = add_weinstein_gate(df, group_col="ticker", price_col="close")

    df = _merge_benchmark(df, benchmark_cache)
    df = add_relative_strength(df, windows=WINDOWS)

    # Rename tier-style RS columns to the ETF column names per schema 004
    rs_renames = {
        "rs_1w_tier": "rs_1w_benchmark",
        "rs_1m_tier": "rs_1m_benchmark",
        "rs_3m_tier": "rs_3m_benchmark",
    }
    df = df.rename(columns={k: v for k, v in rs_renames.items() if k in df.columns})

    # Momentum: ETF EMA / benchmark EMA
    if "ema_10_etf" in df.columns and "ema_10_benchmark" in df.columns:
        df["ema_10_stock"] = df["ema_10_etf"]
        df["ema_20_stock"] = df["ema_20_etf"]
        df = add_rs_momentum(df, group_col="ticker")
        df = df.drop(columns=["ema_10_stock", "ema_20_stock"])

    df = add_vol_ratio(df)
    df["drawdown_ratio_252"] = (
        -df["max_drawdown_252"] if "max_drawdown_252" in df.columns else pd.NA
    )

    # ETF percentile ranking — uses RS vs own benchmark, ranked across ETFs
    for w in ("1w", "1m", "3m"):
        col = f"rs_{w}_benchmark"
        if col in df.columns:
            ranks = df.groupby("date", observed=True)[col].rank(method="dense")
            counts = df.groupby("date", observed=True)[col].transform("count")
            df[f"rs_pctile_{w}"] = (ranks / counts).where(counts >= 5)

    # Gold numéraire variants
    gold = benchmark_cache.loc[benchmark_cache["benchmark_code"] == "GOLD"]
    if not gold.empty:
        gold_subset = gold[["date"] + [f"ret_{w}" for w in ("1w", "1m", "3m")]].rename(
            columns={f"ret_{w}": f"_gold_ret_{w}" for w in ("1w", "1m", "3m")}
        )
        df = df.merge(gold_subset, on="date", how="left")
        for w in ("1w", "1m", "3m"):
            df[f"rs_{w}_benchmark_gold"] = df[f"rs_{w}_benchmark"] / (1 + df[f"_gold_ret_{w}"])
        df = df.drop(columns=[c for c in df.columns if c.startswith("_gold_ret_")])
    else:
        for w in ("1w", "1m", "3m"):
            df[f"rs_{w}_benchmark_gold"] = pd.NA

    # State classification (no Stage-1 base, no within-tier — ETFs are flat)
    df["stage1_base_qualifies"] = False
    df = classify_momentum_state(df, thresholds)
    df = classify_risk_state(df, thresholds)
    df = classify_volume_state(df, thresholds)

    # ETFs use a simplified RS state (no tier percentile) — fall back to
    # Average for v0; a future enhancement can introduce theme percentiles.
    df["rs_state"] = "Average"
    df.loc[df["rs_3m_benchmark"] > 0.05, "rs_state"] = "Strong"
    df.loc[df["rs_3m_benchmark"] < -0.05, "rs_state"] = "Weak"

    df = apply_below_trend_conjunction(df)
    df = apply_suspension_overrides(df, market_dislocation=None)
    return df


def _write_metrics(engine: Engine, df: pd.DataFrame, run_id: uuid.UUID) -> int:
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(METRICS_COLUMNS))
    return bulk_upsert(
        engine,
        table="atlas.atlas_etf_metrics_daily",
        columns=list(METRICS_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["ticker", "date"],
    )


def _write_states(engine: Engine, df: pd.DataFrame, run_id: uuid.UUID) -> int:
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(STATES_COLUMNS))
    required = [
        "rs_state",
        "momentum_state",
        "risk_state",
        "history_gate_pass",
        "liquidity_gate_pass",
        "weinstein_gate_pass",
    ]
    payload = payload.dropna(subset=required)
    return bulk_upsert(
        engine,
        table="atlas.atlas_etf_states_daily",
        columns=list(STATES_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["ticker", "date"],
    )


def run_etf_backfill(
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
    sector_map = _load_sector_benchmark_map(eng)
    universe = _resolve_benchmark_code(universe, sector_map)
    thresholds = load_thresholds(eng)
    benchmark_cache = materialize_benchmark_cache(eng, start=start, end=end)
    persist_benchmark_cache(eng, benchmark_cache)

    # v0: trading-calendar event-day flags aren't yet exposed by JIP.
    # See ``atlas.compute.stocks._load_event_dates`` for the same fallback.
    from atlas.compute.stocks import _load_event_dates as _stock_event_dates

    event_dates = _stock_event_dates(eng)

    ohlcv = _load_ohlcv(
        eng,
        tickers=universe["ticker"].tolist(),
        start=start,
        end=end,
    )
    metrics = _compute_etf_metrics(
        ohlcv,
        universe_with_benchmark=universe,
        benchmark_cache=benchmark_cache,
        event_dates=event_dates,
        thresholds=thresholds,
    )

    metric_rows = _write_metrics(eng, metrics, run_id)
    state_rows = _write_states(eng, metrics, run_id)

    log.info(
        "etf_backfill_complete",
        run_id=str(run_id),
        metric_rows=metric_rows,
        state_rows=state_rows,
        duration_sec=round(time.time() - started, 1),
    )
    return {
        "run_id": str(run_id),
        "metric_rows": metric_rows,
        "state_rows": state_rows,
        "duration_sec": round(time.time() - started, 1),
    }


def run_etf_daily(
    target_date: date,
    *,
    lookback_days: int = 400,
    engine: Engine | None = None,
) -> dict[str, object]:
    return run_etf_backfill(
        start=target_date - timedelta(days=lookback_days),
        end=target_date,
        engine=engine,
    )


__all__ = ["run_etf_backfill", "run_etf_daily"]
