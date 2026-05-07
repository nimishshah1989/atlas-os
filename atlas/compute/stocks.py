"""Stock metric + state pipeline (M2).

Wires primitives → gates → states → bulk DB write. Vectorised across the
entire 750-stock universe in a single pandas operation; never iterates rows
in Python.

Two entry points:

* :func:`run_stock_backfill` — full historical (10 yr x 750 stocks ~2.25 M rows).
* :func:`run_stock_daily` — single-date incremental (T-1 row only, but reads
  back ~252 days of history per stock so rolling windows are correct).

Both write to ``atlas_stock_metrics_daily`` and ``atlas_stock_states_daily``
via :func:`atlas.compute._session.bulk_upsert` with 3,000-row pages.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.benchmarks import (
    GOLD_BENCHMARK,
    TIER_BENCHMARK,
    add_relative_strength,
    add_vol_ratio,
    materialize_benchmark_cache,
    merge_tier_benchmark,
)
from atlas.compute.gates import (
    add_history_gate,
    add_liquidity_gate,
    add_stage1_base,
    add_weinstein_gate,
)
from atlas.compute.primitives import (
    WINDOWS,
    add_atr,
    add_emas,
    add_extension_pct,
    add_max_drawdown,
    add_realized_vol,
    add_returns,
    add_rs_momentum,
    add_volume_primitives,
    add_within_tier_percentiles,
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


METRICS_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "date",
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "ret_12m_1m",
    "rs_1w_tier",
    "rs_1m_tier",
    "rs_3m_tier",
    "rs_6m_tier",
    "rs_12m_tier",
    "rs_pctile_1w",
    "rs_pctile_1m",
    "rs_pctile_3m",
    "ema_10_stock",
    "ema_20_stock",
    "ema_50_stock",
    "ema_200_stock",
    "ema_10_benchmark",
    "ema_20_benchmark",
    "ema_10_ratio",
    "ema_20_ratio",
    "ema_10_at_20d_high",
    "ema_10_at_20d_low",
    "extension_pct",
    "vol_ratio_63",
    "realized_vol_63",
    "drawdown_ratio_252",
    "max_drawdown_252",
    "atr_21",
    "volume_expansion",
    "avg_volume_20",
    "avg_volume_252",
    "effort_ratio_63",
    "above_30w_ma",
    "ma_30w_slope_4w",
    "weinstein_gate_pass",
    "stage1_base_qualifies",
    "rs_1w_tier_gold",
    "rs_1m_tier_gold",
    "rs_3m_tier_gold",
    "compute_run_id",
)

STATES_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "date",
    "rs_state",
    "momentum_state",
    "risk_state",
    "volume_state",
    "history_gate_pass",
    "liquidity_gate_pass",
    "weinstein_gate_pass",
    "stage1_base_qualifies",
    "sector",
    "tier",
    "compute_run_id",
)


def _load_universe(engine: Engine) -> pd.DataFrame:
    """Active stock universe with tier and sector denormalised."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT instrument_id, symbol, tier, sector, listing_date
            FROM atlas.atlas_universe_stocks
            WHERE effective_to IS NULL
            """,
            conn,
        )


def _load_ohlcv(
    engine: Engine,
    *,
    instrument_ids: Iterable[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    """Load adjusted OHLCV for the given universe across the date range.

    Single query for the entire universe — see ``prds/M2_BUILD_PLAN.md`` §3.
    The returned frame is sorted by ``(instrument_id, date)`` so groupby is
    cheap.
    """
    ids = tuple(instrument_ids)
    if not ids:
        return pd.DataFrame()

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT instrument_id, date, open, high, low, close, volume
            FROM public.de_equity_ohlcv
            WHERE instrument_id = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY instrument_id, date
            """,
            conn,
            params={"ids": list(ids), "start": start, "end": end},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _load_event_dates(engine: Engine) -> set:
    """Half-session + major-event dates from JIP trading calendar.

    v0: JIP's ``de_trading_calendar`` only carries ``date``, ``is_trading``,
    ``exchange``, ``notes`` — no ``is_half_session`` or ``is_major_event_day``
    flags. We try those columns and fall back to an empty set when absent,
    keeping the volume primitive functional. Tracked in M2 spec §12 as an
    open data-engineering question.
    """
    has_flags_q = """
        SELECT
          BOOL_OR(column_name = 'is_half_session') AS has_half,
          BOOL_OR(column_name = 'is_major_event_day') AS has_event
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'de_trading_calendar'
    """
    with open_compute_session(engine) as conn:
        flags = pd.read_sql(has_flags_q, conn).iloc[0]
        if not (bool(flags["has_half"]) or bool(flags["has_event"])):
            log.warning("event_day_columns_missing", fallback="empty_set")
            return set()
        cols = []
        if bool(flags["has_half"]):
            cols.append("COALESCE(is_half_session, FALSE)")
        if bool(flags["has_event"]):
            cols.append("COALESCE(is_major_event_day, FALSE)")
        df = pd.read_sql(
            f"SELECT date FROM public.de_trading_calendar WHERE {' OR '.join(cols)}",
            conn,
        )
    return set(pd.to_datetime(df["date"]).dt.date)


