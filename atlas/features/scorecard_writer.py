"""Daily scorecard writer — v6 Phase 3 entrypoint (issue #43).

Reads OHLCV + indices, computes the 6 locked methodology features +
``cap_tier`` daily, derives 5-family R/A/G state, and writes one row per
``(instrument_id, date)`` into ``atlas.atlas_scorecard_daily``.

Design contracts
================

* **Vectorised.** No Python loops over instruments. Every per-instrument
  computation runs through pandas ``groupby + transform`` so the inner loop
  runs in C. Target: <5 min for 727+ instruments on EC2 t3.large
  (eng review §4).

* **Look-ahead audit baked in.** Per CONTEXT.md §"Look-ahead audit gate",
  every feature value at date T uses ONLY OHLCV ≤ T. Enforced two ways:
    1. Structural — the OHLCV query has ``WHERE date <= :target_date``.
    2. Runtime — ``assert (ohlcv["date"] <= target_date).all()`` after load.

* **cap_tier daily.** Per CONTEXT.md §"cap_tier (point-in-time semantics)":
  trailing-60d median traded value at date T, terciles (Small/Mid/Large).
  Computed fresh each day. Position binding to the trigger-time tier is
  enforced by ``atlas_signal_calls.cap_tier_at_trigger`` (out of scope here).

* **Family R/A/G — bootstrap rules.** The methodology lock (Phase 0.5g
  24-framework discovery, issue #25) has not yet produced the canonical
  cell-rule-driven family states. Until it does, this writer derives
  R/A/G from reasonable feature-threshold rules sourced from
  ``atlas_thresholds`` via :func:`atlas.db.load_thresholds`, falling back
  to hardcoded defaults when a threshold key is absent.

* **Decimal for money, float for ratios.** Per the global financial rules.
  ``log_med_tv_60d``, ``realized_vol_60d``, ``rs_residual_6m``,
  ``formation_max_dd``, ``log_price`` are dimensionless ratios — float OK.
  ``data_completeness`` is Decimal(4,3) at the schema boundary.
"""

# allow-large: single cohesive daily-writer pipeline — loaders, feature
# compute, family R/A/G derivation, DB write — forms one indivisible
# computation unit. Splitting would force shared mutable DataFrame plumbing
# across modules with no clean public seam.

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

import numpy as np
import pandas as pd
import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, open_compute_session
from atlas.db import get_engine, load_thresholds

# atlas.discovery.* is imported lazily inside the bridge function to
# avoid a circular import (atlas.discovery → atlas.decisions →
# atlas.features). The bridge needs the deep-search panel computer but
# it must not be hoisted to module scope.

log = structlog.get_logger()


# Features that ship as first-class columns on atlas_scorecard_daily
# (migration 080) — these MUST NOT be duplicated inside the features
# JSONB. The bridge writes every OTHER feature in the deep-search
# library to JSONB so cell-rule predicates can evaluate against them.
_FIRST_CLASS_FEATURE_NAMES: frozenset[str] = frozenset(
    {
        "rs_residual_6m",
        "log_med_tv_60d",
        "realized_vol_60d",
        "formation_max_dd",
        "listing_age_days",
        "log_price",
    }
)

