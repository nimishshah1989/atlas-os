"""Per-cell exhaustive feature/threshold search — Large @ 12m POSITIVE.

Phase 0.5e callsite for the methodology lock §4 principle 7 ("pick features
by what separates TP from FP empirically — not from theory"). The 24-cell
broad sweep in :mod:`atlas.discovery.engine` confirms/denies a fixed
archetype mapping; it cannot DISCOVER new signals in cells where the broad
sweep produced ``no_conviction``.

This module fills that gap for ONE cell at a time. It generates ~60-80
candidate rules across 7 archetype families, walk-forward validates each
against the locked windows, and ranks by IC.

Initial deployment: Large-cap @ 12m POSITIVE — flagged borderline by the
broad sweep and by the Phase 3e changelog (Large pullback at 6m: TP=55.8%
borderline).

Data source: ``/tmp/sde_ohlcv_cache.pkl`` (cache mode only). Synthetic
mode is not supported — exhaustive search needs real cross-section to
distinguish from noise.

Vectorised — uses panel (wide) pivots, no per-instrument loops.
"""

# allow-large: single cohesive deep-search engine — candidate generation,
# feature panel computation, walk-forward evaluation, and persistence
# selection form one indivisible compute unit. HTML rendering lives in
# atlas.discovery.deep_search_report.

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import structlog

from atlas.decisions.rule_dsl import CellRule, FeaturePredicate
from atlas.discovery.engine import (
    DEFAULT_FRICTION_BY_TIER,
    DEFAULT_WINDOWS,
    PER_TENURE_IC_FLOOR,
    TENURE_TO_HORIZON_DAYS,
    WalkForwardWindow,
    _load_cache_files,
)

log = structlog.get_logger()

# Methodology lock identifier for INSERTed cells from this search.
DEEP_SEARCH_METHODOLOGY_REF = "DEEP_SEARCH_2026-05-24"

# Forward horizon for the 12m POSITIVE cell.
HORIZON_12M = TENURE_TO_HORIZON_DAYS["12m"]  # 252 trading days

# Per-tenure IC floor for 12m.
IC_FLOOR_12M = PER_TENURE_IC_FLOOR["12m"]  # Decimal("0.04")

# Friction for Large tier (one-way; round-trip = 2x).
FRICTION_LARGE = DEFAULT_FRICTION_BY_TIER["Large"]

# Minimum trigger observations per candidate (across all windows pooled).
# Below this we can't trust the percentiles. Same threshold as the broad
# sweep (engine.py:1016).
MIN_TRIGGERS = 30


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateRule:
    """One feature/threshold combination to try.

    Attributes:
        name: stable identifier used in the report and (if INSERTed) in the
            cell-definitions notes column.
        archetype: which of the 7 entry-pattern families this is from.
            One of: ``mean_reversion``, ``deep_value``, ``quality_momentum``,
            ``inflection``, ``consolidation_breakout``, ``liquidity_expansion``,
            ``structural``.
        features: flat-AND list of ``FeaturePredicate`` per CONTEXT.md.
            Each predicate names a feature in the FEATURES allowlist.
        rationale: one-line hypothesis describing why this combination
            might separate TP from FP at Large @ 12m POSITIVE.
    """

    name: str
    archetype: str
    features: tuple[FeaturePredicate, ...]
    rationale: str


@dataclass(frozen=True)
class CandidateResult:
    """The per-candidate evaluation outcome."""

    rule: CandidateRule
    ic: float
    tp_rate: float
    median_excess: float
    mean_excess: float
    friction_adjusted_excess: float
    percentile_10: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_90: float
    n_observations: int
    per_window_results: tuple[dict[str, Any], ...]
    validated: bool


@dataclass
class DeepSearchSummary:
    """Aggregate summary across all candidates evaluated."""

    cell_target: tuple[str, str, str]  # (cap_tier, tenure, action)
    results: tuple[CandidateResult, ...]
    run_started_at: datetime
    run_completed_at: datetime
    n_candidates: int
    n_validated: int
    best_ic: float | None
    best_rule_name: str | None
    inserted_cell_id: uuid.UUID | None = None
    inserted_rule_dsl: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Feature panel computation (vectorised, wide-form)
# ---------------------------------------------------------------------------


@dataclass
class FeaturePanels:
    """All feature panels needed by deep-search candidates.

    Each panel is a wide DataFrame (index=date, columns=iid). Cap_tier
    membership is a categorical panel too. Forward returns are precomputed
    once per horizon.
    """

    close: pd.DataFrame
    volume: pd.DataFrame
    cap_tier: pd.DataFrame  # categorical strings (Small/Mid/Large)
    nifty: pd.Series

    # Features.
    log_med_tv_60d: pd.DataFrame
    realized_vol_60d: pd.DataFrame
    realized_vol_252d: pd.DataFrame
    rs_residual_3m: pd.DataFrame
    rs_residual_6m: pd.DataFrame
    rs_residual_12m: pd.DataFrame
    rs_rank_6m: pd.DataFrame  # cross-sectional rank in [0,1]
    rs_rank_12m: pd.DataFrame
    rs_acceleration_63d: pd.DataFrame
    rs_alignment_count: pd.DataFrame
    dd_from_52w_high: pd.DataFrame
    dd_from_3y_high: pd.DataFrame
    dd_from_5y_high: pd.DataFrame
    formation_max_dd: pd.DataFrame
    dist_above_sma50: pd.DataFrame
    dist_above_sma200: pd.DataFrame
    sma50_gt_sma200: pd.DataFrame
    listing_age_days: pd.DataFrame
    close_over_60d_high: pd.DataFrame
    close_over_30d_high: pd.DataFrame
    volume_zscore_60d: pd.DataFrame
    pos_months_12m: pd.DataFrame
    log_price: pd.DataFrame
    trend_slope_60d: pd.DataFrame

    # Forward 252d excess return (vs nifty).
    fwd_excess_252d: pd.DataFrame


def _compute_rs_residual(
    close: pd.DataFrame, nifty: pd.Series, formation_days: int, skip_days: int = 21
) -> pd.DataFrame:
    """β-adjusted formation-window return vs Nifty 500.

    Returns a wide DataFrame indexed by date, columns iid. Vectorised
    end-to-end — no Python loop over instruments.
    """
    stock_daily = close.pct_change(fill_method=None)
    nifty_daily = nifty.pct_change(fill_method=None)
    cov = stock_daily.rolling(60, min_periods=40).cov(nifty_daily)
    var = cast(pd.Series, nifty_daily.rolling(60, min_periods=40).var())
    # Guard zero / nan var to avoid inf beta on holiday runs.
    var_safe = var.replace(0, np.nan)
    beta = cov.div(var_safe, axis=0).shift(skip_days)
    stock_ret = close.shift(skip_days) / close.shift(formation_days) - 1.0
    nifty_ret = nifty.shift(skip_days) / nifty.shift(formation_days) - 1.0
    expected = beta.mul(nifty_ret, axis=0)
    return cast(pd.DataFrame, stock_ret.sub(expected))