def _gold_relative_strength(
    df: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
) -> pd.DataFrame:
    """Append ``rs_<window>_tier_gold`` — gold-numéraire variants of tier RS.

    Per methodology §7.6: divide everything by gold's return for the same
    window. ``RS_gold = (1 + ret_stock) / (1 + ret_gold) - (1 + ret_bench) / (1 + ret_gold)``
    simplifies to ``(ret_stock - ret_bench) / (1 + ret_gold)``.
    """
    out = df.copy()
    gold = benchmark_cache.loc[benchmark_cache["benchmark_code"] == GOLD_BENCHMARK]
    if gold.empty:
        for w in ("1w", "1m", "3m"):
            out[f"rs_{w}_tier_gold"] = pd.NA
        return out

    gold_returns = gold[["date"] + [f"ret_{w}" for w in ("1w", "1m", "3m")]].rename(
        columns={f"ret_{w}": f"_gold_ret_{w}" for w in ("1w", "1m", "3m")}
    )
    out = out.merge(gold_returns, on="date", how="left")
    for w in ("1w", "1m", "3m"):
        out[f"rs_{w}_tier_gold"] = out[f"rs_{w}_tier"] / (1 + out[f"_gold_ret_{w}"])
    out = out.drop(columns=[c for c in out.columns if c.startswith("_gold_ret_")])
    return out


