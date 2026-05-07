"""Breadth primitives shared by sector aggregation (M3 Phase B) and market
regime classification (M3 Phase C).

Per ``docs/00_METHODOLOGY_LOCK.md`` §10.4 (sector breadth) and §11.1
(market regime A/D, MA, new highs/lows, strength breadth families).

Vectorisation discipline:
    Every function takes a single DataFrame containing the *whole universe*
    (all stocks, all dates) and uses pandas groupby / pivot operations so the
    per-stock loop runs in C, not Python. ``df.iterrows()`` is banned (per
    ``~/.claude/rules/data-engineering.md``).

All inputs assume ``close_approx`` reconstructed from
``ema_200_stock * (1 + extension_pct)`` because ``atlas_stock_metrics_daily``
does not store raw close — see M3 build plan locked decision #2.
"""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta
import structlog

log = structlog.get_logger()


# --------------------------------------------------------------------------- #
# Advances / declines                                                         #
# --------------------------------------------------------------------------- #


def compute_advances_declines(
    df: pd.DataFrame,
    *,
    close_col: str = "close_approx",
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Per-date advance/decline counts.

    Args:
        df: long-form stock-day frame with columns
            ``[group_col, "date", close_col]`` (or ``"ret_1d"`` if already
            computed; we recompute for safety to avoid relying on caller pre-state).
        close_col: column holding daily close (or close_approx).
        group_col: per-stock identifier column.

    Returns:
        Date-indexed DataFrame with one row per date and columns:

        ``advances`` (count of stocks with ret_1d > 0),
        ``declines`` (count with ret_1d < 0),
        ``unchanged`` (count with ret_1d == 0),
        ``net_advances`` (advances - declines),
        ``advance_decline_ratio`` (advances / max(declines, 1)).

    The returned frame is sorted by date with ``date`` as a regular column
    (not the index) so callers can chain ``.merge`` / ``.assign`` cleanly.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "advances",
                "declines",
                "unchanged",
                "net_advances",
                "advance_decline_ratio",
            ]
        )

    work = df[[group_col, "date", close_col]].copy()
    work = work.sort_values([group_col, "date"])
    work["ret_1d"] = (
        work.groupby(group_col, group_keys=False, observed=True)[close_col]
        .pct_change(periods=1)
        .astype("float64")
    )

    # Only count stocks where ret_1d is finite (drops the first row per stock).
    valid = work.loc[work["ret_1d"].notna()].copy()

    advances = (valid["ret_1d"] > 0).groupby(valid["date"]).sum().rename("advances")
    declines = (valid["ret_1d"] < 0).groupby(valid["date"]).sum().rename("declines")
    unchanged = (valid["ret_1d"] == 0).groupby(valid["date"]).sum().rename("unchanged")

    out = pd.concat([advances, declines, unchanged], axis=1).fillna(0).astype(int)
    out["net_advances"] = out["advances"] - out["declines"]
    out["advance_decline_ratio"] = out["advances"] / out["declines"].clip(lower=1).astype("float64")
    out = out.reset_index().sort_values("date").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- #
# Cumulative A/D line                                                         #
# --------------------------------------------------------------------------- #


