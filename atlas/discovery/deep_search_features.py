"""Feature-panel computation for :mod:`atlas.discovery.deep_search` v2.

This module computes ALL wide-form feature panels (date × iid) needed by
the per-cell candidate evaluator. Split out from ``deep_search.py`` to
keep the LOC budget per module within the 600-line guardrail.

Vectorised end-to-end — no Python loops over instruments. Streaks are
done with a vectorised groupby-cumcount trick on the boolean panel.

All panels are reachable through :func:`panel_for_feature` so the
generic predicate evaluator never needs to know which panel a feature
lives on.
"""

# allow-large: cohesive feature-panel computation. Each panel is short
# but there are ~50 of them; splitting further would fragment the
# methodology surface and hide cross-feature dependencies.

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

from atlas.discovery import _sector_panels as _sec
from atlas.discovery.engine import TENURE_TO_HORIZON_DAYS

# ---------------------------------------------------------------------------
# Dataclass — all panels in one place
# ---------------------------------------------------------------------------


@dataclass
class FeaturePanels:
    """All feature panels needed by deep-search candidates.

    Each panel is a wide DataFrame (index=date, columns=iid). Cap_tier
    membership is a categorical panel too. Forward returns are precomputed
    once per horizon (1m / 3m / 6m / 12m).
    """

    # Universe primitives.
    close: pd.DataFrame
    volume: pd.DataFrame
    cap_tier: pd.DataFrame  # categorical strings (Small/Mid/Large)
    nifty: pd.Series

    # v1 features (kept for backwards-compat).
    log_med_tv_60d: pd.DataFrame
    realized_vol_60d: pd.DataFrame
    realized_vol_252d: pd.DataFrame
    rs_residual_3m: pd.DataFrame
    rs_residual_6m: pd.DataFrame
    rs_residual_12m: pd.DataFrame
    rs_rank_6m: pd.DataFrame
    rs_rank_12m: pd.DataFrame
    rs_rank_3m: pd.DataFrame
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

    # v2 features (Phase 0.5g extension).
    rs_residual_1m: pd.DataFrame
    realized_vol_20d: pd.DataFrame
    vol_regime_60_252: pd.DataFrame
    downside_vol_60d: pd.DataFrame
    volume_zscore_252d: pd.DataFrame
    tv_momentum_21_63: pd.DataFrame
    roc_21d: pd.DataFrame
    roc_63d: pd.DataFrame
    roc_126d: pd.DataFrame
    max_consec_pos_months_12m: pd.DataFrame
    pos_weeks_12m: pd.DataFrame
    dd_recovery_pct: pd.DataFrame
    dist_from_52w_low: pd.DataFrame
    close_at_52w_high: pd.DataFrame
    consecutive_above_sma50: pd.DataFrame
    consecutive_above_sma200: pd.DataFrame
    rsi_14: pd.DataFrame
    bb_pct_20d: pd.DataFrame
    atr_pct_14: pd.DataFrame
    corr_to_nifty_60d: pd.DataFrame
    beta_60d: pd.DataFrame
    excess_vol_60d: pd.DataFrame
    rs_rank_6m_3m_diff: pd.DataFrame
    rs_rank_12m_6m_diff: pd.DataFrame
    range_compression_60_252: pd.DataFrame
    ulcer_index_60d: pd.DataFrame
    momentum_quality_6m: pd.DataFrame
    trend_strength_60d: pd.DataFrame
    new_high_streak_60d: pd.DataFrame
    close_over_252d_high: pd.DataFrame

    # Red-team quick-win features (Phase 0.5g gap closures).
    amihud_illiq_21d: pd.DataFrame
    obv_slope_60d: pd.DataFrame
    mfi_14: pd.DataFrame
    bb_squeeze_20d: pd.DataFrame
    rs_rank_within_tier_3m: pd.DataFrame
    rs_rank_within_tier_6m: pd.DataFrame
    rs_rank_within_tier_12m: pd.DataFrame

    # Sector relative-strength panels (broadcast to iid columns where
    # appropriate; date-indexed scalar for cross_sector_breadth).
    sector_rs_6m: pd.DataFrame
    sector_rs_12m: pd.DataFrame
    sector_rs_rank_6m: pd.DataFrame
    sector_breadth_pos: pd.DataFrame  # broadcast (date × iid)
    sector_strength_rank: pd.DataFrame  # broadcast (date × iid)
    sector_vol_regime: pd.DataFrame  # broadcast (date × iid)
    cross_sector_breadth: pd.DataFrame  # broadcast (date × iid)

    # Forward returns at each horizon (252d, 126d, 63d, 21d).
    fwd_excess_21d: pd.DataFrame
    fwd_excess_63d: pd.DataFrame
    fwd_excess_126d: pd.DataFrame
    fwd_excess_252d: pd.DataFrame

    def fwd_excess_for_tenure(self, tenure: str) -> pd.DataFrame:
        """Return the forward-excess panel matching ``tenure``."""
        mapping = {
            "1m": self.fwd_excess_21d,
            "3m": self.fwd_excess_63d,
            "6m": self.fwd_excess_126d,
            "12m": self.fwd_excess_252d,
        }
        if tenure not in mapping:
            raise KeyError(f"unknown tenure {tenure!r}")
        return mapping[tenure]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_rs_residual(
    close: pd.DataFrame, nifty: pd.Series, formation_days: int, skip_days: int = 21
) -> pd.DataFrame:
    """β-adjusted formation-window return vs Nifty 500.

    Vectorised end-to-end — no Python loop over instruments.
    """
    stock_daily = close.pct_change(fill_method=None)
    nifty_daily = nifty.pct_change(fill_method=None)
    cov = stock_daily.rolling(60, min_periods=40).cov(nifty_daily)
    var = cast(pd.Series, nifty_daily.rolling(60, min_periods=40).var())
    var_safe = var.replace(0, np.nan)
    beta = cov.div(var_safe, axis=0).shift(skip_days)
    stock_ret = close.shift(skip_days) / close.shift(formation_days) - 1.0
    nifty_ret = nifty.shift(skip_days) / nifty.shift(formation_days) - 1.0
    expected = beta.mul(nifty_ret, axis=0)
    return cast(pd.DataFrame, stock_ret.sub(expected))