# Names wired in panel_for_feature (deep_search_features.py). These are
# the features the cell rules reference at evaluation time. Anything in
# this list MINUS the first-class set is what we write to features JSONB.
# Kept as a module constant so changes here track the discovery library.
_DEEP_SEARCH_PANEL_FEATURES: tuple[str, ...] = (
    # v1
    "log_med_tv_60d",
    "realized_vol_60d",
    "realized_vol_252d",
    "rs_residual_3m",
    "rs_residual_6m",
    "rs_residual_12m",
    "rs_alignment_count",
    "rs_acceleration_63d",
    "formation_max_dd",
    "dd_from_52w_high",
    "dd_from_3y_high",
    "dd_from_5y_high",
    "dist_above_sma50",
    "dist_above_sma200",
    "sma50_gt_sma200",
    "listing_age_days",
    "close_over_60d_high",
    "close_over_30d_high",
    "volume_zscore_60d",
    "pos_months_12m",
    "log_price",
    "trend_slope_60d",
    # v2
    "rs_residual_1m",
    "realized_vol_20d",
    "vol_regime_60_252",
    "downside_vol_60d",
    "volume_zscore_252d",
    "tv_momentum_21_63",
    "roc_21d",
    "roc_63d",
    "roc_126d",
    "max_consec_pos_months_12m",
    "pos_weeks_12m",
    "dd_recovery_pct",
    "dist_from_52w_low",
    "close_at_52w_high",
    "consecutive_above_sma50",
    "consecutive_above_sma200",
    "rsi_14",
    "bb_pct_20d",
    "atr_pct_14",
    "corr_to_nifty_60d",
    "beta_60d",
    "excess_vol_60d",
    "rs_rank_6m_3m_diff",
    "rs_rank_12m_6m_diff",
    "range_compression_60_252",
    "ulcer_index_60d",
    "momentum_quality_6m",
    "trend_strength_60d",
    "new_high_streak_60d",
    "close_over_252d_high",
    # red-team quick wins
    "amihud_illiq_21d",
    "obv_slope_60d",
    "mfi_14",
    "bb_squeeze_20d",
    "rs_rank_within_tier_3m",
    "rs_rank_within_tier_6m",
    "rs_rank_within_tier_12m",
    # sector family
    "sector_rs_6m",
    "sector_rs_12m",
    "sector_rs_rank_6m",
    "sector_breadth_pos",
    "sector_strength_rank",
    "sector_vol_regime",
    "cross_sector_breadth",
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CapTier = Literal["Small", "Mid", "Large"]
FamilyState = Literal["R", "A", "G"]

# Lookback window for OHLCV history loaded per run. 365 calendar days ≈ 252
# trading days = ``ret_12m`` / ``formation_max_dd`` rolling window. The 6
# locked features all sit inside this window; sector RS computation pulls
# index prices over the same horizon.
DEFAULT_LOOKBACK_DAYS = 365

# Window sizes (trading days)
MED_TV_WINDOW = 60
VOL_WINDOW = 60
FORMATION_DD_WINDOW = 252
RS_WINDOW = 126  # 6 months — for rs_residual_6m
DD_FROM_52W_WINDOW = 252

# Family R/A/G default thresholds — bootstrap until Phase 0.5g 24-framework
# discovery (issue #25) produces the cell-rule-driven family states.
# Threshold keys looked up in atlas_thresholds via load_thresholds(); these
# are the fallback values used when the key is absent (most are absent at
# v6 launch per /grill Q11 D7).
_DEFAULT_THRESHOLDS: dict[str, Decimal] = {
    # Volatility — cross-sectional percentiles of realized_vol_60d
    "family_volatility_high_p": Decimal("0.90"),
    "family_volatility_low_p": Decimal("0.25"),
    # Path — formation_max_dd buckets
    "family_path_red_max_dd": Decimal("0.30"),
    "family_path_red_dd_from_52w": Decimal("0.25"),
    "family_path_green_max_dd": Decimal("0.10"),
    "family_path_green_dd_from_52w": Decimal("0.05"),
    # Trend — sector-relative RS deciles (rs_residual_6m percentile)
    "family_trend_red_p": Decimal("0.10"),
    "family_trend_green_p": Decimal("0.90"),
    # Sector RS deciles
    "family_sector_red_p": Decimal("0.10"),
    "family_sector_green_p": Decimal("0.90"),
}


# ---------------------------------------------------------------------------
# Schemas + return contracts
# ---------------------------------------------------------------------------


class ScorecardRow(BaseModel):
    """One scorecard row.

    Mirrors ``atlas.atlas_scorecard_daily`` schema (migration 080) — see
    that migration for the canonical column list. Defaults here match the
    DB ``server_default``s so a model instance with only the required
    fields filled in serialises to a row the DB will accept.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False)

    # Identity
    date: date
    instrument_id: str  # UUID as text; SQLAlchemy casts at the boundary.
    cap_tier: CapTier

    # Family R/A/G states
    family_trend: FamilyState
    family_volatility: FamilyState
    family_volume: FamilyState
    family_path: FamilyState
    family_sector: FamilyState

    # Locked methodology features (first-class columns)
    rs_residual_6m: float | None = None
    log_med_tv_60d: float | None = None
    realized_vol_60d: float | None = None
    formation_max_dd: float | None = None
    listing_age_days: int | None = None
    log_price: float | None = None

    # Extended feature library (JSONB)
    features: dict = Field(default_factory=dict)

    # Data quality
    data_completeness: Decimal = Decimal("1.000")


@dataclass
class ScorecardWriteResult:
    """Outcome of one ``compute_daily_scorecard`` invocation."""

    rows_written: int = 0
    partial_day_count: int = 0
    runtime_seconds: float = 0.0
    missing_instruments: list[str] = field(default_factory=list)
    target_date: date | None = None
    run_id: str | None = None


# Tuple of column names matching atlas_scorecard_daily for bulk insert.
SCORECARD_COLUMNS: tuple[str, ...] = (
    "date",
    "instrument_id",
    "cap_tier",
    "family_trend",
    "family_volatility",
    "family_volume",
    "family_path",
    "family_sector",
    "rs_residual_6m",
    "log_med_tv_60d",
    "realized_vol_60d",
    "formation_max_dd",
    "listing_age_days",
    "log_price",
    "features",
    "data_completeness",
)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_universe(engine: Engine) -> pd.DataFrame:
    """Active M1 universe.

    Reads ``atlas.atlas_universe_stocks`` (the current canonical universe
    table — 727 active instruments today). When ``atlas_universe_snapshot``
    ships in Phase 0.5a it will be a point-in-time variant; until then
    M1 universe at target_date == today's active universe.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                instrument_id::text AS instrument_id,
                symbol,
                tier,
                sector,
                listing_date
            FROM atlas.atlas_universe_stocks
            WHERE effective_to IS NULL
            """,
            conn,
        )
    log.info("scorecard_universe_loaded", count=len(df))
    return df


def _load_ohlcv(
    engine: Engine,
    *,
    instrument_ids: list[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    """Adjusted OHLCV for the universe across ``[start, end]``.

    Look-ahead audit point #1 — structural ``WHERE date <= :end`` clamps the
    server-side query to the audit window.
    """
    if not instrument_ids:
        cols: list[str] = ["instrument_id", "date", "open", "high", "low", "close", "volume"]
        return pd.DataFrame({c: [] for c in cols})

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                instrument_id::text AS instrument_id,
                date,
                open,
                high,
                low,
                COALESCE(close_adj, close) AS close,
                volume
            FROM public.de_equity_ohlcv
            WHERE instrument_id::text = ANY(%(ids)s)
              AND date BETWEEN %(start)s AND %(end)s
            ORDER BY instrument_id, date
            """,
            conn,
            params={"ids": instrument_ids, "start": start, "end": end},
        )
    if df.empty:
        log.warning("scorecard_ohlcv_empty", start=str(start), end=str(end))
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _load_nifty500_close(
    engine: Engine,
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    """NIFTY 500 close as the broad benchmark for ``rs_residual_6m``.

    Single-column wide frame keyed on ``date``. Empty frame returned when
    the index is missing — caller treats RS as NaN.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT date, close
            FROM public.de_index_prices
            WHERE index_code = 'NIFTY 500'
              AND date BETWEEN %(start)s AND %(end)s
              AND close IS NOT NULL
            ORDER BY date
            """,
            conn,
            params={"start": start, "end": end},
        )
    if df.empty:
        log.warning("scorecard_nifty500_empty", start=str(start), end=str(end))
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.rename(columns={"close": "bench_close"})
    return df