def _log_run(
    engine: Engine,
    *,
    run_id: uuid.UUID,
    stage: str,
    status: str,
    rows_written: int,
    started_at: float,
    finished_at: float | None = None,
    error: str | None = None,
) -> None:
    """Append a row to ``atlas_run_log``. Best-effort — failures here log only."""
    finished = finished_at if finished_at is not None else time.time()
    duration_sec = int(finished - started_at)
    # atlas_run_log schema uses per-stage timing columns; M2 stock runs map to stage3.
    payload = {
        "compute_run_id": run_id,
        "business_date": date.today(),
        "started_at": pd.Timestamp.fromtimestamp(started_at, tz="UTC").to_pydatetime(),
        "completed_at": pd.Timestamp.fromtimestamp(finished, tz="UTC").to_pydatetime(),
        "status": status,
        "stage3_stock_etf_sec": duration_sec,
        "rows_written_total": rows_written,
        "failure_message": error,
    }
    try:
        with open_compute_session(engine) as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO atlas.atlas_run_log
                        (compute_run_id, business_date, started_at, completed_at,
                         status, stage3_stock_etf_sec, rows_written_total,
                         failure_message)
                    VALUES
                        (:compute_run_id, :business_date, :started_at, :completed_at,
                         :status, :stage3_stock_etf_sec, :rows_written_total,
                         :failure_message)
                    """
                ),
                payload,
            )
            conn.commit()
    except Exception as exc:
        log.warning("run_log_insert_failed", stage=stage, error=str(exc))


def _compute_stock_metrics(
    ohlcv: pd.DataFrame,
    *,
    universe: pd.DataFrame,
    benchmark_cache: pd.DataFrame,
    event_dates: set,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    """Run the full primitives → percentiles → states pipeline on ``ohlcv``.

    Pure-function: takes inputs, returns a single DataFrame with metrics +
    states columns ready to write. No DB I/O.
    """
    df = ohlcv.merge(
        universe[["instrument_id", "tier", "sector"]],
        on="instrument_id",
        how="left",
    )

    # Phase 1 — per-stock primitives (vectorised across universe)
    df = add_returns(df, group_col="instrument_id", price_col="close")
    df = add_emas(
        df, group_col="instrument_id", price_col="close", lengths=(10, 20, 50, 200), suffix="stock"
    )
    df = add_atr(df, group_col="instrument_id", length=21)
    df = add_realized_vol(df, group_col="instrument_id", return_col="ret_1d", window=63)
    df = add_max_drawdown(df, group_col="instrument_id", return_col="ret_1d", window=252)
    df = add_extension_pct(df)
    df = add_volume_primitives(df, group_col="instrument_id", event_dates=event_dates)

    # Phase 2 — gate computations
    df = add_history_gate(df, group_col="instrument_id")
    df = add_liquidity_gate(df, group_col="instrument_id")
    df = add_weinstein_gate(df, group_col="instrument_id")

    # Phase 3 — benchmark merge + RS + momentum + risk-ratios
    df = merge_tier_benchmark(df, benchmark_cache, tier_col="tier")
    df = add_relative_strength(df, windows=WINDOWS)
    df = add_rs_momentum(df, group_col="instrument_id")
    df = add_vol_ratio(df)

    # Drawdown ratio: stock / benchmark over same window
    bench_dd = (
        benchmark_cache[["benchmark_code", "date", "max_drawdown_252"]]
        if "max_drawdown_252" in benchmark_cache.columns
        else None
    )
    if bench_dd is not None:
        df = df.merge(
            bench_dd.rename(columns={"max_drawdown_252": "max_drawdown_252_bench"}),
            on=["benchmark_code", "date"],
            how="left",
        )
        df["drawdown_ratio_252"] = df["max_drawdown_252"] / df["max_drawdown_252_bench"]
    else:
        df["drawdown_ratio_252"] = pd.NA

    # Phase 4 — within-tier percentiles (must happen after RS for whole universe)
    df = add_within_tier_percentiles(
        df,
        rs_cols=("rs_1w_tier", "rs_1m_tier", "rs_3m_tier"),
        tier_col="tier",
    )

    # Phase 5 — gold numéraire variants (last because it merges another series)
    df = _gold_relative_strength(df, benchmark_cache)

    # Phase 6 — two-pass RS classification because Emerging requires Stage-1
    # base qualification, which itself depends on prior rs_state values.
    # Pass 1: classify with stage1=False everywhere (no Emerging yet).
    # Pass 2: compute stage1 from the just-derived rs_state series, then
    # re-classify so Emerging can fire on rows that qualify.
    df["stage1_base_qualifies"] = False
    df = classify_rs_state(df, thresholds)
    df = add_stage1_base(df, group_col="instrument_id", state_col="rs_state")
    df = classify_rs_state(df, thresholds)
    df = classify_momentum_state(df, thresholds)
    df = classify_risk_state(df, thresholds)
    df = classify_volume_state(df, thresholds)
    df = apply_below_trend_conjunction(df)

    # Phase 7 — suspension overrides (M2 backfill: no market dislocation yet)
    df = apply_suspension_overrides(df, market_dislocation=None)
    return df


def _coerce_volume_bigints(df: pd.DataFrame) -> pd.DataFrame:
    """avg_volume_20 / avg_volume_252 are BIGINT in schema 004 but rolling-mean
    yields float. Cast through nullable ``Int64`` so NaN rows survive as NA →
    None at the psycopg2 boundary.
    """
    out = df.copy()
    for col in ("avg_volume_20", "avg_volume_252"):
        if col in out.columns:
            out[col] = out[col].round().astype("Int64")
    return out


def _write_metrics(engine: Engine, df: pd.DataFrame, run_id: uuid.UUID) -> int:
    """Bulk-upsert into ``atlas_stock_metrics_daily``."""
    df = _coerce_volume_bigints(df)
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(METRICS_COLUMNS))
    return bulk_upsert(
        engine,
        table="atlas.atlas_stock_metrics_daily",
        columns=list(METRICS_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["instrument_id", "date"],
    )


def _write_states(engine: Engine, df: pd.DataFrame, run_id: uuid.UUID) -> int:
    """Bulk-upsert into ``atlas_stock_states_daily``.

    States are NOT NULL in schema 005 — drop rows where critical state cols
    couldn't be classified (e.g., insufficient history at start of series).
    """
    df = df.copy()
    df["compute_run_id"] = str(run_id)
    payload = df.reindex(columns=list(STATES_COLUMNS))
    required = [
        "rs_state",
        "momentum_state",
        "risk_state",
        "volume_state",
        "history_gate_pass",
        "liquidity_gate_pass",
        "weinstein_gate_pass",
        "stage1_base_qualifies",
    ]
    payload = payload.dropna(subset=required)
    return bulk_upsert(
        engine,
        table="atlas.atlas_stock_states_daily",
        columns=list(STATES_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["instrument_id", "date"],
    )


def run_stock_backfill(
    *,
    start: date | None = None,
    end: date | None = None,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Full historical backfill — methodology window 2016-04-07 → today.

    Splits no work in Python — entire universe loaded and computed in two
    pandas frames (metrics, states). Writes happen in 3,000-row pages via
    :func:`atlas.compute._session.bulk_upsert`.
    """
    eng = engine or get_engine()
    run_id = uuid.uuid4()
    started = time.time()

    start = start or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end or date.today()

    log.info("stock_backfill_start", run_id=str(run_id), start=str(start), end=str(end))

    universe = _load_universe(eng)
    log.info("universe_loaded", count=len(universe))

    thresholds = load_thresholds(eng)
    log.info("thresholds_loaded", count=len(thresholds))

    benchmark_cache = materialize_benchmark_cache(eng, start=start, end=end)
    event_dates = _load_event_dates(eng)

    ohlcv = _load_ohlcv(
        eng,
        instrument_ids=universe["instrument_id"].tolist(),
        start=start,
        end=end,
    )
    log.info("ohlcv_loaded", rows=len(ohlcv))

    metrics = _compute_stock_metrics(
        ohlcv,
        universe=universe,
        benchmark_cache=benchmark_cache,
        event_dates=event_dates,
        thresholds=thresholds,
    )
    log.info("compute_complete", rows=len(metrics))

    metric_rows = _write_metrics(eng, metrics, run_id)
    state_rows = _write_states(eng, metrics, run_id)

    finished = time.time()
    _log_run(
        eng,
        run_id=run_id,
        stage="M2_stock_backfill",
        status="SUCCESS",
        rows_written=metric_rows + state_rows,
        started_at=started,
        finished_at=finished,
    )
    return {
        "run_id": str(run_id),
        "metric_rows": metric_rows,
        "state_rows": state_rows,
        "duration_sec": round(finished - started, 1),
    }