def _compute_feature_panels(
    ohlcv: pd.DataFrame,
    nifty500: pd.Series,
    cap_tier_long: pd.DataFrame,
) -> FeaturePanels:
    """Compute every feature panel needed by deep-search candidates.

    Args:
        ohlcv: long-form DataFrame (date, iid, close, volume).
        nifty500: benchmark series (date-indexed).
        cap_tier_long: long-form (date, iid, cap_tier) from the engine's
            _compute_cap_tier_panel.

    Returns:
        :class:`FeaturePanels` with everything wired.
    """
    # --- pivot to wide ----------------------------------------------------
    close = ohlcv.pivot(index="date", columns="iid", values="close").sort_index()
    volume = ohlcv.pivot(index="date", columns="iid", values="volume").sort_index()

    # Reindex nifty to close's index; forward-fill (benchmark covers a
    # superset most days).
    nifty = nifty500.reindex(close.index).ffill()

    # cap_tier wide panel for filtering. Use 'object' dtype so we can
    # compare to strings cleanly.
    cap_wide = cap_tier_long.pivot(index="date", columns="iid", values="cap_tier")
    cap_wide = cap_wide.reindex(index=close.index, columns=close.columns)

    daily = close.pct_change(fill_method=None)
    tv = close * volume

    log_med_tv_60d = cast(pd.DataFrame, np.log(tv.rolling(60, min_periods=30).median()))
    realized_vol_60d = cast(pd.DataFrame, daily.rolling(60, min_periods=40).std())
    realized_vol_252d = cast(pd.DataFrame, daily.rolling(252, min_periods=150).std())

    # 52-week / 3y / 5y drawdowns.
    high_252 = close.rolling(252, min_periods=120).max()
    high_756 = close.rolling(756, min_periods=300).max()  # 3y trading
    high_1260 = close.rolling(1260, min_periods=500).max()  # 5y trading
    dd_from_52w_high = close / high_252 - 1.0
    dd_from_3y_high = close / high_756 - 1.0
    dd_from_5y_high = close / high_1260 - 1.0

    # Formation max dd (105-day rolling drawdown, shifted 21d) — same as v5.
    rolling_max_105 = close.rolling(105, min_periods=60).max()
    rolling_dd_105 = close / rolling_max_105 - 1.0
    formation_max_dd = rolling_dd_105.rolling(105, min_periods=60).min().shift(21)

    # SMAs.
    sma50 = close.rolling(50, min_periods=30).mean()
    sma200 = close.rolling(200, min_periods=150).mean()
    dist_above_sma50 = close / sma50 - 1.0
    dist_above_sma200 = close / sma200 - 1.0
    sma50_gt_sma200 = cast(pd.DataFrame, (sma50 > sma200).astype(float))

    # Listing-age proxy: count of non-NaN closes per instrument up to date.
    listing_age_days = close.notna().cumsum()

    # Close > 30d / 60d high (breakout proxies).
    high_30 = close.rolling(30, min_periods=20).max()
    high_60 = close.rolling(60, min_periods=40).max()
    close_over_30d_high = cast(pd.DataFrame, (close >= high_30 * 0.99).astype(float))
    close_over_60d_high = cast(pd.DataFrame, (close >= high_60 * 0.99).astype(float))

    # Volume z-score 60d.
    tv_21 = tv.rolling(21, min_periods=15).mean()
    tv_252 = tv.rolling(252, min_periods=150).mean()
    tv_252_std = tv.rolling(252, min_periods=150).std().replace(0, np.nan)
    volume_zscore_60d = (tv_21 - tv_252) / tv_252_std

    # pos_months_12m: fraction of last 12 21d returns that were positive.
    monthly_rets = [(close.shift(k * 21) / close.shift((k + 1) * 21) - 1.0) for k in range(12)]
    arr = np.stack([r.values for r in monthly_rets])
    pos = (arr > 0).astype(float)
    valid = ~np.isnan(arr)
    cnt = valid.sum(axis=0)
    pos0 = np.where(valid, pos, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(cnt > 0, pos0.sum(axis=0) / cnt, np.nan)
    pos_months_12m = pd.DataFrame(frac, index=close.index, columns=close.columns)

    # RS residuals 3m / 6m / 12m.
    rs_residual_3m = _compute_rs_residual(close, nifty, 63)
    rs_residual_6m = _compute_rs_residual(close, nifty, 126)
    rs_residual_12m = _compute_rs_residual(close, nifty, 252)
    rs_rank_6m = rs_residual_6m.rank(axis=1, pct=True)
    rs_rank_12m = rs_residual_12m.rank(axis=1, pct=True)
    rs_rank_3m = rs_residual_3m.rank(axis=1, pct=True)

    # rs_alignment_count: how many of (3m,6m,12m) RS are top-quartile.
    rs_alignment_count = cast(
        pd.DataFrame,
        (rs_rank_3m >= 0.75).astype(float)
        + (rs_rank_6m >= 0.75).astype(float)
        + (rs_rank_12m >= 0.75).astype(float),
    )

    # rs_acceleration_63d: change in 6m RS rank over last quarter.
    rs_acceleration_63d = rs_rank_6m - rs_rank_6m.shift(63)

    log_price = cast(pd.DataFrame, np.log(close.clip(lower=1e-9)))

    # trend_slope_60d: simple linear regression slope of log-price on
    # last 60 days. Approximated via .rolling().apply on numpy — slow
    # per-instrument, so use a vectorised closed-form via shift differences.
    # slope ≈ (log_price - log_price.shift(60)) / 60.
    trend_slope_60d = (log_price - log_price.shift(60)) / 60.0

    # --- forward returns -----------------------------------------------
    fwd = close.shift(-HORIZON_12M) / close - 1.0
    nifty_fwd = (nifty.shift(-HORIZON_12M) / nifty) - 1.0
    fwd_excess_252d = fwd.sub(nifty_fwd, axis=0)

    return FeaturePanels(
        close=close,
        volume=volume,
        cap_tier=cap_wide,
        nifty=nifty,
        log_med_tv_60d=log_med_tv_60d,
        realized_vol_60d=realized_vol_60d,
        realized_vol_252d=realized_vol_252d,
        rs_residual_3m=rs_residual_3m,
        rs_residual_6m=rs_residual_6m,
        rs_residual_12m=rs_residual_12m,
        rs_rank_6m=rs_rank_6m,
        rs_rank_12m=rs_rank_12m,
        rs_acceleration_63d=rs_acceleration_63d,
        rs_alignment_count=rs_alignment_count,
        dd_from_52w_high=dd_from_52w_high,
        dd_from_3y_high=dd_from_3y_high,
        dd_from_5y_high=dd_from_5y_high,
        formation_max_dd=formation_max_dd,
        dist_above_sma50=dist_above_sma50,
        dist_above_sma200=dist_above_sma200,
        sma50_gt_sma200=sma50_gt_sma200,
        listing_age_days=listing_age_days,
        close_over_60d_high=close_over_60d_high,
        close_over_30d_high=close_over_30d_high,
        volume_zscore_60d=volume_zscore_60d,
        pos_months_12m=pos_months_12m,
        log_price=log_price,
        trend_slope_60d=trend_slope_60d,
        fwd_excess_252d=fwd_excess_252d,
    )


def _panel_for_feature(panels: FeaturePanels, feature_name: str) -> pd.DataFrame:
    """Map a FEATURES-allowlist name to its computed panel."""
    mapping: dict[str, pd.DataFrame] = {
        "log_med_tv_60d": panels.log_med_tv_60d,
        "realized_vol_60d": panels.realized_vol_60d,
        "realized_vol_252d": panels.realized_vol_252d,
        "rs_residual_3m": panels.rs_residual_3m,
        "rs_residual_6m": panels.rs_residual_6m,
        "rs_residual_12m": panels.rs_residual_12m,
        "rs_alignment_count": panels.rs_alignment_count,
        "rs_acceleration_63d": panels.rs_acceleration_63d,
        "formation_max_dd": panels.formation_max_dd,
        "dd_from_52w_high": panels.dd_from_52w_high,
        "dd_from_3y_high": panels.dd_from_3y_high,
        "dd_from_5y_high": panels.dd_from_5y_high,
        "dist_above_sma50": panels.dist_above_sma50,
        "dist_above_sma200": panels.dist_above_sma200,
        "sma50_gt_sma200": panels.sma50_gt_sma200,
        "listing_age_days": panels.listing_age_days,
        "close_over_60d_high": panels.close_over_60d_high,
        "close_over_30d_high": panels.close_over_30d_high,
        "volume_zscore_60d": panels.volume_zscore_60d,
        "pos_months_12m": panels.pos_months_12m,
        "log_price": panels.log_price,
        "trend_slope_60d": panels.trend_slope_60d,
    }
    if feature_name not in mapping:
        raise KeyError(f"feature {feature_name!r} not wired in deep-search panel map")
    return mapping[feature_name]


# ---------------------------------------------------------------------------
# Candidate generator — ~60-80 rules across 7 archetype families.
# ---------------------------------------------------------------------------


def _pred(feature: str, cmp: str, value: Decimal | tuple[Decimal, Decimal]) -> FeaturePredicate:
    """Concise FeaturePredicate factory."""
    if cmp == "in_range" and isinstance(value, tuple):
        return FeaturePredicate(feature=feature, cmp="in_range", value=value)
    if isinstance(value, tuple):
        raise ValueError(f"tuple value only valid for in_range, got cmp={cmp!r}")
    return FeaturePredicate(feature=feature, cmp=cmp, value=value)  # type: ignore[arg-type]


def _liquidity_floor_large() -> FeaturePredicate:
    """Standard Large-tier liquidity gate — matches engine._build_rule_dsl."""
    return _pred("log_med_tv_60d", ">=", Decimal("16.5"))


def generate_candidates_large_12m_positive() -> list[CandidateRule]:
    """Generate ~60-80 candidate rules for Large @ 12m POSITIVE.

    Seven archetype families, varied threshold ranges within each. Each
    rule has the standard Large liquidity floor plus 1-3 entry predicates.

    The result is order-stable so the same search re-runs deterministically.
    """
    candidates: list[CandidateRule] = []

    # ============ 1. MEAN-REVERSION (pullback-flavored) ===================
    # Hypothesis: top-RS Large-caps that pulled back from peak get
    # institutional rebalance buys → tend to recover over 12m.
    mr_dd_bands: list[tuple[Decimal, Decimal]] = [
        (Decimal("-0.20"), Decimal("-0.05")),
        (Decimal("-0.15"), Decimal("-0.03")),
        (Decimal("-0.12"), Decimal("-0.05")),
        (Decimal("-0.25"), Decimal("-0.05")),
        (Decimal("-0.30"), Decimal("-0.10")),
        (Decimal("-0.10"), Decimal("-0.02")),
    ]
    for low, high in mr_dd_bands:
        candidates.append(
            CandidateRule(
                name=f"MR_rs6m_topdec_dd52w_{int(float(low)*100)}_{int(float(high)*100)}",
                archetype="mean_reversion",
                features=(
                    _liquidity_floor_large(),
                    FeaturePredicate(
                        feature="rs_residual_6m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=10,  # top decile
                    ),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=(
                    f"Large + top-decile 6m RS + dd_from_52w in [{low},{high}] — "
                    "buy-the-dip in leaders"
                ),
            )
        )
    for low, high in mr_dd_bands[:4]:
        candidates.append(
            CandidateRule(
                name=f"MR_rs12m_topdec_dd52w_{int(float(low)*100)}_{int(float(high)*100)}",
                archetype="mean_reversion",
                features=(
                    _liquidity_floor_large(),
                    FeaturePredicate(
                        feature="rs_residual_12m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=10,
                    ),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=(
                    f"Large + top-decile 12m RS + dd_from_52w in [{low},{high}] — "
                    "long-term leader pullback"
                ),
            )
        )
    # Top-quartile RS (broader population) variants
    for low, high in [
        (Decimal("-0.20"), Decimal("-0.05")),
        (Decimal("-0.15"), Decimal("-0.05")),
    ]:
        candidates.append(
            CandidateRule(
                name=f"MR_rs6m_topq_dd52w_{int(float(low)*100)}_{int(float(high)*100)}",
                archetype="mean_reversion",
                features=(
                    _liquidity_floor_large(),
                    FeaturePredicate(
                        feature="rs_residual_6m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=4,  # top quartile
                    ),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=(
                    f"Large + top-quartile 6m RS + dd_from_52w in [{low},{high}] — "
                    "broader leader pullback population"
                ),
            )
        )
    # 3y-high pullback variants (longer drawdown context)
    for low, high in [
        (Decimal("-0.40"), Decimal("-0.15")),
        (Decimal("-0.30"), Decimal("-0.10")),
        (Decimal("-0.50"), Decimal("-0.20")),
    ]:
        candidates.append(
            CandidateRule(
                name=f"MR_rs6m_topdec_dd3y_{int(float(low)*100)}_{int(float(high)*100)}",
                archetype="mean_reversion",
                features=(
                    _liquidity_floor_large(),
                    FeaturePredicate(
                        feature="rs_residual_6m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=10,
                    ),
                    _pred("dd_from_3y_high", "in_range", (low, high)),
                ),
                rationale=(
                    f"Large + top-decile 6m RS + dd_from_3y_high in [{low},{high}] — "
                    "deep pullback in multi-year leader"
                ),
            )
        )

    # ============ 2. DEEP-VALUE (severely-broken-as-reversal-fuel) =========
    # Hypothesis: very-deep drawdowns in still-listed Large-caps tend to
    # mean-revert over 12m as overreaction fades.
    for low, high in [
        (Decimal("-0.60"), Decimal("-0.40")),
        (Decimal("-0.50"), Decimal("-0.30")),
        (Decimal("-0.70"), Decimal("-0.40")),
    ]:
        candidates.append(
            CandidateRule(
                name=f"DV_rs6m_bot_dd52w_{int(float(low)*100)}_{int(float(high)*100)}",
                archetype="deep_value",
                features=(
                    _liquidity_floor_large(),
                    _pred("rs_residual_6m", "<", Decimal("0")),
                    _pred("dd_from_52w_high", "in_range", (low, high)),
                ),
                rationale=(
                    f"Large + negative 6m RS + dd_from_52w in [{low},{high}] — "
                    "deep-value bounce candidate"
                ),
            )
        )
    for low, high in [
        (Decimal("-0.70"), Decimal("-0.40")),
        (Decimal("-0.80"), Decimal("-0.50")),
        (Decimal("-0.60"), Decimal("-0.30")),
    ]:
        candidates.append(
            CandidateRule(
                name=f"DV_rs12m_bot_dd5y_{int(float(low)*100)}_{int(float(high)*100)}",
                archetype="deep_value",
                features=(
                    _liquidity_floor_large(),
                    _pred("rs_residual_12m", "<", Decimal("0")),
                    _pred("dd_from_5y_high", "in_range", (low, high)),
                ),
                rationale=(
                    f"Large + negative 12m RS + dd_from_5y in [{low},{high}] — "
                    "multi-year deep value"
                ),
            )
        )

    # ============ 3. QUALITY-MOMENTUM (sustained leaders) =================
    # Hypothesis: top-RS + low-vol + liquid Large-caps compound institutional
    # demand sustainably over 12m.
    vol_bands: list[Decimal] = [Decimal("0.020"), Decimal("0.025"), Decimal("0.030")]
    for vol_cap in vol_bands:
        candidates.append(
            CandidateRule(
                name=f"QM_rs6m_topdec_lowvol_{int(float(vol_cap)*1000)}",
                archetype="quality_momentum",
                features=(
                    _liquidity_floor_large(),
                    FeaturePredicate(
                        feature="rs_residual_6m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=10,
                    ),
                    _pred("realized_vol_60d", "<=", vol_cap),
                ),
                rationale=(
                    f"Large + top-decile 6m RS + realized_vol_60d <= {vol_cap} — " "low-vol leader"
                ),
            )
        )
    for tv_floor in [Decimal("17.0"), Decimal("17.5"), Decimal("18.0")]:
        candidates.append(
            CandidateRule(
                name=f"QM_rs12m_topdec_megaliq_{int(float(tv_floor)*10)}",
                archetype="quality_momentum",
                features=(
                    _pred("log_med_tv_60d", ">=", tv_floor),
                    FeaturePredicate(
                        feature="rs_residual_12m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=10,
                    ),
                ),
                rationale=f"Mega-liquid Large + top-decile 12m RS (liquidity floor {tv_floor})",
            )
        )
    for age_min in [Decimal("1825"), Decimal("2520"), Decimal("3650")]:  # 5y, 7y, 10y
        candidates.append(
            CandidateRule(
                name=f"QM_rs6m_topdec_mature_{int(age_min)}d",
                archetype="quality_momentum",
                features=(
                    _liquidity_floor_large(),
                    FeaturePredicate(
                        feature="rs_residual_6m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=10,
                    ),
                    _pred("listing_age_days", ">=", age_min),
                ),
                rationale=f"Mature (≥{age_min}d listing) Large + top-decile 6m RS",
            )
        )
    # rs_alignment_count: 3m+6m+12m all top-quartile
    for align_min in [Decimal("2"), Decimal("3")]:
        candidates.append(
            CandidateRule(
                name=f"QM_align{int(align_min)}_lowvol",
                archetype="quality_momentum",
                features=(
                    _liquidity_floor_large(),
                    _pred("rs_alignment_count", ">=", align_min),
                    _pred("realized_vol_60d", "<=", Decimal("0.025")),
                ),
                rationale=(
                    f"Large + rs_alignment_count>={align_min} (3m∧6m∧12m all top-Q) " "+ low vol"
                ),
            )
        )
    # pos_months_12m high (consistent monthly winners)
    for pos_min in [Decimal("0.58"), Decimal("0.67"), Decimal("0.75")]:
        candidates.append(
            CandidateRule(
                name=f"QM_pos12m_{int(float(pos_min)*100)}",
                archetype="quality_momentum",
                features=(
                    _liquidity_floor_large(),
                    _pred("pos_months_12m", ">=", pos_min),
                    FeaturePredicate(
                        feature="rs_residual_6m",
                        cmp="in_top_quantile",
                        value=Decimal("1"),
                        value_quantile_n=4,
                    ),
                ),
                rationale=f"Large + pos_months_12m>={pos_min} + top-quartile 6m RS",
            )
        )

    # ============ 4. INFLECTION (trend-change) ===========================
    # Hypothesis: stocks that just crossed back above SMA200 (or
    # SMA50>SMA200) often start multi-year uptrends.
    for dist_min, dist_max in [
        (Decimal("0.00"), Decimal("0.05")),
        (Decimal("-0.02"), Decimal("0.03")),
        (Decimal("0.00"), Decimal("0.10")),
    ]:
        candidates.append(
            CandidateRule(
                name=f"INF_sma200_cross_{int(float(dist_min)*100)}_{int(float(dist_max)*100)}",
                archetype="inflection",
                features=(
                    _liquidity_floor_large(),
                    _pred("dist_above_sma200", "in_range", (dist_min, dist_max)),
                    _pred("rs_acceleration_63d", ">=", Decimal("0.10")),
                ),
                rationale=(
                    f"Large + recently-crossed-above-sma200 (dist in [{dist_min},{dist_max}]) "
                    "+ accelerating RS"
                ),
            )
        )
    # Golden cross — SMA50 above SMA200 + price above both
    candidates.append(
        CandidateRule(
            name="INF_golden_cross_recent",
            archetype="inflection",
            features=(
                _liquidity_floor_large(),
                _pred("sma50_gt_sma200", ">=", Decimal("1")),
                _pred("dist_above_sma50", ">=", Decimal("0.00")),
                _pred("dist_above_sma200", "in_range", (Decimal("0.00"), Decimal("0.15"))),
            ),
            rationale="Large + SMA50>SMA200 + price above both, modestly above SMA200",
        )
    )
    # RS rank rising — crossed from bottom to top half within 63d
    for accel_min in [Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]:
        candidates.append(
            CandidateRule(
                name=f"INF_rs_accel_{int(float(accel_min)*100)}",
                archetype="inflection",
                features=(
                    _liquidity_floor_large(),
                    _pred("rs_acceleration_63d", ">=", accel_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=(
                    f"Large + rs_acceleration_63d>={accel_min} (rapid rank improvement) "
                    "+ positive RS"
                ),
            )
        )

    # ============ 5. CONSOLIDATION-BREAKOUT ==============================
    # Hypothesis: low-vol consolidation + breakout to new highs = sustained
    # uptrend ahead.
    for vol_cap in [Decimal("0.015"), Decimal("0.018"), Decimal("0.022")]:
        candidates.append(
            CandidateRule(
                name=f"CB_lowvol_60dhigh_{int(float(vol_cap)*1000)}",
                archetype="consolidation_breakout",
                features=(
                    _liquidity_floor_large(),
                    _pred("realized_vol_60d", "<=", vol_cap),
                    _pred("close_over_60d_high", ">=", Decimal("1")),
                ),
                rationale=f"Large + low vol (<={vol_cap}) + near 60d high breakout",
            )
        )
    # Tight base — formation_max_dd very small (shallow base) + close at 30d high
    for dd_min in [Decimal("-0.08"), Decimal("-0.05"), Decimal("-0.10"), Decimal("-0.12")]:
        candidates.append(
            CandidateRule(
                name=f"CB_shallowbase_30dhigh_{int(float(dd_min)*100)}",
                archetype="consolidation_breakout",
                features=(
                    _liquidity_floor_large(),
                    _pred("formation_max_dd", ">=", dd_min),
                    _pred("close_over_30d_high", ">=", Decimal("1")),
                ),
                rationale=(f"Large + shallow formation drawdown (>= {dd_min}) + near 30d high"),
            )
        )
    # Pos-months high + breakout
    candidates.append(
        CandidateRule(
            name="CB_pos12m_60dhigh",
            archetype="consolidation_breakout",
            features=(
                _liquidity_floor_large(),
                _pred("pos_months_12m", ">=", Decimal("0.58")),
                _pred("close_over_60d_high", ">=", Decimal("1")),
            ),
            rationale="Large + ≥7/12 positive months + at 60d high — momentum continuation",
        )
    )

    # ============ 6. LIQUIDITY-EXPANSION ==================================
    # Hypothesis: rising liquidity (volume z-score > 1) on top-RS stocks
    # signals institutional accumulation.
    for vz_min in [Decimal("0.5"), Decimal("1.0"), Decimal("1.5"), Decimal("2.0")]:
        candidates.append(
            CandidateRule(
                name=f"LE_volz_{int(float(vz_min)*10)}_rs6m_pos",
                archetype="liquidity_expansion",
                features=(
                    _liquidity_floor_large(),
                    _pred("volume_zscore_60d", ">=", vz_min),
                    _pred("rs_residual_6m", ">", Decimal("0")),
                ),
                rationale=f"Large + volume z>={vz_min} (accumulation) + positive 6m RS",
            )
        )
    candidates.append(
        CandidateRule(
            name="LE_volz_2_topq_rs6m",
            archetype="liquidity_expansion",
            features=(
                _liquidity_floor_large(),
                _pred("volume_zscore_60d", ">=", Decimal("2.0")),
                FeaturePredicate(
                    feature="rs_residual_6m",
                    cmp="in_top_quantile",
                    value=Decimal("1"),
                    value_quantile_n=4,
                ),
            ),
            rationale="Large + volume z>=2 + top-quartile 6m RS",
        )
    )
    candidates.append(
        CandidateRule(
            name="LE_volz_15_topdec_rs12m",
            archetype="liquidity_expansion",
            features=(
                _liquidity_floor_large(),
                _pred("volume_zscore_60d", ">=", Decimal("1.5")),
                FeaturePredicate(
                    feature="rs_residual_12m",
                    cmp="in_top_quantile",
                    value=Decimal("1"),
                    value_quantile_n=10,
                ),
            ),
            rationale="Large + volume z>=1.5 + top-decile 12m RS",
        )
    )

    # ============ 7. STRUCTURAL (multi-year setups) ======================
    # Hypothesis: mature stocks near multi-year lows with recent reversal
    # signal capitulation-end and multi-year upside.
    for dd_min, dd_max in [
        (Decimal("-0.40"), Decimal("-0.15")),
        (Decimal("-0.50"), Decimal("-0.20")),
    ]:
        candidates.append(
            CandidateRule(
                name=f"STR_mature_dd5y_{int(float(dd_min)*100)}_{int(float(dd_max)*100)}",
                archetype="structural",
                features=(
                    _liquidity_floor_large(),
                    _pred("listing_age_days", ">=", Decimal("3650")),
                    _pred("dd_from_5y_high", "in_range", (dd_min, dd_max)),
                    _pred("rs_residual_12m", ">", Decimal("0")),
                ),
                rationale=(
                    f"Mature (10y+) Large + dd_from_5y in [{dd_min},{dd_max}] "
                    "+ positive 12m RS (turnaround)"
                ),
            )
        )
    # Trend-slope positive + above-SMA200 (structural uptrend)
    for slope_min in [Decimal("0.0005"), Decimal("0.001"), Decimal("0.0015")]:
        candidates.append(
            CandidateRule(
                name=f"STR_slope_{int(float(slope_min)*10000)}_abovesma200",
                archetype="structural",
                features=(
                    _liquidity_floor_large(),
                    _pred("trend_slope_60d", ">=", slope_min),
                    _pred("dist_above_sma200", ">=", Decimal("0.05")),
                ),
                rationale=(
                    f"Large + trend_slope_60d>={slope_min} (steady uptrend) "
                    "+ comfortably above SMA200"
                ),
            )
        )
    # 5y leader still ascending (rs_12m top-decile + age + slope)
    candidates.append(
        CandidateRule(
            name="STR_age10y_rs12m_topdec_slope_pos",
            archetype="structural",
            features=(
                _liquidity_floor_large(),
                _pred("listing_age_days", ">=", Decimal("3650")),
                FeaturePredicate(
                    feature="rs_residual_12m",
                    cmp="in_top_quantile",
                    value=Decimal("1"),
                    value_quantile_n=10,
                ),
                _pred("trend_slope_60d", ">=", Decimal("0.0005")),
            ),
            rationale="10y+ Large + top-decile 12m RS + positive slope — compounders",
        )
    )

    return candidates


# ---------------------------------------------------------------------------
# Candidate evaluation — vectorised mask + windowed metrics
# ---------------------------------------------------------------------------


def _build_test_window_mask_2d(
    reference: pd.DataFrame,
    windows: tuple[WalkForwardWindow, ...],
) -> pd.DataFrame:
    """Build a 2-D (date × instrument) boolean mask marking test-window dates.

    Vectorised — converts the datetime index to numpy ``datetime64[D]``
    so comparisons against the windows' ``date`` objects are unambiguous
    to pyright and identical at runtime.
    """
    idx = reference.index
    # Convert pandas DatetimeIndex to numpy datetime64[D] for comparison.
    if isinstance(idx, pd.DatetimeIndex):
        dates64 = idx.values.astype("datetime64[D]")
    else:
        dates64 = pd.to_datetime(idx).values.astype("datetime64[D]")
    mask_1d = np.zeros(len(idx), dtype=bool)
    for win in windows:
        win_lo = np.datetime64(win.test_start)
        win_hi = np.datetime64(win.test_end)
        mask_1d |= (dates64 >= win_lo) & (dates64 <= win_hi)
    return pd.DataFrame(
        np.broadcast_to(mask_1d[:, None], (len(idx), reference.shape[1])).copy(),
        index=idx,
        columns=reference.columns,
    )


def _apply_predicate(panel: pd.DataFrame, pred: FeaturePredicate) -> pd.DataFrame:
    """Apply one predicate against its feature panel, returning a boolean panel."""
    cmp = pred.cmp
    if cmp == "in_range":
        low, high = cast(tuple[Decimal, Decimal], pred.value)
        return (panel >= float(low)) & (panel <= float(high))
    if cmp == "in_top_quantile":
        # value_quantile_n=10 → top decile (rank pct >= 0.9).
        if pred.value_quantile_n is None:
            raise ValueError("in_top_quantile requires value_quantile_n")
        ranks = panel.rank(axis=1, pct=True)
        threshold = 1.0 - (1.0 / float(pred.value_quantile_n))
        return ranks >= threshold
    scalar = float(cast(Decimal, pred.value))
    if cmp == ">":
        return panel > scalar
    if cmp == ">=":
        return panel >= scalar
    if cmp == "<":
        return panel < scalar
    if cmp == "<=":
        return panel <= scalar
    if cmp == "==":
        return panel == scalar
    raise ValueError(f"unsupported cmp={cmp!r}")


def _evaluate_candidate(
    candidate: CandidateRule,
    panels: FeaturePanels,
    windows: tuple[WalkForwardWindow, ...],
    cap_tier: str = "Large",
) -> CandidateResult:
    """Walk-forward evaluate one candidate.

    Pipeline:
      1. Build a wide boolean entry mask = AND of all predicate panels.
      2. Filter to (a) cap_tier == 'Large', (b) trigger-date in any test window.
      3. Extract trigger forward excess; compute median, percentiles, TP rate.
      4. Compute pooled Spearman IC between rank-strength (RS 6m rank) and
         forward excess across all Large-cap obs in test windows.
      5. Per-window stats for stability.

    Returns CandidateResult.
    """
    # --- Build entry mask -------------------------------------------------
    masks: list[pd.DataFrame] = []
    for pred in candidate.features:
        panel = _panel_for_feature(panels, pred.feature)
        masks.append(_apply_predicate(panel, pred))

    # AND-combine, treating NaN/missing feature values as False.
    entry_mask = masks[0].fillna(False).astype(bool)
    for m in masks[1:]:
        entry_mask = entry_mask & m.fillna(False).astype(bool)

    # Restrict to cap_tier=Large.
    cap_mask = (panels.cap_tier == cap_tier).fillna(False)
    entry_mask = entry_mask & cap_mask

    # --- Pooled IC over TRIGGER set --------------------------------------
    # Per methodology lock §4 principle 7, IC should reflect the score
    # the candidate's archetype encodes — not a universe-wide RS IC. We
    # compute conditional IC: among triggers, how does the most-relevant
    # feature score the forward excess?
    #
    # We use the LAST entry predicate's feature panel as the score panel.
    # This is intentional: each candidate's last predicate is its most-
    # specific filter, and ranking *within* the trigger set on that score
    # is the conditional IC we care about.
    test_mask_2d = _build_test_window_mask_2d(panels.close, windows)

    fwd_panel = panels.fwd_excess_252d
    # Conditional IC: among trigger observations, rank-correlate the
    # last predicate's feature value with forward excess. If the feature
    # encodes a meaningful gradient, IC will be > 0; if the trigger is
    # already at the threshold edge, IC may be flat.
    last_pred = candidate.features[-1]
    score_panel = _panel_for_feature(panels, last_pred.feature)
    conditional_universe_mask = entry_mask & test_mask_2d
    ic = _pooled_spearman_ic(score_panel, fwd_panel, conditional_universe_mask)

    # --- Trigger metrics --------------------------------------------------
    # Triggers in test windows only.
    trigger_mask = entry_mask & test_mask_2d

    # Pull forward excess at trigger points.
    fwd_arr = np.asarray(fwd_panel.values, dtype=float)
    trigger_arr = np.asarray(trigger_mask.values, dtype=bool)
    trigger_excess_values = fwd_arr[trigger_arr]
    trigger_excess_values = trigger_excess_values[~np.isnan(trigger_excess_values)]
    n_obs = len(trigger_excess_values)

    per_window: list[dict[str, Any]] = []
    for win in windows:
        win_2d = _build_test_window_mask_2d(panels.close, (win,))
        win_trigger_mask = entry_mask & win_2d
        win_trigger_arr = np.asarray(win_trigger_mask.values, dtype=bool)
        win_excess = fwd_arr[win_trigger_arr]
        win_excess = win_excess[~np.isnan(win_excess)]
        win_n = len(win_excess)
        win_median = float(np.median(win_excess)) if win_n else float("nan")
        per_window.append(
            {
                "window": f"{win.test_start.isoformat()}_to_{win.test_end.isoformat()}",
                "n_obs": win_n,
                "median_excess": win_median,
                "positive": bool(win_median > 0) if win_n else False,
            }
        )

    if n_obs < MIN_TRIGGERS:
        return CandidateResult(
            rule=candidate,
            ic=float(ic) if ic is not None else float("nan"),
            tp_rate=float("nan"),
            median_excess=float("nan"),
            mean_excess=float("nan"),
            friction_adjusted_excess=float("nan"),
            percentile_10=float("nan"),
            percentile_25=float("nan"),
            percentile_50=float("nan"),
            percentile_75=float("nan"),
            percentile_90=float("nan"),
            n_observations=n_obs,
            per_window_results=tuple(per_window),
            validated=False,
        )

    median_excess = float(np.median(trigger_excess_values))
    mean_excess = float(np.mean(trigger_excess_values))
    tp_rate = float(np.mean(trigger_excess_values > 0))

    round_trip_friction = float(FRICTION_LARGE) * 2.0
    friction_adjusted = median_excess - round_trip_friction

    p10 = float(np.quantile(trigger_excess_values, 0.10))
    p25 = float(np.quantile(trigger_excess_values, 0.25))
    p50 = float(np.quantile(trigger_excess_values, 0.50))
    p75 = float(np.quantile(trigger_excess_values, 0.75))
    p90 = float(np.quantile(trigger_excess_values, 0.90))

    # Validation gate: |IC| >= 0.04 AND friction_adjusted > 0 AND at least
    # 2 of 3 windows have positive median excess.
    ic_pass = ic is not None and abs(float(ic)) >= float(IC_FLOOR_12M)
    friction_pass = friction_adjusted > 0
    windows_pos = sum(1 for w in per_window if w["positive"])
    window_pass = windows_pos >= 2
    validated = bool(ic_pass and friction_pass and window_pass)

    return CandidateResult(
        rule=candidate,
        ic=float(ic) if ic is not None else float("nan"),
        tp_rate=tp_rate,
        median_excess=median_excess,
        mean_excess=mean_excess,
        friction_adjusted_excess=friction_adjusted,
        percentile_10=p10,
        percentile_25=p25,
        percentile_50=p50,
        percentile_75=p75,
        percentile_90=p90,
        n_observations=n_obs,
        per_window_results=tuple(per_window),
        validated=validated,
    )


def _pooled_spearman_ic(
    score_panel: pd.DataFrame,
    fwd_panel: pd.DataFrame,
    universe_mask: pd.DataFrame,
) -> float | None:
    """Spearman rank IC between score and forward returns, pooled across
    (date, instrument) cells where universe_mask is True.

    Returns None if fewer than 30 valid pairs.
    """
    s_vals_arr = np.asarray(score_panel.values, dtype=float)
    f_vals_arr = np.asarray(fwd_panel.values, dtype=float)
    mask_arr = np.asarray(universe_mask.values, dtype=bool)
    s_vals = s_vals_arr[mask_arr]
    f_vals = f_vals_arr[mask_arr]
    valid = ~np.isnan(s_vals) & ~np.isnan(f_vals)
    s_vals = s_vals[valid]
    f_vals = f_vals[valid]
    if len(s_vals) < 30:
        return None
    s_ranks = np.asarray(pd.Series(s_vals).rank().values, dtype=float)
    f_ranks = np.asarray(pd.Series(f_vals).rank().values, dtype=float)
    s_std = float(np.std(s_ranks))
    f_std = float(np.std(f_ranks))
    if s_std == 0 or f_std == 0:
        return None
    corr = float(np.corrcoef(s_ranks, f_ranks)[0, 1])
    if np.isnan(corr):
        return None
    return corr


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def load_cache_panels(cache_dir: Path | None = None) -> FeaturePanels:
    """Load + shape cache OHLCV into wide feature panels.

    Raises FileNotFoundError when the cache pickles are absent.
    """
    from atlas.discovery.engine import DEFAULT_CACHE_DIR, _compute_cap_tier_panel

    cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    ohlcv, nifty500, blacklist = _load_cache_files(cache_dir)
    if blacklist:
        ohlcv = cast(pd.DataFrame, ohlcv[~ohlcv["iid"].isin(list(blacklist))].copy())
    cap_panel = _compute_cap_tier_panel(ohlcv)
    return _compute_feature_panels(ohlcv, nifty500, cap_panel)


def run_deep_search(
    cell_target: tuple[str, str, str],
    candidates: list[CandidateRule],
    panels: FeaturePanels,
    windows: tuple[WalkForwardWindow, ...] = DEFAULT_WINDOWS,
) -> DeepSearchSummary:
    """Evaluate every candidate; return ranked summary.

    Args:
        cell_target: (cap_tier, tenure, action). Used for filtering and
            for the rule_dsl persisted on best validation.
        candidates: list of CandidateRule to evaluate.
        panels: precomputed FeaturePanels (call load_cache_panels first).
        windows: walk-forward windows (defaults to DEFAULT_WINDOWS).

    Returns:
        DeepSearchSummary with candidates ranked by absolute IC descending.
    """
    cap_tier, tenure, action = cell_target
    if tenure != "12m" or action != "POSITIVE":
        # Defensive — current candidate library is hand-tuned for this cell.
        # The pipeline still works (cap_tier filter applies), but signal
        # quality outside this configuration is undefined.
        log.warning(
            "deep_search_off_cell_target",
            cap_tier=cap_tier,
            tenure=tenure,
            action=action,
            note="candidate library tuned for Large/12m/POSITIVE",
        )

    started = datetime.now(UTC)
    results: list[CandidateResult] = []
    for i, candidate in enumerate(candidates):
        log.debug("deep_search_candidate", i=i, name=candidate.name)
        try:
            result = _evaluate_candidate(candidate, panels, windows, cap_tier=cap_tier)
        except (ValueError, KeyError, TypeError) as exc:
            log.error(
                "deep_search_candidate_failed",
                name=candidate.name,
                error=str(exc),
            )
            continue
        results.append(result)

    # Rank by absolute IC descending (highest first) for the report.
    results.sort(key=lambda r: abs(r.ic) if not np.isnan(r.ic) else 0.0, reverse=True)

    completed = datetime.now(UTC)
    # The "best" for INSERT purposes is the validated candidate with
    # highest friction-adjusted excess — the economically strongest pick
    # among those that cleared the IC gate. Falls back to highest |IC|
    # if nothing validated (informational only).
    validated_results = [r for r in results if r.validated]
    best: CandidateResult | None
    if validated_results:
        validated_results.sort(key=lambda r: r.friction_adjusted_excess, reverse=True)
        best = validated_results[0]
    elif results:
        best = results[0]
    else:
        best = None

    summary = DeepSearchSummary(
        cell_target=cell_target,
        results=tuple(results),
        run_started_at=started,
        run_completed_at=completed,
        n_candidates=len(candidates),
        n_validated=len(validated_results),
        best_ic=(abs(best.ic) if best is not None and not np.isnan(best.ic) else None),
        best_rule_name=best.rule.name if best is not None else None,
    )
    log.info(
        "deep_search_complete",
        n_candidates=summary.n_candidates,
        n_validated=summary.n_validated,
        best_rule=summary.best_rule_name,
        best_ic=summary.best_ic,
        duration_s=(completed - started).total_seconds(),
    )
    return summary


def build_rule_dsl_for_candidate(
    candidate: CandidateRule,
    cell_target: tuple[str, str, str],
) -> dict[str, Any]:
    """Construct the JSONB-serialisable rule_dsl dict for INSERT.

    All entry predicates go into the ``entry`` list; the cap-tier
    liquidity floor (always first in the candidate's features) becomes
    the sole ``eligibility`` predicate.
    """
    cap_tier, tenure, action = cell_target
    eligibility: list[FeaturePredicate] = []
    entry: list[FeaturePredicate] = []
    for i, pred in enumerate(candidate.features):
        if i == 0 and pred.feature == "log_med_tv_60d":
            eligibility.append(pred)
        else:
            entry.append(pred)

    # Map archetype → rule_type literal (atlas.decisions.rule_dsl).
    # The 9 v6 archetypes accept "placeholder" as a deliberate fallback —
    # we use it for archetypes that don't cleanly map onto one of the
    # original 4 entry patterns (pullback / severely_broken / emerging /
    # topping) so the methodology audit trail records the discovery
    # provenance via the notes string, not a forced-fit rule_type.
    archetype_to_rule_type: dict[str, str] = {
        "mean_reversion": "pullback",
        "deep_value": "severely_broken",
        "quality_momentum": "accumulate",
        "inflection": "emerging",
        "consolidation_breakout": "accumulate",
        "liquidity_expansion": "accumulate",
        "structural": "hold",
    }
    rule_type = archetype_to_rule_type.get(candidate.archetype, "placeholder")
    rule = CellRule(
        rule_type=rule_type,  # type: ignore[arg-type]
        eligibility=eligibility,
        entry=entry,
        tier=cap_tier,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        tenure=tenure,  # type: ignore[arg-type]
        rule_version=1,
        methodology_lock_ref=DEEP_SEARCH_METHODOLOGY_REF,
        notes=(
            f"deep_search 2026-05-24 ({candidate.archetype}) — {candidate.rationale} "
            f"[rule={candidate.name}]"
        ),
    )
    return rule.model_dump(mode="json")


def maybe_insert_validated_cell(
    summary: DeepSearchSummary,
    db_engine: Any,
) -> uuid.UUID | None:
    """If the summary has at least one validated candidate, INSERT the best.

    Returns the inserted cell_id (UUID) or None if no candidate validated
    or db_engine is None.

    Raises any DB exception so caller can decide handling.
    """
    if db_engine is None:
        return None
    if summary.n_validated == 0:
        return None
    # Pick the validated candidate with the highest friction-adjusted
    # excess — matches the "best" identification in :func:`run_deep_search`.
    validated = [r for r in summary.results if r.validated]
    if not validated:
        return None
    best = max(validated, key=lambda r: r.friction_adjusted_excess)

    rule_dsl = build_rule_dsl_for_candidate(best.rule, summary.cell_target)
    summary.inserted_rule_dsl = rule_dsl

    from sqlalchemy import text

    cell_id = uuid.uuid4()
    walkforward_run_id = uuid.uuid4()
    with db_engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_cell_definitions (
                    cell_id, cap_tier, action, tenure, rule_dsl,
                    confidence_unconditional, friction_adjusted_excess,
                    stable_features, methodology_lock_ref,
                    walkforward_run_id, validated_at
                ) VALUES (
                    :cell_id, :cap_tier, :action, :tenure, CAST(:rule_dsl AS JSONB),
                    :confidence_unconditional, :friction_adjusted_excess,
                    CAST(:stable_features AS JSONB), :methodology_lock_ref,
                    :walkforward_run_id, NOW()
                )
                """
            ),
            {
                "cell_id": str(cell_id),
                "cap_tier": summary.cell_target[0],
                "action": summary.cell_target[2],
                "tenure": summary.cell_target[1],
                "rule_dsl": json.dumps(rule_dsl, default=str),
                "confidence_unconditional": Decimal(str(round(best.tp_rate, 4))),
                "friction_adjusted_excess": Decimal(str(round(best.friction_adjusted_excess, 6))),
                "stable_features": json.dumps([p.feature for p in best.rule.features]),
                "methodology_lock_ref": DEEP_SEARCH_METHODOLOGY_REF,
                "walkforward_run_id": str(walkforward_run_id),
            },
        )
        conn.commit()
    summary.inserted_cell_id = cell_id
    log.info(
        "deep_search_cell_inserted",
        cell_id=str(cell_id),
        rule=best.rule.name,
        ic=best.ic,
        friction_adjusted=best.friction_adjusted_excess,
    )
    return cell_id


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_cli_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        prog="atlas.discovery.deep_search",
        description="Atlas v6 deep-search per-cell exhaustive feature exploration",
    )
    parser.add_argument(
        "--cell",
        default="Large/12m/POSITIVE",
        help="Cell target in form cap_tier/tenure/action (default: Large/12m/POSITIVE)",
    )
    parser.add_argument(
        "--mode",
        default="cache",
        choices=["cache"],
        help="data-source mode (only 'cache' supported today)",
    )
    parser.add_argument(
        "--output-html",
        default=None,
        help="path to write the deep-search HTML report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="don't INSERT into atlas_cell_definitions even if a candidate validates",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry — returns exit code (0=success, 1=no validation, 2=fatal)."""
    args = _build_cli_parser().parse_args(argv)

    try:
        cap_tier, tenure, action = args.cell.split("/")
    except ValueError:
        print(json.dumps({"error": f"--cell must be cap_tier/tenure/action, got {args.cell!r}"}))
        return 2

    log.info("deep_search_cli_start", cell=args.cell, mode=args.mode)

    try:
        panels = load_cache_panels()
    except FileNotFoundError as exc:
        print(json.dumps({"error": f"cache missing: {exc}"}))
        return 2

    if action != "POSITIVE" or tenure != "12m" or cap_tier != "Large":
        log.warning(
            "deep_search_off_cell_target_cli",
            note="candidate library is currently tuned for Large/12m/POSITIVE",
        )

    candidates = generate_candidates_large_12m_positive()

    summary = run_deep_search(
        cell_target=(cap_tier, tenure, action),
        candidates=candidates,
        panels=panels,
    )

    # Optionally INSERT.
    if not args.dry_run and summary.n_validated > 0:
        try:
            from atlas.db import get_engine

            engine = get_engine()
            maybe_insert_validated_cell(summary, engine)
        except (RuntimeError, OSError, ValueError) as exc:
            log.error("deep_search_insert_skipped", error=str(exc))

    # Render HTML.
    if args.output_html:
        from atlas.discovery.deep_search_report import generate_deep_search_report

        out_path = Path(args.output_html)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        generate_deep_search_report(summary, output_path=out_path)
        log.info("deep_search_html_written", path=str(out_path))

    # Print summary to stdout (programmatic consumer).
    print(
        json.dumps(
            {
                "cell": args.cell,
                "n_candidates": summary.n_candidates,
                "n_validated": summary.n_validated,
                "best_ic": summary.best_ic,
                "best_rule": summary.best_rule_name,
                "inserted_cell_id": (
                    str(summary.inserted_cell_id) if summary.inserted_cell_id else None
                ),
                "output_html": args.output_html,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if summary.n_validated > 0 else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
