"""Market regime classifier (M3 Phase C).

Per ``docs/00_METHODOLOGY_LOCK.md`` §11 and ``docs/02_DATABASE_SCHEMA.md``
§3.5 (``atlas_market_regime_daily``).

One row per trading day. The regime answers a single question — *how
aggressively should capital be deployed today?* — by combining four
families of breadth measures (Trend, MA Breadth, A/D Breadth, New Highs/Lows,
Strength Breadth) plus volatility into a four-state classification:

    Risk-On (1.0×) | Constructive (0.7×) | Cautious (0.4×) | Risk-Off (0.0×)

Plus a system-wide ``DISLOCATION_SUSPENDED`` override when 5-day realised
vol of NIFTY 500 exceeds ``dislocation_vol_multiplier`` × its trailing
252-day median (methodology §11.5).

Implementation pattern mirrors :mod:`atlas.compute.sectors`: pure functions
for each transform, an orchestrator that loads, computes, and writes.
"""
# allow-large: monolithic regime pipeline — loaders, breadth aggregation,
# dislocation override, state classification, and DB writers are a tightly
# coupled single-pass computation. Splitting would break the single-read
# guarantee needed on EC2 where two reads could see different pipeline states.

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
from atlas.compute.breadth import (
    compute_ad_line,
    compute_advances_declines,
    compute_ma_breadth,
    compute_mcclellan,
    compute_new_highs_lows,
    compute_pct_4w_high,
)
from atlas.compute.indices import INDIA_VIX_CODE, NIFTY500_CODE
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()


METRICS_COLUMNS: tuple[str, ...] = (
    "date",
    "nifty500_close",
    "nifty500_ema_50",
    "nifty500_ema_200",
    "nifty500_above_ema_50",
    "nifty500_above_ema_200",
    "nifty500_ema_50_slope",
    "nifty500_ema_200_slope",
    "pct_above_ema_20",
    "pct_above_ema_50",
    "pct_above_ema_100",
    "pct_above_ema_200",
    "pct_4w_high",
    "advances_count",
    "declines_count",
    "unchanged_count",
    "ad_ratio",
    "ad_line",
    "ad_line_slope_21",
    "mcclellan_oscillator",
    "mcclellan_summation",
    "new_52w_highs",
    "new_52w_lows",
    "net_new_highs",
    "new_high_low_ratio",
    "pct_in_strong_states",
    "pct_weinstein_pass",
    "india_vix",
    "realized_vol_5d_nifty500",
    "vol_252_median_nifty500",
    "regime_state",
    "deployment_multiplier",
    "dislocation_active",
    "dislocation_started",
    "compute_run_id",
)
"""Mirrors ``docs/02_DATABASE_SCHEMA.md`` §3.5 column order. Two columns
``pct_above_ema_20`` and ``nifty500_ema_50_slope`` are computed best-effort
and may be NaN where EMA20 isn't materialised in the stock table."""


# Regime state → multiplier mapping (methodology §11.4 + dislocation §11.5).
DEPLOYMENT_MULTIPLIERS: dict[str, float] = {
    "Risk-On": 1.0,
    "Constructive": 0.7,
    "Cautious": 0.4,
    "Risk-Off": 0.0,
    "DISLOCATION_SUSPENDED": 0.0,
}


# --------------------------------------------------------------------------- #
# Loaders                                                                     #
# --------------------------------------------------------------------------- #