def run_stock_daily(
    target_date: date,
    *,
    lookback_days: int = 400,
    engine: Engine | None = None,
) -> dict[str, object]:
    """Single-day incremental compute.

    Loads ``[target_date - lookback_days, target_date]`` so rolling windows
    have enough history, computes the full pipeline, but writes only rows
    for ``target_date``.
    """
    eng = engine or get_engine()
    run_id = uuid.uuid4()
    started = time.time()

    start = target_date - timedelta(days=lookback_days)
    log.info(
        "stock_daily_start",
        run_id=str(run_id),
        target=str(target_date),
        lookback_start=str(start),
    )

    universe = _load_universe(eng)
    thresholds = load_thresholds(eng)
    benchmark_cache = materialize_benchmark_cache(eng, start=start, end=target_date)
    event_dates = _load_event_dates(eng)
    ohlcv = _load_ohlcv(
        eng,
        instrument_ids=universe["instrument_id"].tolist(),
        start=start,
        end=target_date,
    )
    metrics = _compute_stock_metrics(
        ohlcv,
        universe=universe,
        benchmark_cache=benchmark_cache,
        event_dates=event_dates,
        thresholds=thresholds,
    )
    target_rows = metrics.loc[metrics["date"] == target_date]

    metric_rows = _write_metrics(eng, target_rows, run_id)
    state_rows = _write_states(eng, target_rows, run_id)

    finished = time.time()
    _log_run(
        eng,
        run_id=run_id,
        stage="M2_stock_daily",
        status="SUCCESS",
        rows_written=metric_rows + state_rows,
        started_at=started,
        finished_at=finished,
    )
    return {
        "run_id": str(run_id),
        "target_date": str(target_date),
        "metric_rows": metric_rows,
        "state_rows": state_rows,
        "duration_sec": round(finished - started, 1),
    }


__all__ = [
    "TIER_BENCHMARK",
    "run_stock_backfill",
    "run_stock_daily",
]