# ---------------------------------------------------------------------------
# cap_tier daily compute
# ---------------------------------------------------------------------------


def compute_cap_tiers(
    ohlcv_long: pd.DataFrame,
    target_date: date,
    *,
    window: int = MED_TV_WINDOW,
) -> pd.Series:
    """Compute cap tier per instrument from trailing-60d median traded value.

    Args:
        ohlcv_long: long-form OHLCV. Must contain at minimum
            ``instrument_id``, ``date``, ``close`` and ``volume`` columns.
            ``traded_value`` is derived as ``close * volume``.
        target_date: the audit horizon — only rows with ``date <= target_date``
            participate. (Structural look-ahead guard.)
        window: trailing window in trading days. Default 60 per methodology.

    Returns:
        ``pd.Series`` indexed by ``instrument_id`` with values in
        ``{"Small", "Mid", "Large"}``. Instruments with insufficient
        history get a ``NaN`` placeholder (caller decides default tier).

    Vectorised — no Python loop over instruments. The full universe is
    grouped, the trailing window is selected via ``groupby.tail``, the
    median is computed in C, and ``pd.qcut`` assigns terciles in one shot.
    """
    if ohlcv_long.empty:
        return pd.Series([], dtype=object, name="cap_tier")

    df = ohlcv_long.copy()
    # Compute traded_value if not present
    if "traded_value" not in df.columns:
        df["traded_value"] = df["close"].astype("float64") * df["volume"].astype("float64")

    # Structural look-ahead guard — drop any rows past the audit horizon.
    df = df.loc[df["date"] <= target_date]
    if df.empty:
        return pd.Series([], dtype=object, name="cap_tier")

    # Sort then groupby + tail to grab the trailing ``window`` rows per
    # instrument. ``observed=True`` avoids cartesian expansion on categoricals.
    df = df.sort_values(["instrument_id", "date"])
    tail = df.groupby("instrument_id", group_keys=False, observed=True).tail(window)

    med = tail.groupby("instrument_id", observed=True)["traded_value"].median()

    # If fewer than 3 instruments have valid medians, terciles collapse —
    # default everyone to Mid in that pathological case.
    valid = med.dropna()
    if len(valid) < 3:
        out = pd.Series("Mid", index=med.index, name="cap_tier", dtype=object)
        out[med.isna()] = pd.NA
        return out

    # ``qcut`` with explicit labels — Smallest tercile → "Small".
    # ``duplicates="drop"`` guards a degenerate distribution (all-same TV)
    # in which case qcut would otherwise raise. If that happens we fall
    # back to "Mid" for everyone (signal absent).
    tier_values: pd.Series
    try:
        qcut_result = pd.qcut(
            valid,
            q=3,
            labels=["Small", "Mid", "Large"],
            duplicates="drop",
        )
        qcut_series = pd.Series(qcut_result, index=valid.index)
        unique_labels = pd.unique(qcut_series.dropna().astype(str))
        if len(unique_labels) < 3:
            # qcut collapsed an edge — rank-fallback assigns Small/Mid/Large.
            ranks = valid.rank(method="first", pct=True)
            tier_values = pd.Series(
                np.where(
                    ranks <= 1 / 3,
                    "Small",
                    np.where(ranks <= 2 / 3, "Mid", "Large"),
                ),
                index=valid.index,
            )
        else:
            tier_values = qcut_series.astype(str)
    except ValueError:
        ranks = valid.rank(method="first", pct=True)
        tier_values = pd.Series(
            np.where(
                ranks <= 1 / 3,
                "Small",
                np.where(ranks <= 2 / 3, "Mid", "Large"),
            ),
            index=valid.index,
        )

    out = pd.Series(pd.NA, index=med.index, name="cap_tier", dtype=object)
    out.loc[valid.index] = tier_values.astype(object).to_numpy()
    return out


# ---------------------------------------------------------------------------
# Locked methodology features
# ---------------------------------------------------------------------------