def compute_ad_line(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Vectorised cumsum of net_advances over the full date range.

    Recomputes from scratch on every call (no incremental updates) — locked
    decision #3 in the M3 build plan. Idempotent: rerunning on the same
    history produces identical values.

    Args:
        df_daily: output of :func:`compute_advances_declines` (or any frame
            with ``date`` and ``net_advances`` columns).

    Returns:
        Same frame with an additional ``ad_line`` column.
    """
    if df_daily.empty:
        out = df_daily.copy()
        out["ad_line"] = pd.Series(dtype="float64")
        return out

    out = df_daily.sort_values("date").reset_index(drop=True).copy()
    out["ad_line"] = out["net_advances"].cumsum().astype("float64")
    return out


# --------------------------------------------------------------------------- #
# McClellan Oscillator                                                        #
# --------------------------------------------------------------------------- #


def compute_mcclellan(df_daily: pd.DataFrame) -> pd.DataFrame:
    """McClellan Oscillator = EMA(19, net_advances) − EMA(39, net_advances).

    Per methodology §11.1 (A/D Breadth family). Uses ``pandas_ta.ema`` to
    match the same EMA seed convention (first-N SMA) as
    :mod:`atlas.compute.primitives` so library drift fails fast under Tier 2
    validation.

    Args:
        df_daily: output of :func:`compute_advances_declines`.

    Returns:
        Same frame with ``mcclellan_oscillator`` and ``mcclellan_summation``
        (cumulative oscillator) columns appended.
    """
    if df_daily.empty:
        out = df_daily.copy()
        out["mcclellan_oscillator"] = pd.Series(dtype="float64")
        out["mcclellan_summation"] = pd.Series(dtype="float64")
        return out

    out = df_daily.sort_values("date").reset_index(drop=True).copy()
    net = out["net_advances"].astype("float64")
    ema_19 = ta.ema(net, length=19)
    ema_39 = ta.ema(net, length=39)
    out["mcclellan_oscillator"] = (ema_19 - ema_39).astype("float64")
    out["mcclellan_summation"] = out["mcclellan_oscillator"].fillna(0).cumsum().astype("float64")
    return out


# --------------------------------------------------------------------------- #
# New 52-week highs / lows                                                    #
# --------------------------------------------------------------------------- #


def compute_new_highs_lows(
    df_stocks: pd.DataFrame,
    *,
    close_col: str = "close_approx",
    group_col: str = "instrument_id",
    window: int = 252,
) -> pd.DataFrame:
    """Per-date new 52-week highs and lows.

    A stock is at a new 52-week high on date ``t`` iff ``close_t`` equals the
    rolling-252d max of its close series (inclusive of t). Symmetrically for
    lows.

    Args:
        df_stocks: long stock-day frame with ``[group_col, "date", close_col]``.
        close_col: column holding daily close (or close_approx).
        group_col: per-stock identifier column.
        window: rolling window in trading days; 252 ≈ 1 year.

    Returns:
        Date-indexed frame with ``new_52w_highs``, ``new_52w_lows``,
        ``net_new_highs``, ``new_high_low_ratio`` columns.
    """
    if df_stocks.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "new_52w_highs",
                "new_52w_lows",
                "net_new_highs",
                "new_high_low_ratio",
            ]
        )

    work = df_stocks[[group_col, "date", close_col]].copy()
    work = work.sort_values([group_col, "date"]).reset_index(drop=True)

    grp = work.groupby(group_col, group_keys=False, observed=True)[close_col]
    rolling_max = grp.transform(lambda s: s.rolling(window, min_periods=window // 2).max())
    rolling_min = grp.transform(lambda s: s.rolling(window, min_periods=window // 2).min())

    is_new_high = (work[close_col] - rolling_max).abs() < 1e-9
    is_new_low = (work[close_col] - rolling_min).abs() < 1e-9
    # Only count where the rolling window is warm (rolling_max is finite).
    is_new_high = is_new_high & rolling_max.notna()
    is_new_low = is_new_low & rolling_min.notna()

    highs = is_new_high.groupby(work["date"]).sum().astype(int).rename("new_52w_highs")
    lows = is_new_low.groupby(work["date"]).sum().astype(int).rename("new_52w_lows")

    out = pd.concat([highs, lows], axis=1).fillna(0).astype(int)
    out["net_new_highs"] = out["new_52w_highs"] - out["new_52w_lows"]
    out["new_high_low_ratio"] = out["new_52w_highs"] / out["new_52w_lows"].clip(lower=1).astype(
        "float64"
    )
    out = out.reset_index().sort_values("date").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- #
# MA breadth                                                                  #
# --------------------------------------------------------------------------- #


def compute_ma_breadth(
    df_stocks: pd.DataFrame,
    *,
    close_col: str = "close_approx",
    ema_50_col: str = "ema_50_stock",
    ema_200_col: str = "ema_200_stock",
) -> pd.DataFrame:
    """Per-date fraction of stocks above their 50-/200-EMA.

    Per methodology §11.1 (MA Breadth family) — Bhaven's anchor. Stocks where
    the EMA is NULL (warm-up rows) are excluded from both numerator and
    denominator, so early-listing stocks don't bias the ratio.

    Args:
        df_stocks: long stock-day frame containing the close and EMA columns.
        close_col: column holding daily close (or close_approx).
        ema_50_col / ema_200_col: stock-level EMA columns from
            ``atlas_stock_metrics_daily``.

    Returns:
        Date-indexed frame with ``pct_above_ema_50`` and ``pct_above_ema_200``
        columns (each in [0, 1]).
    """
    if df_stocks.empty:
        return pd.DataFrame(columns=["date", "pct_above_ema_50", "pct_above_ema_200"])

    work = df_stocks[["date", close_col, ema_50_col, ema_200_col]].copy()

    # ---- 50-day EMA breadth -------------------------------------------------
    valid_50 = work.dropna(subset=[close_col, ema_50_col])
    above_50 = (valid_50[close_col] > valid_50[ema_50_col]).astype(int)
    counts_50 = above_50.groupby(valid_50["date"]).agg(["sum", "count"])
    pct_50 = (counts_50["sum"] / counts_50["count"].clip(lower=1)).rename("pct_above_ema_50")

    # ---- 200-day EMA breadth ------------------------------------------------
    valid_200 = work.dropna(subset=[close_col, ema_200_col])
    above_200 = (valid_200[close_col] > valid_200[ema_200_col]).astype(int)
    counts_200 = above_200.groupby(valid_200["date"]).agg(["sum", "count"])
    pct_200 = (counts_200["sum"] / counts_200["count"].clip(lower=1)).rename("pct_above_ema_200")

    out = pd.concat([pct_50, pct_200], axis=1).reset_index()
    out = out.sort_values("date").reset_index(drop=True)
    # If a date is present in only one of the two cohorts, the missing column
    # comes through as NaN — keep that signal rather than imputing 0.
    return out


__all__ = [
    "compute_ad_line",
    "compute_advances_declines",
    "compute_ma_breadth",
    "compute_mcclellan",
    "compute_new_highs_lows",
]