def _load_stock_data_for_regime(
    engine: Engine,
    start_date: date,
    end_date: date,
    lookback_days: int = 900,
) -> pd.DataFrame:
    """Stock-level metrics + states needed for breadth computation.

    Pulls ``ema_50_stock``, ``ema_200_stock``, ``extension_pct`` (for
    ``close_approx``), plus ``rs_state`` and ``momentum_state`` for the
    strength-breadth family. Lookback feeds the 252d new-highs/lows window.
    """
    load_start = start_date - timedelta(days=lookback_days)
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                m.instrument_id,
                m.date,
                m.ema_50_stock,
                m.ema_200_stock,
                m.extension_pct,
                m.rs_1m_tier,
                s.rs_state,
                s.momentum_state,
                s.weinstein_gate_pass,
                COALESCE(o.close_adj, o.close) AS close_real
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id = m.instrument_id
                AND u.effective_to IS NULL
            LEFT JOIN atlas.atlas_stock_states_daily s
                ON s.instrument_id = m.instrument_id
                AND s.date = m.date
            LEFT JOIN public.de_equity_ohlcv o
                ON o.instrument_id = m.instrument_id
                AND o.date = m.date
            WHERE m.date BETWEEN %(start)s AND %(end)s
              AND u.in_nifty_500 = TRUE
            ORDER BY m.instrument_id, m.date
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )

    if df.empty:
        log.warning("regime_stock_data_empty", start=str(load_start), end=str(end_date))
        return df

    df["date"] = pd.to_datetime(df["date"]).dt.date
    # Breadth (new highs/lows, MA breadth) computes off close_approx. Use the
    # real adjusted close from de_equity_ohlcv — it is complete and reliable.
    # Fall back to the ema_200×(1+extension_pct) reconstruction only where the
    # OHLCV row is missing, so a sparse ema_200 column can never silently
    # collapse breadth to zero again (see 2026-05 breadth regression).
    close_real = df["close_real"].astype("float64")
    ema200 = df["ema_200_stock"].astype("float64")
    ext = df["extension_pct"].astype("float64")
    reconstructed = ema200 * (1.0 + ext)
    df["close_approx"] = close_real.where(close_real.notna(), reconstructed)
    return df


