"""Daily regime cron (#44).

Computes the 4 regime inputs from production data and writes one row to
``atlas.atlas_regime_daily`` per target_date.

Inputs (all derived at ``target_date`` using only data ``<= target_date`` —
look-ahead audit point #1: structural ``WHERE date <= :end`` in the queries):

* ``smallcap_rs_z`` — rolling z-score of ``log(Nifty Smallcap 250 / NIFTY 500)``
  over a trailing ``lookback_days`` window. Captures small-cap risk-on/off.
* ``breadth_pct_above_200dma`` — fraction of M1 universe with ``close > 200d SMA``
  at ``target_date``. Sourced from ``de_equity_ohlcv`` joined to the
  ``atlas_universe_stocks`` active universe (the same universe the scorecard
  writer uses, so the two stay in lock-step).
* ``vix_percentile`` — where today's ``INDIA VIX`` falls in the trailing 252d
  distribution. ``NaN`` when VIX is unavailable (e.g. pre-2018) — ``vix_valid``
  flag passed through to :func:`classify`.
* ``cross_sectional_dispersion`` — standard deviation of trailing-20d returns
  across the M1 universe at ``target_date``. High = stock-pickers' market.

Thresholds: loaded via :func:`atlas.db.load_thresholds`. The Phase 0.5h-prime
sweep (#16) ships real values keyed under ``regime.*`` (e.g.
``regime.smallcap_rs_z.risk_off_threshold``). When the keys are absent — the
v6 launch state per migration 089 — we fall back to the hardcoded defaults
in :class:`RegimeThresholds`. The returned :class:`RegimeWriteResult` records
``threshold_source`` so callers can tell which path fired.

Write semantics: ``atlas_regime_daily`` has a ``UNIQUE`` constraint on
``date`` — this cron is INSERT-OR-UPDATE on ``date``. Calling it twice for
the same target_date leaves exactly one row carrying the latest values.

Rule-based per CEO plan Principle 2 — pure pandas/numpy vectorised; no ML.
"""

