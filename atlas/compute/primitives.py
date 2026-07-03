"""Atlas-M2 primitive computations.

Per the lens methodology.

The four primitives — Relative Strength, RS Momentum, Relative Risk, Volume —
plus EMAs and ATR are computed here. Every formula maps to a vetted library
call (``pandas-ta``, ``empyrical``, ``numpy``); no hand-rolled rolling-window
math except where the methodology explicitly specifies the formula (returns,
ratios).

Vectorisation pattern: every function takes a DataFrame containing the *whole
universe* (all instruments, all dates) and uses ``groupby(instrument_id)`` so
the per-instrument loop runs in C, not Python.
§3 for the time budget this pattern hits.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta

WINDOWS: dict[str, int] = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
    "12m_1m": 231,
    "24m": 504,
}
"""Trading-day window lengths per methodology §4.1. ``12m_1m`` skips the most
recent month (252 - 21 = 231) — the academic 12m-1m momentum convention.

RS windows expanded 5 → 7 (2026-05-30 CONTEXT.md lock): ``1d`` (1 trading day,
informational/never load-bearing) and ``24m`` (504 trading days, ~2yr) added so
every RS surface covers 1d/1w/1m/3m/6m/12m/24m. ``1d``/``24m`` feed RS only —
no scoring/feature code iterates WINDOWS (verified), and vol/drawdown take their
own window args."""


RS_WINDOWS: tuple[str, ...] = ("1d", "1w", "1m", "3m", "6m", "12m", "24m")
"""The 7 canonical relative-strength windows (CONTEXT.md lock). This is
``WINDOWS`` minus ``12m_1m`` — the skip-most-recent variant feeds momentum
scoring, not RS display surfaces. Every RS metric (tier, gold, market-vs-Nifty500)
iterates exactly these 7 windows."""


# --------------------------------------------------------------------------- #
# Returns                                                                     #
# --------------------------------------------------------------------------- #


def add_returns(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    price_col: str = "close",
    windows: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Append ``ret_<window>`` columns vectorised across all groups.

    Returns are decimal (0.05 = 5%), computed via ``pct_change(periods=N)`` on
    each group's price series. ``ret_12m_1m`` is computed as
    ``(price_t / price_{t-21}) / (price_{t-252} / price_{t-273}) - 1`` only
    when explicitly requested via the ``12m_1m`` window key — otherwise it's
    just ``pct_change(231)`` (skip-most-recent variant), per methodology §4.1.

    Mutates a copy; original ``df`` is unchanged.
    """
    out = df.copy()
    out = out.sort_values([group_col, "date"])

    win = windows or WINDOWS
    grouped = out.groupby(group_col, group_keys=False, observed=True)[price_col]

    for name, n in win.items():
        out[f"ret_{name}"] = grouped.pct_change(periods=n).astype("float64")

    out["ret_1d"] = grouped.pct_change(periods=1).astype("float64")
    return out


# --------------------------------------------------------------------------- #
# EMAs + ATR — pandas-ta primitives                                           #
# --------------------------------------------------------------------------- #


def add_emas(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    price_col: str = "close",
    lengths: tuple[int, ...] = (10, 20, 50, 200),
    suffix: str = "stock",
) -> pd.DataFrame:
    """Append ``ema_{N}_{suffix}`` columns via ``pandas_ta.ema``, group-vectorised.

    pandas-ta seeds EMA with a first-N-period SMA, returning NaN for the first
    ``N-1`` rows. This matches methodology §4.2 expectations and is verified
    by Tier 2 hand-validation (see ``atlas/validation/tier2_metrics.py``).
    """
    out = df.copy().sort_values([group_col, "date"])
    grouped = out.groupby(group_col, group_keys=False, observed=True)

    for n in lengths:
        out[f"ema_{n}_{suffix}"] = grouped[price_col].transform(
            lambda s, length=n: ta.ema(s, length=length)
        )
    return out