def _streak_above(boolean_panel: pd.DataFrame) -> pd.DataFrame:
    """Vectorised current-streak length per column.

    For each column, returns the number of consecutive ``True`` values
    ending at each row index (0 when False). Uses the per-column
    cumcount-on-reset trick — O(n) per column but pure vector ops.
    """
    # Replace NaN with False before the streak compute (NaN → not streak).
    panel = boolean_panel.fillna(False).astype(bool)
    out_cols: dict[str, np.ndarray] = {}
    for col in panel.columns:
        s = np.asarray(panel[col].to_numpy(), dtype=bool)
        # Reset groups whenever False; cumcount within True-runs.
        # The trick: cumsum of (~s) gives a unique group id per True-run.
        # Then groupby-cumcount within each group gives positions.
        not_s = (~s).astype(np.int64)
        group = not_s.cumsum()
        # Within each group, the cumulative count of positions where s
        # is True (and we want it 1-based at the True positions, 0 where
        # False).
        ones = s.astype(np.int64)
        # cumulative ones within each group via pandas.
        ser = pd.Series(ones)
        grp = pd.Series(group)
        streak = np.asarray(ser.groupby(grp).cumsum().to_numpy(), dtype=np.int64)
        # Zero out False positions.
        streak = streak * ones
        out_cols[col] = streak.astype(float)
    return pd.DataFrame(out_cols, index=panel.index, columns=panel.columns)


def _ulcer_index(close: pd.DataFrame, window: int) -> pd.DataFrame:
    """Ulcer index = sqrt(mean(dd^2, window)) where dd is drawdown from rolling max."""
    rolling_max = close.rolling(window, min_periods=int(window * 0.6)).max()
    dd = close / rolling_max - 1.0  # values are <= 0
    dd_sq = dd * dd
    return cast(
        pd.DataFrame,
        np.sqrt(dd_sq.rolling(window, min_periods=int(window * 0.6)).mean()),
    )