def _compute_locked_features(
    ohlcv: pd.DataFrame,
    *,
    bench_close: pd.DataFrame,
    universe: pd.DataFrame,
    target_date: date,
) -> pd.DataFrame:
    """Compute the 6 locked methodology features at ``target_date``.

    Returns a per-instrument frame with columns:
        - rs_residual_6m
        - log_med_tv_60d
        - realized_vol_60d
        - formation_max_dd
        - listing_age_days
        - log_price
        - dd_from_52w (helper for family_path)
        - data_completeness

    Strictly vectorised; no per-instrument Python loop.
    """
    if ohlcv.empty:
        return pd.DataFrame()

    df = ohlcv.copy().sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # Look-ahead audit point #2 — runtime assertion that no future data leaked
    # through the query. Cheap to evaluate (single np.any).
    assert (
        df["date"] <= target_date
    ).all(), "scorecard_writer look-ahead audit violation: OHLCV contains rows after target_date"

    # --- ret_1d for rolling vol ---------------------------------------------
    grouped_close = df.groupby("instrument_id", group_keys=False, observed=True)["close"]
    df["ret_1d"] = grouped_close.pct_change(periods=1).astype("float64")

    # traded_value (used by log_med_tv_60d) -----------------------------------
    df["traded_value"] = df["close"].astype("float64") * df["volume"].astype("float64")

    # --- realized_vol_60d (annualised std of daily returns) ------------------
    df["realized_vol_60d"] = df.groupby("instrument_id", group_keys=False, observed=True)[
        "ret_1d"
    ].transform(lambda s: s.rolling(VOL_WINDOW, min_periods=VOL_WINDOW // 2).std()) * np.sqrt(252)

    # --- log_med_tv_60d ------------------------------------------------------
    df["med_tv_60d"] = df.groupby("instrument_id", group_keys=False, observed=True)[
        "traded_value"
    ].transform(lambda s: s.rolling(MED_TV_WINDOW, min_periods=MED_TV_WINDOW // 2).median())
    df["log_med_tv_60d"] = np.log1p(df["med_tv_60d"].clip(lower=0))

    # --- formation_max_dd (rolling 252-day) ---------------------------------
    def _max_dd(returns: pd.Series) -> pd.Series:
        cumulative = (1 + returns.fillna(0)).cumprod()
        rolling_peak = cumulative.rolling(
            FORMATION_DD_WINDOW, min_periods=FORMATION_DD_WINDOW // 2
        ).max()
        drawdown = cumulative.div(rolling_peak.replace(0, np.nan)).sub(1)
        return (
            drawdown.rolling(FORMATION_DD_WINDOW, min_periods=FORMATION_DD_WINDOW // 2).min().abs()
        )

    df["formation_max_dd"] = df.groupby("instrument_id", group_keys=False, observed=True)[
        "ret_1d"
    ].transform(_max_dd)

    # --- log_price -----------------------------------------------------------
    df["log_price"] = np.log(df["close"].clip(lower=1e-9))

    # --- rs_residual_6m ------------------------------------------------------
    # Definition for v6 launch: 6-month return of the stock minus 6-month
    # return of the broad benchmark (NIFTY 500). True "residual" form
    # (sector-beta-controlled) lands in Phase 0.5g; this is the M2-spec
    # excess-return proxy that the family thresholds already calibrate
    # against.
    df["close_6m_ago"] = df.groupby("instrument_id", group_keys=False, observed=True)[
        "close"
    ].shift(RS_WINDOW)
    df["ret_6m"] = df["close"].astype("float64") / df["close_6m_ago"].astype("float64") - 1.0

    if not bench_close.empty:
        bench = bench_close.copy().sort_values("date").reset_index(drop=True)
        bench["bench_close_6m_ago"] = bench["bench_close"].shift(RS_WINDOW)
        bench["bench_ret_6m"] = (
            bench["bench_close"].astype("float64") / bench["bench_close_6m_ago"].astype("float64")
            - 1.0
        )
        df = df.merge(bench[["date", "bench_ret_6m"]], on="date", how="left")
    else:
        df["bench_ret_6m"] = np.nan

    df["rs_residual_6m"] = df["ret_6m"] - df["bench_ret_6m"]

    # --- dd_from_52w (helper for family_path) -------------------------------
    df["high_52w"] = df.groupby("instrument_id", group_keys=False, observed=True)[
        "close"
    ].transform(lambda s: s.rolling(DD_FROM_52W_WINDOW, min_periods=DD_FROM_52W_WINDOW // 4).max())
    df["dd_from_52w"] = (df["high_52w"].astype("float64") - df["close"].astype("float64")) / df[
        "high_52w"
    ].replace(0, np.nan).astype("float64")
    df["dd_from_52w"] = df["dd_from_52w"].clip(lower=0)

    # --- Pick the target_date snapshot --------------------------------------
    snap = df.loc[df["date"] == target_date].copy()
    if snap.empty:
        log.warning("scorecard_no_rows_on_target_date", target_date=str(target_date))
        return snap

    # --- listing_age_days ----------------------------------------------------
    # Compute against universe.listing_date when known; else fall back to
    # min(date) per instrument in the loaded window.
    if "listing_date" in universe.columns:
        listing = universe[["instrument_id", "listing_date"]].copy()
        listing["instrument_id"] = listing["instrument_id"].astype(str)
        snap = snap.merge(listing, on="instrument_id", how="left")
    else:
        snap["listing_date"] = pd.NaT

    first_seen_series = df.groupby("instrument_id", observed=True)["date"].min()
    first_seen = first_seen_series.reset_index()
    first_seen.columns = ["instrument_id", "first_seen_date"]
    snap = snap.merge(first_seen, on="instrument_id", how="left")
    snap["listing_date"] = snap["listing_date"].fillna(snap["first_seen_date"])
    snap["listing_age_days"] = (
        pd.to_datetime(target_date) - pd.to_datetime(snap["listing_date"])
    ).dt.days

    # --- data_completeness ---------------------------------------------------
    # Fraction of expected bars present in the lookback window. "Expected"
    # is bench_close trading-day count when bench is available (most reliable
    # NSE-calendar proxy), otherwise the max bar-count across the universe.
    if not bench_close.empty:
        expected = bench_close.loc[bench_close["date"] <= target_date, "date"].nunique()
    else:
        expected = df.groupby("instrument_id", observed=True)["date"].nunique().max()
    expected = max(int(expected), 1)

    bar_counts = df.groupby("instrument_id", observed=True)["date"].nunique()
    completeness = (bar_counts / expected).clip(upper=1.0)
    snap = snap.merge(
        completeness.rename("data_completeness").reset_index(),
        on="instrument_id",
        how="left",
    )
    snap["data_completeness"] = snap["data_completeness"].fillna(0.0)

    return snap


# ---------------------------------------------------------------------------
# Family R/A/G derivation
# ---------------------------------------------------------------------------


def _t(thresholds: Mapping[str, Decimal], key: str) -> float:
    """Threshold accessor — atlas_thresholds → fallback default → float."""
    val = thresholds.get(key, _DEFAULT_THRESHOLDS[key])
    return float(val)


def derive_family_states(
    snap: pd.DataFrame,
    thresholds: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Compute the 5-family R/A/G state per row.

    Mutates a copy of ``snap`` to add ``family_trend, family_volatility,
    family_volume, family_path, family_sector``. Pure-pandas vectorised
    operations; no Python loop over instruments.

    Family R/A/G rules at v6 launch are **bootstrap defaults** — Phase 0.5g
    cell-rule discovery (issue #25) replaces these with the discovered
    cell rules. Until then the rules below provide a sensible default
    so the writer ships and the scorecard surface is populated.

    Rule summary:
        - family_trend:       sector-relative RS percentile in (red_p, green_p)
        - family_volatility:  cross-sectional realized_vol_60d percentile
        - family_volume:      90d trend of log_med_tv_60d (rising = G)
        - family_path:        formation_max_dd ∧ dd_from_52w composite
        - family_sector:      sector-aggregated RS percentile
    """
    out = snap.copy()

    # All rules need cross-sectional ranks computed at the target_date —
    # everything in ``snap`` is one date, so .rank(pct=True) is per-row.
    rs_pct = out["rs_residual_6m"].rank(pct=True, method="dense")
    vol_pct = out["realized_vol_60d"].rank(pct=True, method="dense")

    # --- family_trend (sector-neutralised RS) -------------------------------
    # ``<=`` for the red cutoff so the bottom decile is inclusive — matches
    # the standard "bottom 10%" quintile convention.
    red_p = _t(thresholds, "family_trend_red_p")
    green_p = _t(thresholds, "family_trend_green_p")
    out["family_trend"] = np.where(
        rs_pct.isna(),
        "A",
        np.where(rs_pct <= red_p, "R", np.where(rs_pct >= green_p, "G", "A")),
    )

    # --- family_volatility --------------------------------------------------
    hi_p = _t(thresholds, "family_volatility_high_p")
    lo_p = _t(thresholds, "family_volatility_low_p")
    out["family_volatility"] = np.where(
        vol_pct.isna(),
        "A",
        np.where(vol_pct >= hi_p, "R", np.where(vol_pct <= lo_p, "G", "A")),
    )

    # --- family_volume (trend of log_med_tv_60d) ----------------------------
    # snap is one date — we need the prior log_med_tv to assess trend. We
    # expose ``log_med_tv_60d_prev`` if computed upstream; otherwise default
    # to A. Trend is captured in derivative form by caller passing in the
    # ratio col when available.
    if "log_med_tv_60d_trend" in out.columns:
        trend = out["log_med_tv_60d_trend"]
        out["family_volume"] = np.where(
            trend.isna(), "A", np.where(trend > 0, "G", np.where(trend < 0, "R", "A"))
        )
    else:
        out["family_volume"] = "A"

    # --- family_path --------------------------------------------------------
    red_max_dd = _t(thresholds, "family_path_red_max_dd")
    red_dd52 = _t(thresholds, "family_path_red_dd_from_52w")
    green_max_dd = _t(thresholds, "family_path_green_max_dd")
    green_dd52 = _t(thresholds, "family_path_green_dd_from_52w")

    max_dd = out["formation_max_dd"].astype("float64")
    dd52 = (
        out["dd_from_52w"].astype("float64")
        if "dd_from_52w" in out.columns
        else pd.Series(np.nan, index=out.index)
    )

    is_red = (max_dd > red_max_dd) & (dd52 > red_dd52)
    is_green = (max_dd < green_max_dd) & (dd52 < green_dd52)
    # Conservative-first ordering — R wins over G at the boundary.
    out["family_path"] = np.where(
        max_dd.isna() | dd52.isna(),
        "A",
        np.where(is_red, "R", np.where(is_green, "G", "A")),
    )

    # --- family_sector ------------------------------------------------------
    # Aggregate rs_residual_6m to sector level (cross-sectional median),
    # then rank sectors and apply the deciles.
    sector_red_p = _t(thresholds, "family_sector_red_p")
    sector_green_p = _t(thresholds, "family_sector_green_p")
    if "sector" in out.columns:
        sector_rs = out.groupby("sector", observed=True)["rs_residual_6m"].transform("median")
        sector_rank = sector_rs.rank(pct=True, method="dense")
        out["family_sector"] = np.where(
            sector_rank.isna(),
            "A",
            np.where(
                sector_rank <= sector_red_p,
                "R",
                np.where(sector_rank >= sector_green_p, "G", "A"),
            ),
        )
    else:
        out["family_sector"] = "A"

    return out


# ---------------------------------------------------------------------------
# Helper: log_med_tv 90d trend (for family_volume) — vectorised
# ---------------------------------------------------------------------------


def _add_volume_trend(
    ohlcv_with_log_med_tv: pd.DataFrame,
    target_date: date,
) -> pd.DataFrame:
    """Add ``log_med_tv_60d_trend`` (90d slope sign) to the snap row.

    Computes ``log_med_tv_60d(T) - log_med_tv_60d(T-90)`` per instrument.
    Positive = G (volume rising), negative = R, ~0 = A.
    """
    if ohlcv_with_log_med_tv.empty:
        return ohlcv_with_log_med_tv

    df = ohlcv_with_log_med_tv.sort_values(["instrument_id", "date"])
    # 90-day lag of log_med_tv_60d, per instrument
    lag = df.groupby("instrument_id", group_keys=False, observed=True)["log_med_tv_60d"].shift(90)
    trend = df["log_med_tv_60d"].astype("float64") - lag.astype("float64")
    df = df.assign(log_med_tv_60d_trend=trend)
    return df


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _row_dicts(snap: pd.DataFrame, target_date: date) -> list[dict]:
    """Convert the snap frame to a list of dicts matching ``SCORECARD_COLUMNS``."""
    if snap.empty:
        return []

    out = snap.copy()
    # Cap_tier defaults — if cap_tier is NA (insufficient history), default
    # to "Mid" so the NOT NULL DB constraint is satisfied. data_completeness
    # captures that this instrument is partial.
    out["cap_tier"] = out["cap_tier"].fillna("Mid")

    # data_completeness → Decimal(4,3)
    def _to_dc(v: float | None) -> Decimal:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return Decimal("0.000")
        # Clip to [0,1] and round to 3 decimal places
        v_clamped = max(0.0, min(1.0, float(v)))
        return Decimal(str(round(v_clamped, 3)))

    out["data_completeness"] = out["data_completeness"].apply(_to_dc)

    # listing_age_days → int / None
    if "listing_age_days" in out.columns:

        def _to_int_or_none(v: object) -> int | None:
            if v is None:
                return None
            if isinstance(v, float):
                if np.isnan(v):
                    return None
                return int(v)
            if isinstance(v, int):
                return int(v)
            # Numpy scalar / Decimal / etc — fall back via str round-trip
            try:
                return int(float(str(v)))
            except (TypeError, ValueError):
                return None

        out["listing_age_days"] = (
            out["listing_age_days"]
            .where(out["listing_age_days"].notna(), other=None)
            .map(_to_int_or_none)
        )

    # features JSONB — use the precomputed deep-search bridge dict when
    # the caller populated the ``features_jsonb`` column; otherwise empty.
    if "features_jsonb" in out.columns:
        out["features"] = out["features_jsonb"].apply(lambda v: v if isinstance(v, dict) else {})
    else:
        out["features"] = [{} for _ in range(len(out))]
    # Make sure date is a python date object
    out["date"] = pd.to_datetime(out["date"]).dt.date
    # date is always target_date for this snap, but enforce it:
    out["date"] = target_date

    return out.reindex(columns=list(SCORECARD_COLUMNS)).to_dict(orient="records")


# ---------------------------------------------------------------------------
# Deep-search feature bridge
# ---------------------------------------------------------------------------


def _to_jsonb_safe(value: object) -> float | int | bool | None:
    """Coerce a single panel value to a JSON-safe scalar.

    Returns:
        * ``None`` when the value is NaN, ±inf, or otherwise unrepresentable.
        * ``int`` when the value is a whole number (preserves listing-age /
          streak semantics in the JSONB).
        * ``float`` for ordinary numeric values.

    The predicate evaluator treats absent keys as NULL, so omitting NaN
    instead of writing `null` saves bytes without changing semantics.
    """
    if value is None:
        return None
    # bool is a subclass of int — keep it explicit.
    if isinstance(value, bool):
        return value
    if isinstance(value, int | np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    # Fallback — coerce via float.
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return f


def _compute_deep_search_features_jsonb(
    ohlcv: pd.DataFrame,
    bench: pd.DataFrame,
    cap_tiers: pd.Series,
    target_date: date,
) -> dict[str, dict[str, float | int | bool | None]]:
    """Compute deep-search feature panels and extract per-iid values.

    Bridges :func:`compute_daily_scorecard` to the deep-search feature
    library that the cell-rule predicates evaluate against. The 6 locked
    methodology features stay as first-class columns and are NOT written
    to the JSONB; everything else in :data:`_DEEP_SEARCH_PANEL_FEATURES`
    that produces a non-NaN value at ``target_date`` lands in the dict.

    Args:
        ohlcv: long-form OHLCV loaded by :func:`_load_ohlcv` — columns
            ``instrument_id, date, open, high, low, close, volume``. The
            ``instrument_id`` column is renamed to ``iid`` inline for the
            deep-search API.
        bench: NIFTY 500 benchmark frame (``date, bench_close``). Empty
            frame is acceptable; sector + RS panels will produce NaN.
        cap_tiers: per-iid Series produced by :func:`compute_cap_tiers`.
            Broadcast to a full date-indexed panel so the deep-search
            sector + within-tier panels resolve.
        target_date: the snapshot date — the function returns one dict
            per instrument with values at this date.

    Returns:
        ``{instrument_id: {feature: value, ...}}``. Empty dict when the
        OHLCV slice is empty or no panels produce values.

    Performance: panels are vectorised; on a 365 × 750 panel this runs
    in well under the 5-minute backfill budget. Sector mapping is loaded
    once from the staged CSV (``/tmp/deep_search_v2/sector_mapping.csv``)
    and reused; absence is tolerated (sector panels fall back to NaN).
    """
    if ohlcv.empty:
        return {}

    # Lazy imports — atlas.discovery transitively depends on atlas.features
    # (for the FEATURES allowlist), so module-level imports would create a
    # cycle. The bridge is the only call site so deferring is cheap.
    from atlas.discovery._sector_panels import load_sector_mapping
    from atlas.discovery.deep_search_features import (
        compute_feature_panels,
        panel_for_feature,
    )

    # Deep-search API expects (date, iid, close, volume). Rename and
    # narrow. Build the frame directly to dodge pandas rename's
    # overload-resolution ambiguity (pyright cannot pick the right
    # overload from a single-arg call).
    ds_ohlcv = pd.DataFrame(
        {
            "iid": ohlcv["instrument_id"].astype(str).to_numpy(),
            "date": ohlcv["date"].to_numpy(),
            "close": ohlcv["close"].to_numpy(),
            "volume": ohlcv["volume"].to_numpy(),
        }
    )

    # compute_feature_panels uses .pivot, which is happy with python date
    # and the str-coerced iid built above.

    # Build a nifty Series indexed by date. compute_rs_residual reindexes
    # this to the close panel index and forward-fills, so a sparse bench
    # frame is acceptable.
    if not bench.empty:
        nifty_series = pd.Series(
            bench["bench_close"].astype("float64").to_numpy(),
            index=pd.Index(bench["date"], name="date"),
            name="nifty500",
        )
    else:
        # All-NaN series of the right length → RS panels produce NaN,
        # caller handles gracefully.
        nifty_series = pd.Series(
            [np.nan] * len(ds_ohlcv["date"].unique()),
            index=pd.Index(sorted(ds_ohlcv["date"].unique()), name="date"),
            name="nifty500",
        )

    # cap_tier panel — deep-search expects long-form (date, iid, cap_tier)
    # covering the full panel. Broadcast the per-iid target-date tier
    # across every date in ds_ohlcv (the within-tier rank panels read the
    # tier at each date; using today's tier is an acceptable approximation
    # at v6 launch — point-in-time cap_tier landing is queued for the
    # phase 0.5g refresh, and is orthogonal to closing the scorecard
    # JSONB gap).
    cap_long_rows: list[dict[str, object]] = []
    tier_lookup = cap_tiers.fillna("Mid").astype(str).to_dict()
    unique_dates = sorted(ds_ohlcv["date"].unique())
    for d in unique_dates:
        for iid, tier in tier_lookup.items():
            cap_long_rows.append({"date": d, "iid": str(iid), "cap_tier": tier})
    cap_long = pd.DataFrame(cap_long_rows)

    sector_of = load_sector_mapping()

    panels = compute_feature_panels(ds_ohlcv, nifty_series, cap_long, sector_of=sector_of)

    # Extract per-instrument values at target_date. The panels are wide
    # frames indexed by date with iid columns. compute_feature_panels
    # forces every iid in the OHLCV to appear as a column.
    if target_date not in panels.close.index:
        # Fall back to the most recent available date <= target_date —
        # the panels reindex on close.index which is the OHLCV dates.
        # Defensive guard: if the target_date never appears in OHLCV
        # (holiday on the exchange), the scorecard writer's caller has
        # already logged a warning; emit no JSONB here.
        log.warning(
            "scorecard_deep_search_target_date_missing",
            target_date=str(target_date),
        )
        return {}

    out: dict[str, dict[str, float | int | bool | None]] = {}
    iid_columns = list(panels.close.columns)

    # Pre-collect each panel's row at target_date.
    target_rows: dict[str, pd.Series] = {}
    for feature in _DEEP_SEARCH_PANEL_FEATURES:
        if feature in _FIRST_CLASS_FEATURE_NAMES:
            continue
        try:
            panel = panel_for_feature(panels, feature)
        except KeyError:
            # New feature added to the cell vocabulary without a panel —
            # log once and skip; conviction tape will fall back to NULL
            # for predicates referencing it (existing behaviour).
            log.warning("scorecard_deep_search_panel_missing", feature=feature)
            continue
        if target_date not in panel.index:
            continue
        target_rows[feature] = panel.loc[target_date]

    for iid in iid_columns:
        iid_str = str(iid)
        feature_dict: dict[str, float | int | bool | None] = {}
        for feature, row_series in target_rows.items():
            raw = row_series.get(iid)
            safe = _to_jsonb_safe(raw)
            if safe is None:
                continue
            feature_dict[feature] = safe
        if feature_dict:
            out[iid_str] = feature_dict

    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compute_daily_scorecard(
    target_date: date,
    db_engine: Engine | None = None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    write: bool = True,
) -> ScorecardWriteResult:
    """Compute and write the daily scorecard for ``target_date``.

    Args:
        target_date: the date to compute the scorecard for. All features
            use only OHLCV with ``date <= target_date``.
        db_engine: optional engine override; defaults to the process-wide
            engine via :func:`atlas.db.get_engine`.
        lookback_days: how far back to load OHLCV for rolling windows.
            Default 365 (≈252 trading days) covers ``ret_12m`` /
            ``formation_max_dd``.
        write: if False, compute everything but skip the DB bulk_upsert.
            Useful for backfill dry-runs.

    Returns:
        :class:`ScorecardWriteResult` with rows_written, partial_day_count,
        runtime, and any missing instruments.
    """
    engine = db_engine or get_engine()
    run_id = uuid.uuid4()
    started = time.time()
    result = ScorecardWriteResult(target_date=target_date, run_id=str(run_id))

    log.info(
        "scorecard_writer_start",
        run_id=str(run_id),
        target_date=str(target_date),
        lookback_days=lookback_days,
    )

    # Load universe + thresholds + OHLCV + benchmark
    universe = _load_universe(engine)
    if universe.empty:
        log.error("scorecard_universe_empty")
        result.runtime_seconds = time.time() - started
        return result

    thresholds = load_thresholds(engine=engine)
    log.info("scorecard_thresholds_loaded", count=len(thresholds))

    start_date = target_date - timedelta(days=lookback_days)
    instrument_ids = universe["instrument_id"].astype(str).tolist()

    ohlcv = _load_ohlcv(engine, instrument_ids=instrument_ids, start=start_date, end=target_date)
    if ohlcv.empty:
        log.error("scorecard_ohlcv_empty", target_date=str(target_date))
        result.runtime_seconds = time.time() - started
        return result

    bench = _load_nifty500_close(engine, start=start_date, end=target_date)

    # Compute cap_tier daily for the full universe
    cap_tiers = compute_cap_tiers(ohlcv, target_date)
    log.info("scorecard_cap_tiers_computed", count=int(cap_tiers.notna().sum()))

    # Compute the 6 locked features + helpers
    feature_snap = _compute_locked_features(
        ohlcv, bench_close=bench, universe=universe, target_date=target_date
    )

    if feature_snap.empty:
        log.warning("scorecard_no_target_date_rows", target_date=str(target_date))
        result.runtime_seconds = time.time() - started
        return result

    # Add volume trend on the long frame, then merge target_date row
    # (vectorised — _add_volume_trend runs on the long frame).
    long_with_features = ohlcv.copy()
    long_with_features = long_with_features.sort_values(["instrument_id", "date"]).reset_index(
        drop=True
    )
    long_with_features["traded_value"] = long_with_features["close"].astype("float64") * (
        long_with_features["volume"].astype("float64")
    )
    long_with_features["log_med_tv_60d"] = long_with_features.groupby(
        "instrument_id", group_keys=False, observed=True
    )["traded_value"].transform(
        lambda s: np.log1p(
            s.rolling(MED_TV_WINDOW, min_periods=MED_TV_WINDOW // 2).median().clip(lower=0)
        )
    )
    long_with_features = _add_volume_trend(long_with_features, target_date)
    trend_snap = long_with_features.loc[
        long_with_features["date"] == target_date,
        ["instrument_id", "log_med_tv_60d_trend"],
    ]
    feature_snap = feature_snap.merge(trend_snap, on="instrument_id", how="left")

    # Attach cap_tier + sector
    feature_snap = feature_snap.merge(
        cap_tiers.rename("cap_tier").reset_index(),
        on="instrument_id",
        how="left",
    )
    feature_snap = feature_snap.merge(
        universe[["instrument_id", "sector"]],
        on="instrument_id",
        how="left",
    )

    # Derive family R/A/G
    feature_snap = derive_family_states(feature_snap, thresholds)

    # Bridge: compute the deep-search feature library and attach a
    # ``features_jsonb`` column. Predicate evaluator merges this dict
    # into the scorecard row via dict.update(), so each non-NaN key
    # becomes addressable from cell-rule predicates. The 6 locked
    # methodology features remain first-class columns and are excluded
    # from the JSONB to avoid duplication.
    deep_search_jsonb = _compute_deep_search_features_jsonb(ohlcv, bench, cap_tiers, target_date)
    feature_snap["features_jsonb"] = (
        feature_snap["instrument_id"].astype(str).map(lambda iid: deep_search_jsonb.get(iid, {}))
    )
    # Defensive: ensure every cell is a dict before serialization. The
    # map above already returns {} for unknown iids, but a stray NaN
    # from a downstream merge would silently corrupt JSONB writes.
    feature_snap["features_jsonb"] = feature_snap["features_jsonb"].apply(
        lambda v: v if isinstance(v, dict) else {}
    )
    populated = int((feature_snap["features_jsonb"].apply(len) > 0).sum())
    log.info(
        "scorecard_deep_search_jsonb_attached",
        populated=populated,
        total=len(feature_snap),
    )

    # Missing instruments — universe IDs absent from the OHLCV snap
    snap_ids = set(feature_snap["instrument_id"].astype(str).tolist())
    universe_ids = set(universe["instrument_id"].astype(str).tolist())
    result.missing_instruments = sorted(universe_ids - snap_ids)
    if result.missing_instruments:
        log.warning(
            "scorecard_missing_instruments",
            count=len(result.missing_instruments),
            sample=result.missing_instruments[:5],
        )

    # Partial-day count (data_completeness < 1.0)
    result.partial_day_count = int((feature_snap["data_completeness"] < 1.0).sum())

    # Serialize → bulk_upsert
    rows = _row_dicts(feature_snap, target_date)
    if write and rows:
        tuples = [tuple(r[c] for c in SCORECARD_COLUMNS) for r in rows]
        # JSONB column needs psycopg2-friendly form
        from psycopg2.extras import Json

        # Re-pack with Json wrapper for the features column
        f_idx = SCORECARD_COLUMNS.index("features")
        tuples = [(*t[:f_idx], Json(t[f_idx]), *t[f_idx + 1 :]) for t in tuples]

        rows_written = bulk_upsert(
            engine,
            table="atlas.atlas_scorecard_daily",
            columns=list(SCORECARD_COLUMNS),
            rows=tuples,
            pk_columns=["date", "instrument_id"],
        )
        result.rows_written = rows_written
    elif rows:
        result.rows_written = len(rows)

    result.runtime_seconds = round(time.time() - started, 2)
    log.info(
        "scorecard_writer_complete",
        run_id=str(run_id),
        target_date=str(target_date),
        rows_written=result.rows_written,
        partial_day_count=result.partial_day_count,
        missing_instruments=len(result.missing_instruments),
        runtime_seconds=result.runtime_seconds,
    )
    return result


__all__ = [
    "SCORECARD_COLUMNS",
    "ScorecardRow",
    "ScorecardWriteResult",
    "compute_cap_tiers",
    "compute_daily_scorecard",
    "derive_family_states",
]