def _load_index_inputs(
    engine: Engine,
    start_date: date,
    end_date: date,
    lookback_days: int = 900,
) -> pd.DataFrame:
    """Per-date Nifty500 close + EMAs + INDIA VIX state.

    Schema §3.3 stores ``ema_10_index``, ``ema_20_index`` in
    ``atlas_index_metrics_daily``. The regime classifier wants 50 + 200 EMA
    of NIFTY 500 close; we derive these on-the-fly here from
    ``de_index_prices`` because the index pipeline doesn't materialise them.
    """
    load_start = start_date - timedelta(days=lookback_days)
    with open_compute_session(engine) as conn:
        prices = pd.read_sql(
            """
            SELECT index_code, date, close
            FROM public.de_index_prices
            WHERE index_code IN ('NIFTY 500', 'INDIA VIX')
              AND date BETWEEN %(start)s AND %(end)s
              AND close IS NOT NULL
            ORDER BY index_code, date
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )
        idx_metrics = pd.read_sql(
            """
            SELECT date, realized_vol_5d, vol_252_median
            FROM atlas.atlas_index_metrics_daily
            WHERE index_code = 'INDIA VIX'
              AND date BETWEEN %(start)s AND %(end)s
            """,
            conn,
            params={"start": load_start, "end": end_date},
        )

    prices["date"] = pd.to_datetime(prices["date"]).dt.date
    if not idx_metrics.empty:
        idx_metrics["date"] = pd.to_datetime(idx_metrics["date"]).dt.date

    # Nifty500 close + EMAs (50, 200) + 21-day slope on the EMAs.
    nifty = prices.loc[prices["index_code"] == NIFTY500_CODE, ["date", "close"]].copy()
    nifty = nifty.sort_values("date").reset_index(drop=True)
    nifty = nifty.rename(columns={"close": "nifty500_close"})
    nifty["nifty500_ema_50"] = (
        nifty["nifty500_close"].ewm(span=50, adjust=False, min_periods=50).mean()
    )
    nifty["nifty500_ema_200"] = (
        nifty["nifty500_close"].ewm(span=200, adjust=False, min_periods=200).mean()
    )
    nifty["nifty500_ema_50_slope"] = nifty["nifty500_ema_50"].pct_change(periods=21)
    nifty["nifty500_ema_200_slope"] = nifty["nifty500_ema_200"].pct_change(periods=21)
    nifty["nifty500_above_ema_50"] = nifty["nifty500_close"] > nifty["nifty500_ema_50"]
    nifty["nifty500_above_ema_200"] = nifty["nifty500_close"] > nifty["nifty500_ema_200"]

    # Realised vol 5d / 252d median — Nifty500-derived for dislocation override.
    n_ret = nifty["nifty500_close"].pct_change(periods=1)
    nifty["realized_vol_5d_nifty500"] = n_ret.rolling(5, min_periods=3).std() * np.sqrt(252)
    daily_vol = n_ret.abs() * np.sqrt(252)
    nifty["vol_252_median_nifty500"] = daily_vol.rolling(252, min_periods=120).median()

    # India VIX level — closing level on each date.
    vix = prices.loc[prices["index_code"] == INDIA_VIX_CODE, ["date", "close"]].rename(
        columns={"close": "india_vix"}
    )

    # VIX 5d realised vol vs 252d median — for the dislocation override.
    if not idx_metrics.empty:
        vix = vix.merge(idx_metrics, on="date", how="left")
        vix["vix_5d_realized_vol_ratio"] = vix["realized_vol_5d"] / vix["vol_252_median"].replace(
            0, np.nan
        )
    else:
        vix["vix_5d_realized_vol_ratio"] = np.nan

    out = nifty.merge(vix, on="date", how="left")
    return out


# --------------------------------------------------------------------------- #
# Strength breadth                                                            #
# --------------------------------------------------------------------------- #


def _compute_strength_breadth(df_stocks: pd.DataFrame) -> pd.DataFrame:
    """Per-date ``pct_in_strong_states`` and ``pct_weinstein_pass``.

    * ``pct_in_strong_states`` — fraction of stocks with rs_state in
      {Leader, Strong, Emerging} per methodology §11.1 strength breadth.
    * ``pct_weinstein_pass`` — fraction with ``weinstein_gate_pass = True``.
    * ``pct_stocks_rs_positive`` — fraction with ``rs_1m_tier > 0``
      (rs_1m_tier is a difference, so positive means outperforming).
    * ``pct_stocks_momentum_positive`` — fraction with momentum_state in
      {Improving, Accelerating}.
    """
    if df_stocks.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "pct_in_strong_states",
                "pct_weinstein_pass",
                "pct_stocks_rs_positive",
                "pct_stocks_momentum_positive",
            ]
        )

    work = df_stocks[
        [
            "date",
            "rs_state",
            "momentum_state",
            "weinstein_gate_pass",
            "rs_1m_tier",
        ]
    ].copy()

    strong_set = {"Leader", "Strong", "Emerging"}
    momentum_pos = {"Improving", "Accelerating"}

    work["is_strong"] = work["rs_state"].isin(strong_set).astype(int)
    work["is_weinstein"] = work["weinstein_gate_pass"].fillna(False).astype(int)
    work["is_rs_positive"] = (work["rs_1m_tier"] > 0).fillna(False).astype(int)
    work["is_momentum_positive"] = work["momentum_state"].isin(momentum_pos).astype(int)

    grouped = work.groupby("date", observed=True)[
        ["is_strong", "is_weinstein", "is_rs_positive", "is_momentum_positive"]
    ].mean()

    grouped = grouped.rename(
        columns={
            "is_strong": "pct_in_strong_states",
            "is_weinstein": "pct_weinstein_pass",
            "is_rs_positive": "pct_stocks_rs_positive",
            "is_momentum_positive": "pct_stocks_momentum_positive",
        }
    )
    return grouped.reset_index()


# --------------------------------------------------------------------------- #
# Composite regime inputs                                                     #
# --------------------------------------------------------------------------- #


def compute_regime_inputs(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Build the per-date frame with all 18+ regime inputs.

    Returns a date-indexed long frame. Output columns align with
    :data:`METRICS_COLUMNS` minus the classification columns
    (``regime_state``, ``deployment_multiplier``, ``dislocation_active``,
    ``dislocation_started``, ``compute_run_id``).
    """
    stock_data = _load_stock_data_for_regime(engine, start_date, end_date)
    idx_inputs = _load_index_inputs(engine, start_date, end_date)

    # Breadth frames keyed by date.
    ad = compute_advances_declines(stock_data)
    ad = compute_ad_line(ad)
    ad = compute_mcclellan(ad)
    nh = compute_new_highs_lows(stock_data)
    ma = compute_ma_breadth(stock_data)
    p4wh = compute_pct_4w_high(stock_data)
    sb = _compute_strength_breadth(stock_data)

    # ``ad`` is the master per-date scaffold (every trading day with ≥1 stock
    # has an entry). Outer-join the rest.
    out = (
        ad.merge(nh, on="date", how="outer")
        .merge(ma, on="date", how="outer")
        .merge(p4wh, on="date", how="outer")
        .merge(sb, on="date", how="outer")
        .merge(idx_inputs, on="date", how="outer")
    )
    out = out.sort_values("date").reset_index(drop=True)

    # MA-breadth (20/50/100/200) and 4-week-high are now computed above; any
    # column the merge didn't produce (e.g. an empty universe slice) is carried
    # through as NaN so the upsert column set stays stable.
    for _col in ("pct_above_ema_20", "pct_above_ema_100", "pct_4w_high"):
        if _col not in out.columns:
            out[_col] = np.nan

    # ``ad_line_slope_21`` — 21-day slope (pct_change-equivalent) of A/D line.
    out["ad_line_slope_21"] = out["ad_line"].pct_change(periods=21)

    # Rename to schema column names where they differ.
    rename_map = {
        "advances": "advances_count",
        "declines": "declines_count",
        "unchanged": "unchanged_count",
        "advance_decline_ratio": "ad_ratio",
    }
    out = out.rename(columns=rename_map)

    return out


# --------------------------------------------------------------------------- #
# Classification                                                              #
# --------------------------------------------------------------------------- #


def classify_regime_state(
    df_inputs: pd.DataFrame,
    df_thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Apply methodology §11.4 — Risk-On / Constructive / Cautious / Risk-Off.

    Rules (all conditions must hold for that state):

        Risk-On      — Nifty500>EMA200 AND pct_above_ema_50>risk_on_min AND VIX<risk_on_vix_max
        Constructive — Nifty500>EMA200 AND pct_above_ema_50 in [constr_min,risk_on_min]
                       AND VIX<constr_vix_max
        Cautious     — |Nifty500-EMA200|<=near_band OR breadth_deteriorating
                       OR VIX in [constr_vix, cautious_vix]
        Risk-Off     — Nifty500<EMA200 AND pct_above_ema_50<risk_off_max AND VIX>cautious_vix

    Args:
        df_inputs: output of :func:`compute_regime_inputs`.
        df_thresholds: ``atlas_thresholds`` dict (percent values; we /100 here).

    Returns:
        Same frame with ``regime_state`` and ``deployment_multiplier`` added.
        Order of evaluation is Risk-Off → Risk-On → Constructive → Cautious →
        default Cautious so the most-restrictive call wins on ties.
    """
    if df_inputs.empty:
        out = df_inputs.copy()
        out["regime_state"] = pd.Series(dtype="object")
        out["deployment_multiplier"] = pd.Series(dtype="float64")
        return out

    out = df_inputs.copy()

    # All thresholds stored as percent → fraction. Convert to float for pandas
    # Series comparison (Decimal / float raises TypeError; Decimal / int is fine
    # but pandas needs float scalars for clean dtype handling).
    risk_on_min = float(df_thresholds["regime_risk_on_breadth_min_pct"]) / 100.0
    constr_min = float(df_thresholds["regime_constructive_breadth_min_pct"]) / 100.0
    risk_off_max = float(df_thresholds["regime_risk_off_breadth_max_pct"]) / 100.0
    risk_on_vix = float(df_thresholds["regime_risk_on_vix_max"])
    constr_vix = float(df_thresholds["regime_constructive_vix_max"])
    cautious_vix = float(df_thresholds["regime_cautious_vix_max"])
    near_200_band = float(df_thresholds["regime_near_200ema_band_pct"]) / 100.0

    above_200 = out["nifty500_above_ema_200"].fillna(False).astype(bool)
    pct_50 = out["pct_above_ema_50"].astype("float64")
    vix = out["india_vix"].astype("float64")

    # Near 200 EMA band: |close/ema200 - 1| ≤ near_band
    close = out["nifty500_close"].astype("float64")
    ema200 = out["nifty500_ema_200"].astype("float64")
    near_200 = ((close / ema200 - 1).abs() <= near_200_band) & ema200.notna()

    # Breadth deteriorating: pct_above_ema_50 dropped > 5 pts over 21 days.
    breadth_drop = out["pct_above_ema_50"].diff(periods=21)
    breadth_deteriorating = (breadth_drop < -0.05).fillna(False)

    # When VIX is NaN (data gap / holiday), treat it as non-contributory to any
    # condition: don't let it block Risk-On and don't use it to trigger Risk-Off.
    # Breadth + price trend drive the regime on VIX-gap dates.
    vix_valid = vix.notna()
    is_risk_on = above_200 & (pct_50 > risk_on_min) & (~vix_valid | (vix < risk_on_vix))
    is_constructive = (
        above_200
        & (pct_50 >= constr_min)
        & (pct_50 <= risk_on_min)
        & (~vix_valid | (vix < constr_vix))
    )
    is_risk_off = (~above_200) & (pct_50 < risk_off_max) & vix_valid & (vix > cautious_vix)
    is_cautious = (
        near_200 | breadth_deteriorating | (vix_valid & (vix >= constr_vix) & (vix <= cautious_vix))
    )

    # Order of priority: Risk-Off (most-restrictive) → Risk-On → Constructive
    # → Cautious → default Cautious. We deliberately let Risk-Off win ties
    # against Cautious so a deteriorating market with high VIX is properly
    # called Risk-Off.
    out["regime_state"] = np.select(
        [is_risk_off, is_risk_on, is_constructive, is_cautious],
        ["Risk-Off", "Risk-On", "Constructive", "Cautious"],
        default="Cautious",
    )
    out["deployment_multiplier"] = out["regime_state"].map(DEPLOYMENT_MULTIPLIERS).astype("float64")

    # Where price + breadth inputs are both absent (early-history warm-up), null
    # out the state. VIX gap alone is handled above via vix_valid guards.
    no_inputs = pct_50.isna() & close.isna()
    out.loc[no_inputs, "regime_state"] = None
    out.loc[no_inputs, "deployment_multiplier"] = np.nan

    return out


# --------------------------------------------------------------------------- #
# Dislocation override                                                        #
# --------------------------------------------------------------------------- #


def apply_dislocation_override(
    df_classified: pd.DataFrame,
    df_thresholds: Mapping[str, Decimal] | None = None,
    *,
    persist_days: int = 5,
) -> pd.DataFrame:
    """Override regime to ``DISLOCATION_SUSPENDED`` when vol explodes.

    Per methodology §11.5: when 5d realised vol of NIFTY 500 exceeds
    ``dislocation_vol_multiplier`` × its 252d median, all classifications
    suspend. Resumption requires ``persist_days`` consecutive trading days
    of normalised vol, so we use a forward-rolling max to keep the flag set
    for ``persist_days`` after the last trigger.

    Args:
        df_classified: output of :func:`classify_regime_state`.
        df_thresholds: ``atlas_thresholds`` dict; uses
            ``dislocation_vol_multiplier`` (default 4.0).
        persist_days: trading days the override stays on after last trigger.

    Returns:
        Same frame with ``dislocation_active``, ``dislocation_started``
        columns set, and ``regime_state`` / ``deployment_multiplier``
        overridden where the override fires. Adds ``vix_5d_realized_vol_ratio``
        as a documented side-output for downstream validators (NOT a schema
        column — dropped by the writer).
    """
    if df_classified.empty:
        out = df_classified.copy()
        out["dislocation_active"] = pd.Series(dtype="bool")
        out["dislocation_started"] = pd.Series(dtype="object")
        return out

    out = df_classified.sort_values("date").reset_index(drop=True).copy()

    multiplier = float((df_thresholds or {}).get("dislocation_vol_multiplier", 4.0))

    # Trigger uses Nifty500-derived 5d vol vs 252d median per methodology
    # §11.5. NULL guard: if either input is NaN, treat trigger as False.
    realized = out.get("realized_vol_5d_nifty500")
    median = out.get("vol_252_median_nifty500")

    if realized is None or median is None:
        trigger = pd.Series(False, index=out.index)
    else:
        ratio = realized.astype("float64") / median.replace(0, np.nan).astype("float64")
        trigger = (ratio > multiplier).fillna(False)

    # Persist for ``persist_days`` after the last trigger using a backwards-
    # rolling max (so day t is "active" if any trigger fired in [t-persist+1, t]).
    active = trigger.rolling(persist_days, min_periods=1).max().astype(bool)
    out["dislocation_active"] = active.values

    # dislocation_started = first date inside the most-recent active streak.
    streak_id = (active != active.shift(fill_value=False)).cumsum()
    started_per_streak = (
        out.loc[active]
        .assign(streak_id=streak_id[active])
        .groupby("streak_id")["date"]
        .transform("first")
    )
    out["dislocation_started"] = pd.NaT
    if not started_per_streak.empty:
        out.loc[active, "dislocation_started"] = started_per_streak.values

    # Override the regime state where active.
    override_mask = out["dislocation_active"].astype(bool)
    out.loc[override_mask, "regime_state"] = "DISLOCATION_SUSPENDED"
    out.loc[override_mask, "deployment_multiplier"] = 0.0

    return out


# --------------------------------------------------------------------------- #
# DB writers                                                                  #
# --------------------------------------------------------------------------- #


_VALID_SCHEMAS = frozenset({"atlas", "us_atlas", "global_atlas"})


def _write_metrics(
    engine: Engine,
    df: pd.DataFrame,
    run_id: uuid.UUID,
    schema: str = "atlas",
) -> int:
    if schema not in _VALID_SCHEMAS:
        raise ValueError(f"_write_metrics: schema must be one of {_VALID_SCHEMAS}, got {schema!r}")
    if df.empty:
        return 0
    df = df.copy()
    df = df.replace([np.inf, -np.inf], np.nan)
    df["compute_run_id"] = str(run_id)

    # Coerce integer-typed columns through Int64 to handle NaN gracefully.
    int_cols = (
        "advances_count",
        "declines_count",
        "unchanged_count",
        "new_52w_highs",
        "new_52w_lows",
        "net_new_highs",
    )
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Sanity: drop rows without a regime state — schema says NOT NULL.
    df = df.dropna(subset=["regime_state", "deployment_multiplier"])

    payload = df.reindex(columns=list(METRICS_COLUMNS))
    return bulk_upsert(
        engine,
        table=f"{schema}.atlas_market_regime_daily",
        columns=list(METRICS_COLUMNS),
        rows=df_to_pg_rows(payload),
        pk_columns=["date"],
    )


# --------------------------------------------------------------------------- #
# Top-level runners                                                           #
# --------------------------------------------------------------------------- #


def _run_pipeline(
    engine: Engine,
    *,
    start: date,
    end: date,
    write_start: date | None = None,
    schema: str = "atlas",
) -> dict[str, object]:
    """Shared orchestration for backfill + daily."""
    run_id = uuid.uuid4()
    started = time.time()

    log.info(
        "regime_pipeline_start",
        run_id=str(run_id),
        start=str(start),
        end=str(end),
        schema=schema,
    )

    thresholds = load_thresholds(schema=schema, engine=engine)
    inputs = compute_regime_inputs(engine, start_date=start, end_date=end)
    classified = classify_regime_state(inputs, thresholds)
    final = apply_dislocation_override(classified, thresholds)

    if write_start is not None:
        final = final.loc[final["date"] >= write_start].copy()

    rows = _write_metrics(engine, final, run_id, schema=schema)
    duration = round(time.time() - started, 1)
    log.info(
        "regime_pipeline_complete",
        run_id=str(run_id),
        rows_written=rows,
        duration_sec=duration,
    )
    return {
        "run_id": str(run_id),
        "rows_written": rows,
        "duration_sec": duration,
    }


def backfill_regime(
    engine: Engine | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    schema: str = "atlas",
) -> int:
    """Full historical backfill (default: HISTORICAL_START_DATE → today)."""
    eng = engine or get_engine()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()
    result = _run_pipeline(eng, start=start, end=end, write_start=start, schema=schema)
    return int(str(result["rows_written"]))


def run_daily_regime(engine: Engine | None = None, schema: str = "atlas") -> int:
    """Incremental run for the most recent ~10 calendar days."""
    eng = engine or get_engine()
    today = date.today()
    window_start = today - timedelta(days=10)
    result = _run_pipeline(
        eng, start=window_start, end=today, write_start=window_start, schema=schema
    )
    return int(str(result["rows_written"]))


__all__ = [
    "DEPLOYMENT_MULTIPLIERS",
    "METRICS_COLUMNS",
    "apply_dislocation_override",
    "backfill_regime",
    "classify_regime_state",
    "compute_regime_inputs",
    "run_daily_regime",
]