def _trend_strength_60d(log_price: pd.DataFrame) -> pd.DataFrame:
    """Closed-form rolling-r^2 of log_price ~ t (over 60d).

    r^2 = cov(price, t)^2 / (var(price) * var(t)). Vectorised via
    rolling means.
    """
    win = 60
    n = win
    # Time index 0..n-1 has fixed mean (n-1)/2 and variance.
    t_mean = (n - 1) / 2.0
    t_var = (n * n - 1) / 12.0  # variance of 0..n-1 (population)
    # Build a "t" panel matching shape: just the integer offset which we
    # reduce inline via E[X*t] = sum(X*t)/n where the t sequence is fixed.
    # Use rolling apply of weighted sums; but we can do it more cleanly:
    # cov(x, t) = E[x*t] - E[x]*E[t]
    # E[x*t] over a rolling window is the dot product of x with [0..n-1]/n.
    # We use a rolling sum of x weighted by index — implement via shift tricks:
    # sum_{k=0..n-1} k * x_{t-k} = sum over k of k * x.shift(k).
    # That's O(n) per column. For n=60 this is fine.
    weighted = sum(k * log_price.shift(k) for k in range(n))  # type: ignore[arg-type]
    x_sum = log_price.rolling(win, min_periods=int(win * 0.6)).sum()
    x_sq_sum = (log_price * log_price).rolling(win, min_periods=int(win * 0.6)).sum()

    # E[x] = x_sum / n; var(x) (pop) = E[x^2] - E[x]^2.
    x_mean = x_sum / n
    x_var = (x_sq_sum / n) - x_mean * x_mean
    # cov(x, t) = E[x*t] - E[x]*t_mean. Note weighted is reversed order
    # (k=0 is the newest), but t_mean is symmetric so doesn't matter for
    # variance; for cov sign we want covariance with increasing t. Since
    # we used k=0..n-1 against shift(k), our pseudo-t runs n-1, n-2, ... 0
    # in real order. Flip sign for slope direction by negating.
    cov_xt = -((weighted / n) - x_mean * t_mean)  # negate for forward time
    var_safe = (x_var * t_var).replace(0, np.nan)
    r2 = (cov_xt * cov_xt) / var_safe
    # Clip to [0,1] for safety (numerical noise).
    return cast(pd.DataFrame, r2.clip(lower=0.0, upper=1.0))


def _rsi_14(daily: pd.DataFrame) -> pd.DataFrame:
    """Wilder's RSI(14) computed via EWM with alpha=1/14.

    Vectorised: ewm.mean is per-column. NaN-safe.
    """
    gain = daily.clip(lower=0.0)
    loss = (-daily.clip(upper=0.0)).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return cast(pd.DataFrame, rsi)


def _bollinger_pct(close: pd.DataFrame) -> pd.DataFrame:
    """Position relative to 20d Bollinger bands in std-units."""
    sma20 = close.rolling(20, min_periods=15).mean()
    std20 = close.rolling(20, min_periods=15).std().replace(0, np.nan)
    return cast(pd.DataFrame, (close - sma20) / (2.0 * std20))


# ---------------------------------------------------------------------------
# Master computation
# ---------------------------------------------------------------------------


def _money_flow_index_14(close: pd.DataFrame, tv: pd.DataFrame) -> pd.DataFrame:
    """Money Flow Index (MFI) on a close-proxy typical price.

    Since the cache only has close + volume (no high/low), we use close
    as the typical price. positive_mf sums turnover (price × volume) on
    up-days; negative_mf sums on down-days. Window is 14 days (Wilder
    original).
    """
    daily_diff = close.diff()
    pos_flow = tv.where(daily_diff > 0, 0.0)
    neg_flow = tv.where(daily_diff < 0, 0.0)
    pos_sum = cast(pd.DataFrame, pos_flow.rolling(14, min_periods=10).sum())
    neg_sum = cast(pd.DataFrame, neg_flow.rolling(14, min_periods=10).sum()).replace(0, np.nan)
    money_ratio = pos_sum / neg_sum
    mfi = 100.0 - 100.0 / (1.0 + money_ratio)
    return cast(pd.DataFrame, mfi)


def _amihud_illiq_21d(daily: pd.DataFrame, tv: pd.DataFrame) -> pd.DataFrame:
    """Amihud (2002) illiquidity: rolling mean of |return| / turnover.

    High values = high price-impact per unit turnover. Guard against
    zero turnover and infinity.
    """
    tv_safe = tv.replace(0, np.nan)
    ratio = daily.abs() / tv_safe
    # Replace inf with NaN before rolling — pandas can produce inf when
    # turnover sneaks below floating-point zero.
    ratio = ratio.replace([np.inf, -np.inf], np.nan)
    return cast(pd.DataFrame, ratio.rolling(21, min_periods=15).mean())