def add_atr(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    length: int = 21,
) -> pd.DataFrame:
    """Append ``atr_{length}`` via ``pandas_ta.atr`` (Wilder smoothing).

    Required by methodology §13.4 trigger 6 (M5 ATR-stop exit) — included in
    M2 to avoid a re-run when M5 lands.
    """
    out = df.copy().sort_values([group_col, "date"])
    col = f"atr_{length}"

    def _atr(g: pd.DataFrame) -> pd.Series:
        return ta.atr(g["high"], g["low"], g["close"], length=length)

    out[col] = (
        out.groupby(group_col, group_keys=False, observed=True)
        .apply(_atr)
        .reset_index(level=0, drop=True)
    )
    return out


# --------------------------------------------------------------------------- #
# Relative Risk components                                                    #
# --------------------------------------------------------------------------- #


def add_realized_vol(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    return_col: str = "ret_1d",
    window: int = 63,
    annualization_factor: int = 252,
    out_col: str | None = None,
) -> pd.DataFrame:
    """Annualised realised vol over a rolling window. Pure NumPy/pandas.

    ``vol_t = std(daily_returns[t-window+1 .. t]) * sqrt(252)``.
    Methodology §7.3.
    """
    out = df.copy().sort_values([group_col, "date"])
    col = out_col or f"realized_vol_{window}"

    out[col] = (
        out.groupby(group_col, group_keys=False, observed=True)[return_col].transform(
            lambda s: s.rolling(window, min_periods=window // 2).std()
        )
        * np.sqrt(annualization_factor)
    ).astype("float64")
    return out


def add_max_drawdown(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    return_col: str = "ret_1d",
    window: int = 252,
    out_col: str | None = None,
) -> pd.DataFrame:
    """Vectorised rolling max drawdown over ``window`` days.

    Empyrical's ``max_drawdown`` is a single-pass scan; running it inside a
    per-row loop is O(n × window) and untenable at 2.3 M rows. This is the
    architecturally-mandated vectorised equivalent (per M2 spec §4.4 note):

        cumulative   = cumprod(1 + returns)
        rolling_peak = cumulative.rolling(window).max()
        drawdown_t   = cumulative_t / rolling_peak_t - 1
        max_dd_t     = drawdown.rolling(window).min().abs()

    Result matches ``empyrical.max_drawdown`` to within float32 precision
    (verified by Tier 2 hand-validation).
    """
    out = df.copy().sort_values([group_col, "date"])
    col = out_col or f"max_drawdown_{window}"

    def _per_group(returns: pd.Series) -> pd.Series:
        cumulative = (1 + returns.fillna(0)).cumprod()
        rolling_peak = cumulative.rolling(window, min_periods=window // 2).max()
        drawdown = cumulative.div(rolling_peak).sub(1)
        return drawdown.rolling(window, min_periods=window // 2).min().abs()

    out[col] = (
        out.groupby(group_col, group_keys=False, observed=True)[return_col]
        .transform(_per_group)
        .astype("float64")
    )
    return out


def add_extension_pct(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    ema_col: str = "ema_200_stock",
    out_col: str = "extension_pct",
) -> pd.DataFrame:
    """``(close - ema_200) / ema_200``. Methodology §7.3."""
    out = df.copy()
    out[out_col] = (out[price_col] - out[ema_col]) / out[ema_col]
    return out


# --------------------------------------------------------------------------- #
# Volume primitives                                                           #
# --------------------------------------------------------------------------- #


def add_volume_primitives(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
    event_dates: set[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    """Append ``volume_expansion`` and ``effort_ratio_63`` per methodology §7.4.

    Event-day exclusion: half-sessions / Budget days have anomalous volume.
    The caller supplies the set of event dates; rows on those dates contribute
    NaN to rolling windows (preserving everything else).
    """
    out = df.copy().sort_values([group_col, "date"])

    event_dates = event_dates or set()
    is_event = out["date"].isin(event_dates)
    volume_clean = out["volume"].where(~is_event, np.nan)

    is_up = out["close"] >= out["open"]
    is_down = out["close"] < out["open"]

    grouped = out.groupby(group_col, group_keys=False, observed=True)

    out["avg_volume_20"] = grouped["volume"].transform(
        lambda s, vc=volume_clean: vc.loc[s.index].rolling(20, min_periods=14).mean()
    )
    out["avg_volume_252"] = grouped["volume"].transform(
        lambda s, vc=volume_clean: vc.loc[s.index].rolling(252, min_periods=180).mean()
    )
    out["volume_expansion"] = out["avg_volume_20"] / out["avg_volume_252"]

    up_vol = volume_clean.where(is_up, 0.0)
    down_vol = volume_clean.where(is_down, 0.0)

    out["up_volume_sum_63"] = grouped["volume"].transform(
        lambda s, uv=up_vol: uv.loc[s.index].rolling(63, min_periods=42).sum()
    )
    out["down_volume_sum_63"] = grouped["volume"].transform(
        lambda s, dv=down_vol: dv.loc[s.index].rolling(63, min_periods=42).sum()
    )

    # Avoid divide-by-zero: clip to 1 (methodology §7.4 implicit floor)
    out["effort_ratio_63"] = out["up_volume_sum_63"] / out["down_volume_sum_63"].clip(lower=1.0)
    return out


# --------------------------------------------------------------------------- #
# RS Momentum (EMA-ratio approach, methodology §7.2)                          #
# --------------------------------------------------------------------------- #


def add_rs_momentum(
    df: pd.DataFrame,
    *,
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Compute ``ema_*_ratio`` and 20-day high/low flags.

    Requires ``ema_10_stock``, ``ema_20_stock`` from ``add_emas`` AND
    ``ema_10_benchmark``, ``ema_20_benchmark`` already merged onto each row
    (typically via :func:`atlas.compute.benchmarks.merge_benchmark_emas`).

    Methodology §7.2:

    * ``ema_10_ratio = ema_10_stock / ema_20_stock``   — stock trending up short-term (> 1)
    * ``ema_20_ratio = ema_10_benchmark / ema_20_benchmark`` — benchmark trending up (> 1)
    * ``ema_10_at_20d_high`` = today's ``ema_10_ratio`` ties the 20-day max
    * ``ema_10_at_20d_low``  = today's ``ema_10_ratio`` ties the 20-day min

    Note: ratios compare EMA10 vs EMA20 *within* the same entity, not across
    entities.  Dividing stock EMA by benchmark EMA (a price-level ratio) broke
    ETFs because their price (~₹200) was always far below Nifty (~22,000).
    """
    out = df.copy().sort_values([group_col, "date"])

    out["ema_10_ratio"] = out["ema_10_stock"] / out["ema_20_stock"]
    out["ema_20_ratio"] = out["ema_10_benchmark"] / out["ema_20_benchmark"]

    grouped = out.groupby(group_col, group_keys=False, observed=True)["ema_10_ratio"]
    rolling_max = grouped.transform(lambda s: s.rolling(20, min_periods=1).max())
    rolling_min = grouped.transform(lambda s: s.rolling(20, min_periods=1).min())

    out["ema_10_at_20d_high"] = (out["ema_10_ratio"] - rolling_max).abs() < 1e-12
    out["ema_10_at_20d_low"] = (out["ema_10_ratio"] - rolling_min).abs() < 1e-12
    return out


# --------------------------------------------------------------------------- #
# Within-tier percentile rank                                                 #
# --------------------------------------------------------------------------- #


def add_within_tier_percentiles(
    df: pd.DataFrame,
    *,
    rs_cols: tuple[str, ...] = ("rs_1w_tier", "rs_1m_tier", "rs_3m_tier"),
    tier_col: str = "tier",
    date_col: str = "date",
) -> pd.DataFrame:
    """Percentile-rank each stock's RS within (date, tier) cohort.

    Result is dense rank scaled to [0, 1]. Cohorts with fewer than 5 ranked
    observations on a date emit NaN — methodology §6.4 minimum-cohort rule.
    """
    out = df.copy()

    for col in rs_cols:
        suffix = col.replace("rs_", "rs_pctile_").replace("_tier", "")
        ranks = out.groupby([date_col, tier_col], observed=True)[col].rank(method="dense")
        counts = out.groupby([date_col, tier_col], observed=True)[col].transform("count")
        out[suffix] = (ranks / counts).where(counts >= 5)

    return out