# allow-large: single cohesive daily-cron pipeline — loaders, four input
# computations, threshold resolution, write helper, entry point — forms one
# indivisible compute unit. Same shape as atlas/features/scorecard_writer.py:
# splitting would force shared mutable-frame plumbing across modules with no
# clean public seam (the helpers all share the same target_date + engine).

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, open_compute_session
from atlas.db import get_engine, load_thresholds
from atlas.regime.classifier import (
    RegimeInputs,
    RegimeState,
    RegimeThresholds,
    classify,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Trailing windows (trading days)
SMALLCAP_RS_WINDOW = 252  # 1Y z-score
VIX_PCT_WINDOW = 252
BREADTH_SMA_WINDOW = 200
DISPERSION_WINDOW = 20

# Index codes — exact JIP `index_code` strings (see atlas/preflight.py).
INDEX_CODE_BROAD = "NIFTY 500"
INDEX_CODE_SMALLCAP = "NIFTY SMLCAP 250"
INDEX_CODE_VIX = "INDIA VIX"

# Threshold keys probed in atlas_thresholds. Absent at v6 launch (migration
# 089 §"atlas_thresholds regime placeholder rows — SKIPPED"); Phase 0.5h-prime
# sweep (#16) writes the real numeric values keyed under this namespace.
_THRESHOLD_KEYS: dict[str, str] = {
    "smallcap_rs_z_below_trend": "regime.smallcap_rs_z.below_trend_threshold",
    "smallcap_rs_z_risk_off": "regime.smallcap_rs_z.risk_off_threshold",
    "breadth_below_trend": "regime.breadth.below_trend_threshold",
    "breadth_risk_off": "regime.breadth.risk_off_threshold",
    "vix_pct_elevated": "regime.vix_percentile.elevated_threshold",
    "vix_pct_risk_off": "regime.vix_percentile.risk_off_threshold",
    "dispersion_elevated": "regime.dispersion.elevated_threshold",
}

ThresholdSource = Literal["atlas_thresholds", "fallback"]


# ---------------------------------------------------------------------------
# Return contract
# ---------------------------------------------------------------------------


@dataclass
class RegimeWriteResult:
    """Outcome of one :func:`compute_daily_regime` invocation."""

    target_date: date | None = None
    state: RegimeState | None = None
    # Input drivers actually written (post-NaN normalisation)
    smallcap_rs_z: float | None = None
    breadth_pct_above_200dma: float | None = None
    vix_percentile: float | None = None
    cross_sectional_dispersion: float | None = None
    vix_valid: bool = True
    threshold_source: ThresholdSource = "fallback"
    rows_written: int = 0
    runtime_seconds: float = 0.0
    # Diagnostic counts — surfaced via structlog too.
    universe_size: int = 0
    breadth_eligible_count: int = 0
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Threshold loading with fallback
# ---------------------------------------------------------------------------


def _resolve_thresholds(
    raw: Mapping[str, Decimal] | None,
) -> tuple[RegimeThresholds, ThresholdSource]:
    """Build a :class:`RegimeThresholds` from a loaded ``atlas_thresholds`` map.

    Returns ``("atlas_thresholds", th)`` only if EVERY required key is present
    in ``raw``. Otherwise falls back to the hardcoded defaults — partial
    overrides are deliberately rejected to avoid mixing OOS-locked values
    with placeholder defaults silently (an unsigned methodology change).
    """
    defaults = RegimeThresholds()
    if not raw:
        return defaults, "fallback"

    resolved: dict[str, float] = {}
    for field_name, key in _THRESHOLD_KEYS.items():
        if key not in raw:
            return defaults, "fallback"
        try:
            resolved[field_name] = float(raw[key])
        except (TypeError, ValueError):
            return defaults, "fallback"

    return RegimeThresholds(**resolved), "atlas_thresholds"


# ---------------------------------------------------------------------------
# Loaders — all clamp to date <= target_date (look-ahead audit point #1).
# ---------------------------------------------------------------------------


def _load_index_close(
    engine: Engine,
    *,
    index_code: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Load ``(date, close)`` for ``index_code`` over ``[start, end]``.

    Empty frame returned when the index is missing or has no rows in window.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, close
            FROM public.de_index_prices
            WHERE index_code = %(code)s
              AND date BETWEEN %(start)s AND %(end)s
              AND close IS NOT NULL
            ORDER BY date
            """,
            conn,
            params={"code": index_code, "start": start, "end": end},
        )
    if df.empty:
        log.warning(
            "regime_index_empty",
            index_code=index_code,
            start=str(start),
            end=str(end),
        )
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["close"] = df["close"].astype("float64")
    return df


def _load_universe_ohlcv(
    engine: Engine,
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Long-frame OHLCV for the active M1 universe over ``[start, end]``.

    Joined server-side to ``atlas_universe_stocks`` so we get exactly the
    M1 universe (same set the scorecard writer uses). Look-ahead audit point
    #1 — ``date <= :end``.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                o.instrument_id::text AS instrument_id,
                o.date,
                COALESCE(o.close_adj, o.close) AS close
            FROM public.de_equity_ohlcv AS o
            JOIN atlas.atlas_universe_stocks AS u
              ON u.instrument_id = o.instrument_id
             AND u.effective_to IS NULL
            WHERE o.date BETWEEN %(start)s AND %(end)s
              AND o.close IS NOT NULL
            ORDER BY o.instrument_id, o.date
            """,
            conn,
            params={"start": start, "end": end},
        )
    if df.empty:
        log.warning("regime_ohlcv_empty", start=str(start), end=str(end))
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["close"] = df["close"].astype("float64")
    return df


# ---------------------------------------------------------------------------
# Input computations — all pure functions on dataframes.
# ---------------------------------------------------------------------------


def compute_smallcap_rs_z(
    smallcap: pd.DataFrame,
    broad: pd.DataFrame,
    target_date: date,
    *,
    window: int = SMALLCAP_RS_WINDOW,
) -> float:
    """Rolling z-score of ``log(smallcap_close / broad_close)`` at ``target_date``.

    The RS *line* is dimensionless ``log(small / broad)``. We compute its
    trailing-``window`` mean and std and report ``(value_today - mean) / std``.
    Returns ``nan`` when either index is empty or has insufficient history.
    """
    if smallcap.empty or broad.empty:
        return float("nan")

    # Look-ahead audit point #2 — runtime guard.
    assert (smallcap["date"] <= target_date).all(), "regime: smallcap data past target_date"
    assert (broad["date"] <= target_date).all(), "regime: broad data past target_date"

    merged = pd.merge(
        smallcap.rename(columns={"close": "smallcap_close"}),
        broad.rename(columns={"close": "broad_close"}),
        on="date",
        how="inner",
    ).sort_values("date")
    if merged.empty:
        return float("nan")

    # Guard zero / negative denominators (defensive — index closes should
    # never be <= 0 but pattern follows global rule "Division guards").
    broad_clean = merged["broad_close"].replace(0, np.nan)
    rs = np.log(merged["smallcap_close"] / broad_clean)

    # Need at least ``window`` rows for a meaningful z-score; if fewer, use
    # what we have (min_periods relaxed) but log it.
    min_periods = min(window, max(int(window // 2), 30))
    if len(rs.dropna()) < min_periods:
        log.warning(
            "regime_smallcap_rs_z_insufficient",
            available=len(rs.dropna()),
            min_periods=min_periods,
            target_date=str(target_date),
        )
        return float("nan")

    mean_ = rs.rolling(window, min_periods=min_periods).mean().iloc[-1]
    std_ = rs.rolling(window, min_periods=min_periods).std().iloc[-1]
    today = rs.iloc[-1]

    if pd.isna(mean_) or pd.isna(std_) or std_ == 0 or pd.isna(today):
        return float("nan")
    return float((today - mean_) / std_)


def compute_vix_percentile(
    vix: pd.DataFrame,
    target_date: date,
    *,
    window: int = VIX_PCT_WINDOW,
) -> tuple[float, bool]:
    """Percentile rank of today's VIX close in the trailing ``window``.

    Returns ``(percentile_in_[0,1], vix_valid)``. ``vix_valid=False`` (and
    ``percentile=nan``) when VIX is missing — caller passes through to
    :func:`classify` per the global VIX-NaN rule.
    """
    if vix.empty:
        return float("nan"), False
    assert (vix["date"] <= target_date).all(), "regime: vix data past target_date"

    series = vix.sort_values("date")["close"].dropna()
    if series.empty:
        return float("nan"), False
    tail = series.tail(window)
    if len(tail) < 30:  # min sample for a meaningful percentile
        log.warning(
            "regime_vix_pct_insufficient",
            available=len(tail),
            target_date=str(target_date),
        )
        return float("nan"), False

    today = float(tail.iloc[-1])
    # Fraction strictly below today + half of ties = rank-based percentile.
    below = (tail < today).sum()
    equal = (tail == today).sum()
    pct = (below + 0.5 * equal) / float(len(tail))
    return float(pct), True


def compute_breadth_pct_above_200dma(
    ohlcv_long: pd.DataFrame,
    target_date: date,
    *,
    window: int = BREADTH_SMA_WINDOW,
) -> tuple[float, int]:
    """Fraction of universe trading above its 200d SMA at ``target_date``.

    Vectorised — ``groupby + transform`` computes the 200d rolling mean per
    instrument in C; the snapshot row at ``target_date`` is then filtered.
    Returns ``(fraction_in_[0,1], n_instruments_eligible)``.
    """
    if ohlcv_long.empty:
        return float("nan"), 0
    assert (ohlcv_long["date"] <= target_date).all(), "regime: ohlcv past target_date"

    df = ohlcv_long.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # 200d SMA per instrument — vectorised.
    df["sma_200d"] = df.groupby("instrument_id", group_keys=False, observed=True)[
        "close"
    ].transform(lambda s: s.rolling(window, min_periods=window // 2).mean())

    snap = df.loc[df["date"] == target_date, ["instrument_id", "close", "sma_200d"]].copy()
    snap = snap.dropna(subset=["close", "sma_200d"])
    if snap.empty:
        log.warning(
            "regime_breadth_no_snap",
            target_date=str(target_date),
            window=window,
        )
        return float("nan"), 0

    above = (snap["close"] > snap["sma_200d"]).sum()
    n = len(snap)
    return float(above) / float(n), n


def compute_cross_sectional_dispersion(
    ohlcv_long: pd.DataFrame,
    target_date: date,
    *,
    window: int = DISPERSION_WINDOW,
) -> float:
    """Std of trailing-``window`` returns across the universe at ``target_date``.

    Per instrument: ``ret_window = close_T / close_{T-window} - 1``. Then
    take the cross-sectional std of those scalars. High = stock-pickers'
    market (Elevated leg). Vectorised — no Python loop.
    """
    if ohlcv_long.empty:
        return float("nan")
    assert (ohlcv_long["date"] <= target_date).all(), "regime: ohlcv past target_date"

    df = ohlcv_long.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # Per-instrument: close at T and close at T-window via shift.
    df["close_lag"] = df.groupby("instrument_id", group_keys=False, observed=True)["close"].shift(
        window
    )

    snap = df.loc[df["date"] == target_date, ["instrument_id", "close", "close_lag"]].copy()
    snap = snap.dropna(subset=["close", "close_lag"])
    # Division guard per global rule.
    snap["close_lag"] = snap["close_lag"].replace(0, np.nan)
    snap = snap.dropna(subset=["close_lag"])
    if snap.empty:
        log.warning(
            "regime_dispersion_no_snap",
            target_date=str(target_date),
            window=window,
        )
        return float("nan")

    rets = (snap["close"].astype("float64") / snap["close_lag"].astype("float64")) - 1.0
    if len(rets) < 2:
        return float("nan")
    return float(rets.std(ddof=1))


# ---------------------------------------------------------------------------
# Write helper
# ---------------------------------------------------------------------------


_REGIME_COLUMNS: tuple[str, ...] = (
    "date",
    "state",
    "smallcap_rs_z",
    "breadth_pct_above_200dma",
    "vix_percentile",
    "cross_sectional_dispersion",
)


def _to_decimal(value: float | None, places: int) -> Decimal | None:
    """Pandas/numpy → Decimal, with NaN/Inf → ``None``."""
    if value is None:
        return None
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    quant = Decimal(10) ** -places
    return Decimal(str(round(float(value), places))).quantize(quant)


def _write_row(
    engine: Engine,
    *,
    target_date: date,
    state: RegimeState,
    smallcap_rs_z: float | None,
    breadth: float | None,
    vix_pct: float | None,
    dispersion: float | None,
) -> int:
    """INSERT/UPSERT a single row into ``atlas.atlas_regime_daily``."""
    row = (
        target_date,
        state.value,
        _to_decimal(smallcap_rs_z, 4),
        _to_decimal(breadth, 4),
        _to_decimal(vix_pct, 4),
        _to_decimal(dispersion, 6),
    )
    return bulk_upsert(
        engine,
        table="atlas.atlas_regime_daily",
        columns=list(_REGIME_COLUMNS),
        rows=[row],
        pk_columns=["date"],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compute_daily_regime(
    target_date: date,
    db_engine: Engine | None = None,
    *,
    lookback_days: int = 252,
    write: bool = True,
) -> RegimeWriteResult:
    """Daily cron: classify the regime at ``target_date`` and write the row.

    Args:
        target_date: the date to classify. All inputs use data ``<= target_date``.
        db_engine: optional engine override; defaults to the process-wide
            engine via :func:`atlas.db.get_engine`.
        lookback_days: how many calendar days of history to load. Default 252
            covers all the rolling windows (smallcap z, vix percentile, 200d SMA).
            Pre-2018 dates may want a wider window so the smallcap RS history
            covers the full ``SMALLCAP_RS_WINDOW``.
        write: when ``False``, compute everything but skip the DB write.
            Useful for backfill dry-runs.

    Returns:
        :class:`RegimeWriteResult` carrying the classified state, the 4 input
        drivers, the threshold source, and diagnostic counts.
    """
    engine = db_engine or get_engine()
    started = time.time()
    result = RegimeWriteResult(target_date=target_date)

    log.info(
        "regime_cron_start",
        target_date=str(target_date),
        lookback_days=lookback_days,
        write=write,
    )

    # Load all 4 inputs' raw history. We pull more than `lookback_days` for
    # the smallcap_rs window — the z-score needs 1Y history.
    rs_start = target_date - timedelta(days=max(lookback_days, SMALLCAP_RS_WINDOW) + 60)
    breadth_start = target_date - timedelta(days=max(lookback_days, BREADTH_SMA_WINDOW) + 60)
    vix_start = target_date - timedelta(days=max(lookback_days, VIX_PCT_WINDOW) + 60)
    disp_start = target_date - timedelta(days=max(DISPERSION_WINDOW * 3, 60))

    # Calendar starts can collide; pick the earliest so a single OHLCV load
    # covers both breadth and dispersion.
    ohlcv_start = min(breadth_start, disp_start)

    smallcap = _load_index_close(
        engine, index_code=INDEX_CODE_SMALLCAP, start=rs_start, end=target_date
    )
    broad = _load_index_close(engine, index_code=INDEX_CODE_BROAD, start=rs_start, end=target_date)
    vix = _load_index_close(engine, index_code=INDEX_CODE_VIX, start=vix_start, end=target_date)
    ohlcv = _load_universe_ohlcv(engine, start=ohlcv_start, end=target_date)
    result.universe_size = int(ohlcv["instrument_id"].nunique()) if not ohlcv.empty else 0

    # Inputs
    smallcap_rs_z = compute_smallcap_rs_z(smallcap, broad, target_date)
    vix_pct, vix_valid = compute_vix_percentile(vix, target_date)
    breadth_pct, breadth_n = compute_breadth_pct_above_200dma(ohlcv, target_date)
    dispersion = compute_cross_sectional_dispersion(ohlcv, target_date)

    result.smallcap_rs_z = None if np.isnan(smallcap_rs_z) else smallcap_rs_z
    result.vix_percentile = None if np.isnan(vix_pct) else vix_pct
    result.vix_valid = vix_valid
    result.breadth_pct_above_200dma = None if np.isnan(breadth_pct) else breadth_pct
    result.breadth_eligible_count = breadth_n
    result.cross_sectional_dispersion = None if np.isnan(dispersion) else dispersion

    # Thresholds — load and resolve. Partial keys → fallback (see _resolve_thresholds).
    try:
        raw_thresholds = load_thresholds(engine=engine)
    except (ValueError, RuntimeError, OSError) as exc:
        # If threshold load fails (e.g. table missing in test env), fall back
        # to defaults but record the issue. Never let threshold I/O block the
        # regime write — the placeholder defaults are valid OOS-unverified
        # values per CONTEXT.md.
        log.warning("regime_threshold_load_failed", error=str(exc))
        raw_thresholds = None
    th, th_src = _resolve_thresholds(raw_thresholds)
    result.threshold_source = th_src

    # Classify — feeding the *resolved* numeric inputs and the vix_valid flag.
    # NaN handling: if any non-VIX input is NaN, the conservative call is to
    # treat it as a missing leg by clamping to a non-firing value. Risk-Off
    # smallcap leg requires z <= -2; using +0 lets the leg no-op. Same for
    # breadth (use 1.0 = full participation, no-op) and dispersion (0.0).
    safe_z = result.smallcap_rs_z if result.smallcap_rs_z is not None else 0.0
    safe_breadth = (
        result.breadth_pct_above_200dma if result.breadth_pct_above_200dma is not None else 1.0
    )
    safe_dispersion = (
        result.cross_sectional_dispersion if result.cross_sectional_dispersion is not None else 0.0
    )
    safe_vix = result.vix_percentile if result.vix_percentile is not None else 0.0

    inputs = RegimeInputs(
        smallcap_rs_z=safe_z,
        breadth_pct_above_200dma=safe_breadth,
        vix_percentile=safe_vix,
        cross_sectional_dispersion=safe_dispersion,
    )
    state = classify(inputs, thresholds=th, vix_valid=vix_valid)
    result.state = state

    log.info(
        "regime_classified",
        target_date=str(target_date),
        state=state.value,
        smallcap_rs_z=result.smallcap_rs_z,
        breadth=result.breadth_pct_above_200dma,
        breadth_n=result.breadth_eligible_count,
        vix_percentile=result.vix_percentile,
        vix_valid=vix_valid,
        dispersion=result.cross_sectional_dispersion,
        threshold_source=th_src,
        universe_size=result.universe_size,
    )

    if write:
        rows = _write_row(
            engine,
            target_date=target_date,
            state=state,
            smallcap_rs_z=result.smallcap_rs_z,
            breadth=result.breadth_pct_above_200dma,
            vix_pct=result.vix_percentile,
            dispersion=result.cross_sectional_dispersion,
        )
        result.rows_written = rows

    result.runtime_seconds = round(time.time() - started, 3)
    log.info(
        "regime_cron_complete",
        target_date=str(target_date),
        state=state.value,
        rows_written=result.rows_written,
        runtime_seconds=result.runtime_seconds,
    )
    return result


__all__ = [
    "RegimeWriteResult",
    "compute_breadth_pct_above_200dma",
    "compute_cross_sectional_dispersion",
    "compute_daily_regime",
    "compute_smallcap_rs_z",
    "compute_vix_percentile",
]