def _obv_slope_60d(daily: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """60-day slope of on-balance-volume.

    OBV cumulates sign(daily) × volume. Slope = (obv_t - obv_{t-60})/60
    per column; positive = accumulation, negative = distribution.
    """
    sign_df = cast(pd.DataFrame, np.sign(daily.fillna(0.0)))
    signed_vol = sign_df.mul(volume)
    obv = signed_vol.cumsum()
    return cast(pd.DataFrame, (obv - obv.shift(60)) / 60.0)


def _bb_squeeze_20d(close: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional bb-squeeze indicator.

    Returns 1.0 where the per-instrument 20d band width (2σ/SMA) is
    BELOW the cross-sectional 25th percentile on that date — i.e. the
    stock is in the tightest quartile of its universe. 0.0 otherwise.
    """
    sma20 = cast(pd.DataFrame, close.rolling(20, min_periods=15).mean())
    std20 = cast(pd.DataFrame, close.rolling(20, min_periods=15).std())
    width = (2.0 * std20) / sma20.replace(0, np.nan)
    p25_per_date = width.quantile(0.25, axis=1)
    return cast(pd.DataFrame, (width.le(p25_per_date, axis=0)).astype(float))


def _rs_rank_within_tier(rs_residual: pd.DataFrame, cap_tier: pd.DataFrame) -> pd.DataFrame:
    """Per-date, per-tier percentile rank of ``rs_residual``.

    Uses the staging-style per-tier groupby: for each date, partitions
    iids by cap_tier and ranks within each tier. cap_tier NaN cells
    propagate NaN ranks.
    """
    # We transpose so dates become columns; within each date column we
    # group by tier label and rank.
    out = pd.DataFrame(np.nan, index=rs_residual.index, columns=rs_residual.columns)
    # Vectorised approach: per-date rank within tier using groupby on
    # transposed (iid × date) layout. The classic trick:
    # melt → groupby(date, tier) → rank → pivot back. Faster for small
    # date counts:
    rs_t = rs_residual.T  # iid × date
    tier_t = cap_tier.T  # iid × date
    for d in rs_t.columns:
        s = cast(pd.Series, rs_t[d])
        t = cast(pd.Series, tier_t[d])
        # Drop iids with NaN tier (can't bucket them).
        mask = t.notna()
        if int(mask.sum()) == 0:
            continue
        s_v = cast(pd.Series, s[mask])
        t_v = cast(pd.Series, t[mask])
        ranks = s_v.groupby(t_v, observed=False).rank(pct=True)
        out.loc[d, ranks.index] = ranks.to_numpy()
    return out


def compute_feature_panels(
    ohlcv: pd.DataFrame,
    nifty500: pd.Series,
    cap_tier_long: pd.DataFrame,
    sector_of: pd.Series | None = None,
) -> FeaturePanels:
    """Compute every feature panel needed by deep-search candidates.

    Args:
        ohlcv: long-form DataFrame (date, iid, close, volume).
        nifty500: benchmark series (date-indexed).
        cap_tier_long: long-form (date, iid, cap_tier).

    Returns:
        :class:`FeaturePanels` with everything wired.
    """
    close = ohlcv.pivot(index="date", columns="iid", values="close").sort_index()
    volume = ohlcv.pivot(index="date", columns="iid", values="volume").sort_index()

    nifty = nifty500.reindex(close.index).ffill()

    cap_wide = cap_tier_long.pivot(index="date", columns="iid", values="cap_tier")
    cap_wide = cap_wide.reindex(index=close.index, columns=close.columns)

    daily = close.pct_change(fill_method=None)
    nifty_daily = nifty.pct_change(fill_method=None)
    tv = close * volume

    # --- v1 panels (unchanged from deep_search v1) ----------------------
    log_med_tv_60d = cast(pd.DataFrame, np.log(tv.rolling(60, min_periods=30).median()))
    realized_vol_60d = cast(pd.DataFrame, daily.rolling(60, min_periods=40).std())
    realized_vol_252d = cast(pd.DataFrame, daily.rolling(252, min_periods=150).std())

    high_252 = close.rolling(252, min_periods=120).max()
    low_252 = close.rolling(252, min_periods=120).min()
    high_60 = close.rolling(60, min_periods=40).max()
    high_30 = close.rolling(30, min_periods=20).max()
    high_756 = close.rolling(756, min_periods=300).max()
    high_1260 = close.rolling(1260, min_periods=500).max()
    dd_from_52w_high = close / high_252 - 1.0
    dd_from_3y_high = close / high_756 - 1.0
    dd_from_5y_high = close / high_1260 - 1.0

    rolling_max_105 = close.rolling(105, min_periods=60).max()
    rolling_dd_105 = close / rolling_max_105 - 1.0
    formation_max_dd = rolling_dd_105.rolling(105, min_periods=60).min().shift(21)

    sma50 = close.rolling(50, min_periods=30).mean()
    sma200 = close.rolling(200, min_periods=150).mean()
    dist_above_sma50 = close / sma50 - 1.0
    dist_above_sma200 = close / sma200 - 1.0
    sma50_gt_sma200 = cast(pd.DataFrame, (sma50 > sma200).astype(float))

    listing_age_days = close.notna().cumsum()

    close_over_30d_high = cast(pd.DataFrame, (close >= high_30 * 0.99).astype(float))
    close_over_60d_high = cast(pd.DataFrame, (close >= high_60 * 0.99).astype(float))
    close_over_252d_high = cast(pd.DataFrame, (close >= high_252 * 0.99).astype(float))
    close_at_52w_high = close_over_252d_high.copy()  # alias

    tv_21 = tv.rolling(21, min_periods=15).mean()
    tv_63 = tv.rolling(63, min_periods=40).mean()
    tv_252 = tv.rolling(252, min_periods=150).mean()
    tv_252_std = tv.rolling(252, min_periods=150).std().replace(0, np.nan)
    volume_zscore_60d = (tv_21 - tv_252) / tv_252_std
    volume_zscore_252d = (tv_63 - tv_252) / tv_252_std
    tv_momentum_21_63 = tv_21 / tv_63.replace(0, np.nan)

    # pos_months_12m + max-consec-pos via 12 stacked 21d returns
    monthly_rets = [(close.shift(k * 21) / close.shift((k + 1) * 21) - 1.0) for k in range(12)]
    arr = np.stack([r.values for r in monthly_rets])  # (12, T, N)
    pos = (arr > 0).astype(float)
    valid = ~np.isnan(arr)
    cnt = valid.sum(axis=0)
    pos0 = np.where(valid, pos, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(cnt > 0, pos0.sum(axis=0) / cnt, np.nan)
    pos_months_12m = pd.DataFrame(frac, index=close.index, columns=close.columns)

    # Max consecutive positive months in last 12. Walk down the stack from
    # newest (k=0) to oldest (k=11), tracking runs.
    pos_arr = (arr > 0).astype(np.int64)  # (12, T, N); ignore NaN (treated 0)
    max_run = np.zeros(pos_arr.shape[1:], dtype=np.int64)
    cur = np.zeros(pos_arr.shape[1:], dtype=np.int64)
    for k in range(pos_arr.shape[0]):
        cur = np.where(pos_arr[k] == 1, cur + 1, 0)
        max_run = np.maximum(max_run, cur)
    max_consec_pos_months_12m = pd.DataFrame(
        max_run.astype(float), index=close.index, columns=close.columns
    )

    # pos_weeks_12m: fraction of last 52 weekly (5d) returns > 0
    weekly_rets = [(close.shift(k * 5) / close.shift((k + 1) * 5) - 1.0) for k in range(52)]
    warr = np.stack([r.values for r in weekly_rets])
    wpos = (warr > 0).astype(float)
    wvalid = ~np.isnan(warr)
    wcnt = wvalid.sum(axis=0)
    wpos0 = np.where(wvalid, wpos, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        wfrac = np.where(wcnt > 0, wpos0.sum(axis=0) / wcnt, np.nan)
    pos_weeks_12m = pd.DataFrame(wfrac, index=close.index, columns=close.columns)

    # RS residuals 1m/3m/6m/12m
    rs_residual_1m = compute_rs_residual(close, nifty, 21)
    rs_residual_3m = compute_rs_residual(close, nifty, 63)
    rs_residual_6m = compute_rs_residual(close, nifty, 126)
    rs_residual_12m = compute_rs_residual(close, nifty, 252)
    rs_rank_3m = rs_residual_3m.rank(axis=1, pct=True)
    rs_rank_6m = rs_residual_6m.rank(axis=1, pct=True)
    rs_rank_12m = rs_residual_12m.rank(axis=1, pct=True)

    rs_alignment_count = cast(
        pd.DataFrame,
        (rs_rank_3m >= 0.75).astype(float)
        + (rs_rank_6m >= 0.75).astype(float)
        + (rs_rank_12m >= 0.75).astype(float),
    )
    rs_acceleration_63d = rs_rank_6m - rs_rank_6m.shift(63)
    rs_rank_6m_3m_diff = rs_rank_6m - rs_rank_3m
    rs_rank_12m_6m_diff = rs_rank_12m - rs_rank_6m

    log_price = cast(pd.DataFrame, np.log(close.clip(lower=1e-9)))
    trend_slope_60d = (log_price - log_price.shift(60)) / 60.0

    # --- v2 new panels --------------------------------------------------
    realized_vol_20d = cast(pd.DataFrame, daily.rolling(20, min_periods=15).std())
    vol_regime_60_252 = realized_vol_60d / realized_vol_252d.replace(0, np.nan)

    downside = daily.clip(upper=0.0)
    downside_vol_60d = cast(pd.DataFrame, downside.rolling(60, min_periods=40).std())

    roc_21d = close / close.shift(21) - 1.0
    roc_63d = close / close.shift(63) - 1.0
    roc_126d = close / close.shift(126) - 1.0

    dd_recovery_pct = (close - low_252) / (high_252 - low_252).replace(0, np.nan)
    dist_from_52w_low = close / low_252.replace(0, np.nan) - 1.0

    above_sma50 = (close > sma50).fillna(False).astype(bool)
    above_sma200 = (close > sma200).fillna(False).astype(bool)
    consecutive_above_sma50 = _streak_above(above_sma50)
    consecutive_above_sma200 = _streak_above(above_sma200)

    rsi_14 = _rsi_14(daily)
    bb_pct_20d = _bollinger_pct(close)

    # ATR proxy: when only close+volume in cache, use |daily| as range
    # approximation. Scale by close to get ratio.
    daily_range_abs = daily.abs()
    atr_pct_14 = cast(
        pd.DataFrame, daily_range_abs.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    )

    # Rolling 60d correlation/beta vs nifty.
    cov_60 = cast(pd.DataFrame, daily.rolling(60, min_periods=40).cov(nifty_daily))
    var_60 = cast(pd.Series, nifty_daily.rolling(60, min_periods=40).var())
    beta_60d = cast(pd.DataFrame, cov_60.div(var_60.replace(0, np.nan), axis=0))

    stock_std_60 = cast(pd.DataFrame, daily.rolling(60, min_periods=40).std())
    nifty_std_60 = cast(pd.Series, nifty_daily.rolling(60, min_periods=40).std())
    denom_corr = cast(pd.DataFrame, stock_std_60.mul(nifty_std_60, axis=0).replace(0, np.nan))
    corr_to_nifty_60d = cast(pd.DataFrame, cov_60.div(denom_corr, axis=0))

    # Excess vol (vs cross-sectional median per date).
    vol_median = realized_vol_60d.median(axis=1)
    excess_vol_60d = realized_vol_60d.sub(vol_median, axis=0)

    daily_range = daily.abs()
    range_60 = cast(pd.DataFrame, daily_range.rolling(60, min_periods=40).mean())
    range_252 = cast(pd.DataFrame, daily_range.rolling(252, min_periods=150).mean())
    range_compression_60_252 = range_60 / range_252.replace(0, np.nan)

    ulcer_index_60d = _ulcer_index(close, 60)

    momentum_quality_6m = rs_residual_6m / realized_vol_60d.replace(0, np.nan)
    # Clip extreme values (huge moves on thin vol).
    momentum_quality_6m = momentum_quality_6m.clip(lower=-50.0, upper=50.0)

    trend_strength_60d = _trend_strength_60d(log_price)

    # New-high streak: count days in last 60d where close = rolling max
    # i.e. at a new 60d high. Use a boolean and rolling sum.
    is_new_high = (close >= high_60 * 0.99).astype(float)
    new_high_streak_60d = is_new_high.rolling(60, min_periods=40).sum()

    # --- red-team quick-win panels (Phase 0.5g) ------------------------
    amihud_illiq_21d = _amihud_illiq_21d(daily, tv)
    obv_slope_60d = _obv_slope_60d(daily, volume)
    mfi_14 = _money_flow_index_14(close, tv)
    bb_squeeze_20d = _bb_squeeze_20d(close)
    rs_rank_within_tier_3m = _rs_rank_within_tier(rs_residual_3m, cap_wide)
    rs_rank_within_tier_6m = _rs_rank_within_tier(rs_residual_6m, cap_wide)
    rs_rank_within_tier_12m = _rs_rank_within_tier(rs_residual_12m, cap_wide)

    # --- sector RS panels (Phase 0.5g; NaN-fallback when mapping absent) ---
    iid_columns = close.columns
    nan_panel = pd.DataFrame(np.nan, index=close.index, columns=iid_columns, dtype=float)
    if sector_of is None or len(sector_of) == 0:
        sector_rs_6m_panel = nan_panel.copy()
        sector_rs_12m_panel = nan_panel.copy()
        sector_rs_rank_6m_panel = nan_panel.copy()
        sector_breadth_pos_panel = nan_panel.copy()
        sector_strength_rank_panel = nan_panel.copy()
        sector_vol_regime_panel = nan_panel.copy()
        cross_sector_breadth_panel = nan_panel.copy()
    else:
        # Force iid columns to string for safe index intersection with the
        # mapping index (which we coerced to str in load_sector_mapping).
        close_str_cols = close.copy()
        close_str_cols.columns = close_str_cols.columns.astype(str)
        r6_sector = close_str_cols.pct_change(126, fill_method=None)
        r12_sector = close_str_cols.pct_change(252, fill_method=None)

        sec_mean_6 = _sec.sector_cohort_mean_loo(r6_sector, sector_of)
        sec_mean_12 = _sec.sector_cohort_mean_loo(r12_sector, sector_of)
        sector_rs_6m_str = r6_sector.subtract(sec_mean_6, fill_value=np.nan)
        sector_rs_12m_str = r12_sector.subtract(sec_mean_12, fill_value=np.nan)
        sector_rs_rank_6m_str = _sec.within_sector_rank(r6_sector, sector_of)

        sec_breadth = _sec.sector_breadth(sector_rs_6m_str, sector_of)
        sec_median_6 = _sec.sector_median_return(r6_sector, sector_of)
        sec_strength = _sec.sector_strength_rank(sec_median_6)
        # realized_vol_60d is in original iid columns — coerce to str for
        # the sector groupby.
        vol_str = realized_vol_60d.copy()
        vol_str.columns = vol_str.columns.astype(str)
        sec_vol = _sec.sector_vol_regime_panel(vol_str, sector_of)

        # Broadcast back to original iid columns. Mapping str→original.
        original_to_str = {c: str(c) for c in iid_columns}
        iid_to_sector = pd.Series(
            {c: sector_of.get(original_to_str[c], np.nan) for c in iid_columns}
        )

        def _restore_cols(df: pd.DataFrame) -> pd.DataFrame:
            # Reindex to string columns then rename to original iid type.
            df = df.reindex(columns=[original_to_str[c] for c in iid_columns])
            df.columns = iid_columns
            return df

        sector_rs_6m_panel = _restore_cols(sector_rs_6m_str)
        sector_rs_12m_panel = _restore_cols(sector_rs_12m_str)
        sector_rs_rank_6m_panel = _restore_cols(sector_rs_rank_6m_str)
        sector_breadth_pos_panel = _sec.broadcast_sector_to_iid(
            sec_breadth, iid_to_sector, iid_columns
        )
        sector_strength_rank_panel = _sec.broadcast_sector_to_iid(
            sec_strength, iid_to_sector, iid_columns
        )
        sector_vol_regime_panel = _sec.broadcast_sector_to_iid(sec_vol, iid_to_sector, iid_columns)
        # Cross-sector breadth is a date-level series; broadcast to iid columns.
        cross_breadth = (sec_median_6 > 0).mean(axis=1)
        cross_arr = np.tile(cross_breadth.values.astype(float)[:, None], (1, len(iid_columns)))
        cross_sector_breadth_panel = pd.DataFrame(cross_arr, index=close.index, columns=iid_columns)

    # --- forward returns at each horizon -------------------------------
    fwd_panels: dict[str, pd.DataFrame] = {}
    for tenure, h in TENURE_TO_HORIZON_DAYS.items():
        fwd = close.shift(-h) / close - 1.0
        nifty_fwd = (nifty.shift(-h) / nifty) - 1.0
        fwd_panels[tenure] = fwd.sub(nifty_fwd, axis=0)

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
        rs_rank_3m=rs_rank_3m,
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
        # v2 extension features
        rs_residual_1m=rs_residual_1m,
        realized_vol_20d=realized_vol_20d,
        vol_regime_60_252=vol_regime_60_252,
        downside_vol_60d=downside_vol_60d,
        volume_zscore_252d=volume_zscore_252d,
        tv_momentum_21_63=tv_momentum_21_63,
        roc_21d=roc_21d,
        roc_63d=roc_63d,
        roc_126d=roc_126d,
        max_consec_pos_months_12m=max_consec_pos_months_12m,
        pos_weeks_12m=pos_weeks_12m,
        dd_recovery_pct=dd_recovery_pct,
        dist_from_52w_low=dist_from_52w_low,
        close_at_52w_high=close_at_52w_high,
        consecutive_above_sma50=consecutive_above_sma50,
        consecutive_above_sma200=consecutive_above_sma200,
        rsi_14=rsi_14,
        bb_pct_20d=bb_pct_20d,
        atr_pct_14=atr_pct_14,
        corr_to_nifty_60d=corr_to_nifty_60d,
        beta_60d=beta_60d,
        excess_vol_60d=excess_vol_60d,
        rs_rank_6m_3m_diff=rs_rank_6m_3m_diff,
        rs_rank_12m_6m_diff=rs_rank_12m_6m_diff,
        range_compression_60_252=range_compression_60_252,
        ulcer_index_60d=ulcer_index_60d,
        momentum_quality_6m=momentum_quality_6m,
        trend_strength_60d=trend_strength_60d,
        new_high_streak_60d=new_high_streak_60d,
        close_over_252d_high=close_over_252d_high,
        amihud_illiq_21d=amihud_illiq_21d,
        obv_slope_60d=obv_slope_60d,
        mfi_14=mfi_14,
        bb_squeeze_20d=bb_squeeze_20d,
        rs_rank_within_tier_3m=rs_rank_within_tier_3m,
        rs_rank_within_tier_6m=rs_rank_within_tier_6m,
        rs_rank_within_tier_12m=rs_rank_within_tier_12m,
        sector_rs_6m=sector_rs_6m_panel,
        sector_rs_12m=sector_rs_12m_panel,
        sector_rs_rank_6m=sector_rs_rank_6m_panel,
        sector_breadth_pos=sector_breadth_pos_panel,
        sector_strength_rank=sector_strength_rank_panel,
        sector_vol_regime=sector_vol_regime_panel,
        cross_sector_breadth=cross_sector_breadth_panel,
        fwd_excess_21d=fwd_panels["1m"],
        fwd_excess_63d=fwd_panels["3m"],
        fwd_excess_126d=fwd_panels["6m"],
        fwd_excess_252d=fwd_panels["12m"],
    )


def panel_for_feature(panels: FeaturePanels, feature_name: str) -> pd.DataFrame:
    """Map a FEATURES-allowlist name to its computed panel."""
    mapping: dict[str, pd.DataFrame] = {
        # v1
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
        # v2 extension
        "rs_residual_1m": panels.rs_residual_1m,
        "realized_vol_20d": panels.realized_vol_20d,
        "vol_regime_60_252": panels.vol_regime_60_252,
        "downside_vol_60d": panels.downside_vol_60d,
        "volume_zscore_252d": panels.volume_zscore_252d,
        "tv_momentum_21_63": panels.tv_momentum_21_63,
        "roc_21d": panels.roc_21d,
        "roc_63d": panels.roc_63d,
        "roc_126d": panels.roc_126d,
        "max_consec_pos_months_12m": panels.max_consec_pos_months_12m,
        "pos_weeks_12m": panels.pos_weeks_12m,
        "dd_recovery_pct": panels.dd_recovery_pct,
        "dist_from_52w_low": panels.dist_from_52w_low,
        "close_at_52w_high": panels.close_at_52w_high,
        "consecutive_above_sma50": panels.consecutive_above_sma50,
        "consecutive_above_sma200": panels.consecutive_above_sma200,
        "rsi_14": panels.rsi_14,
        "bb_pct_20d": panels.bb_pct_20d,
        "atr_pct_14": panels.atr_pct_14,
        "corr_to_nifty_60d": panels.corr_to_nifty_60d,
        "beta_60d": panels.beta_60d,
        "excess_vol_60d": panels.excess_vol_60d,
        "rs_rank_6m_3m_diff": panels.rs_rank_6m_3m_diff,
        "rs_rank_12m_6m_diff": panels.rs_rank_12m_6m_diff,
        "range_compression_60_252": panels.range_compression_60_252,
        "ulcer_index_60d": panels.ulcer_index_60d,
        "momentum_quality_6m": panels.momentum_quality_6m,
        "trend_strength_60d": panels.trend_strength_60d,
        "new_high_streak_60d": panels.new_high_streak_60d,
        "close_over_252d_high": panels.close_over_252d_high,
        # Red-team quick wins.
        "amihud_illiq_21d": panels.amihud_illiq_21d,
        "obv_slope_60d": panels.obv_slope_60d,
        "mfi_14": panels.mfi_14,
        "bb_squeeze_20d": panels.bb_squeeze_20d,
        "rs_rank_within_tier_3m": panels.rs_rank_within_tier_3m,
        "rs_rank_within_tier_6m": panels.rs_rank_within_tier_6m,
        "rs_rank_within_tier_12m": panels.rs_rank_within_tier_12m,
        # Sector family.
        "sector_rs_6m": panels.sector_rs_6m,
        "sector_rs_12m": panels.sector_rs_12m,
        "sector_rs_rank_6m": panels.sector_rs_rank_6m,
        "sector_breadth_pos": panels.sector_breadth_pos,
        "sector_strength_rank": panels.sector_strength_rank,
        "sector_vol_regime": panels.sector_vol_regime,
        "cross_sector_breadth": panels.cross_sector_breadth,
    }
    if feature_name not in mapping:
        raise KeyError(f"feature {feature_name!r} not wired in deep-search panel map")
    return mapping[feature_name]
