"""Breadth primitives shared by sector aggregation (M3 Phase B) and market
regime classification (M3 Phase C).

Per the lens methodology.1
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


def _pct_above(work: pd.DataFrame, close_col: str, ema_col: str, name: str) -> pd.Series:
    """Per-date fraction of stocks with ``close > ema``; NULL EMA rows excluded."""
    valid = work.dropna(subset=[close_col, ema_col])
    above = (valid[close_col] > valid[ema_col]).astype(int)
    counts = above.groupby(valid["date"]).agg(["sum", "count"])
    return (counts["sum"] / counts["count"].clip(lower=1)).rename(name)


def compute_ma_breadth(
    df_stocks: pd.DataFrame,
    *,
    close_col: str = "close_approx",
    ema_20_col: str = "ema_20_stock",
    ema_50_col: str = "ema_50_stock",
    ema_200_col: str = "ema_200_stock",
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Per-date fraction of stocks above their 20/50/100/200-EMA.

    Per methodology §11.1 (MA Breadth family). Stocks where the EMA is NULL
    (warm-up rows) are excluded from both numerator and denominator, so
    early-listing stocks don't bias the ratio.

    The 20/50/200-EMA breadth read the **stored** ``ema_20_stock`` /
    ``ema_50_stock`` / ``ema_200_stock`` columns. The 100-EMA is **not stored**,
    so it is computed fresh, vectorised, from ``close_col`` via a per-stock
    ``ewm`` (no Python loop).

    Returns:
        Date-indexed frame with ``pct_above_ema_20/50/100/200`` (each in [0, 1]).
    """
    cols = ["pct_above_ema_20", "pct_above_ema_50", "pct_above_ema_100", "pct_above_ema_200"]
    if df_stocks.empty:
        return pd.DataFrame(columns=["date", *cols])

    want = [group_col, "date", close_col, ema_20_col, ema_50_col, ema_200_col]
    work = df_stocks[[c for c in want if c in df_stocks.columns]].copy()
    if ema_20_col not in work.columns:
        work[ema_20_col] = pd.NA

    # 100-EMA computed fresh from close (not stored at stock grain). ewm runs
    # in C per group — no iterrows. min_periods=100 so warm-up rows stay NaN
    # and drop out of the ratio (consistent with the stored-EMA cohorts).
    work = work.sort_values([group_col, "date"])
    work["ema_100_stock"] = (
        work.groupby(group_col, group_keys=False, observed=True)[close_col]
        .transform(lambda s: s.ewm(span=100, adjust=False, min_periods=100).mean())
        .astype("float64")
    )

    pct_20 = _pct_above(work, close_col, ema_20_col, "pct_above_ema_20")
    pct_50 = _pct_above(work, close_col, ema_50_col, "pct_above_ema_50")
    pct_100 = _pct_above(work, close_col, "ema_100_stock", "pct_above_ema_100")
    pct_200 = _pct_above(work, close_col, ema_200_col, "pct_above_ema_200")

    out = pd.concat([pct_20, pct_50, pct_100, pct_200], axis=1).reset_index()
    out = out.sort_values("date").reset_index(drop=True)
    # A date present in only some cohorts keeps NaN for the others — real signal,
    # not imputed 0.
    return out


def compute_pct_4w_high(
    df_stocks: pd.DataFrame,
    *,
    close_col: str = "close_approx",
    group_col: str = "instrument_id",
    window: int = 20,
    tol: float = 0.001,
) -> pd.DataFrame:
    """Per-date fraction of stocks at (within ``tol`` of) their 4-week high.

    A stock is "at a 4-week high" on date ``t`` iff ``close_t`` is within
    ``tol`` (default 0.1%) of its trailing ``window``-day (≈4 weeks) rolling
    max. Vectorised rolling max per stock — no Python loop.

    Returns:
        Date frame with ``pct_4w_high`` in [0, 1].
    """
    if df_stocks.empty:
        return pd.DataFrame(columns=["date", "pct_4w_high"])

    work = df_stocks[[group_col, "date", close_col]].copy()
    work = work.sort_values([group_col, "date"]).reset_index(drop=True)
    grp = work.groupby(group_col, group_keys=False, observed=True)[close_col]
    # min_periods = window*3//4 so a stock needs ~3 weeks of history to qualify.
    roll_max = grp.transform(lambda s: s.rolling(window, min_periods=window * 3 // 4).max())

    at_high = (work[close_col] >= roll_max * (1.0 - tol)) & roll_max.notna()
    valid = work.assign(_at=at_high).loc[roll_max.notna()]
    counts = valid["_at"].astype(int).groupby(valid["date"]).agg(["sum", "count"])
    pct = (counts["sum"] / counts["count"].clip(lower=1)).rename("pct_4w_high")

    out = pct.reset_index().sort_values("date").reset_index(drop=True)
    return out


__all__ = [
    "compute_ad_line",
    "compute_advances_declines",
    "compute_ma_breadth",
    "compute_mcclellan",
    "compute_new_highs_lows",
    "compute_pct_4w_high",
]
