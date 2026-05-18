"""Shared data-preparation primitives for the trading lab.

Two responsibilities:
  1. Sanitize close_adj corruption (drops stocks with non-corp-action jumps > 100%)
  2. Compute v5 monotonic signals (natr_14, beta_alpha_63d, mom_low_vol) on the
     full (n_stocks, n_days) grid so both genome-driven simulator and
     combinatorial lab can share the work.

Extracted from atlas/trading/simulator.py as part of Chunk 1 (eng-review
scope reduction). Pivot/extraction logic + signal computation now lives here;
window-level vectorbt loop lives in atlas/trading/period_engine.py.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()


def sanitize_close_adj(
    close: np.ndarray,
    instruments: list,
    dates: list,
    corp_actions: set[tuple[str, date]] | None = None,
    jump_threshold: float = 1.0,
) -> np.ndarray:
    """Drop stocks with close_adj corruption; preserve corp-action moves.

    Stocks with close_adj backfill bugs show scale-change discontinuities
    (one big jump UP that persists at the new scale). Forward-filling
    masked days creates a NEW discontinuity, so masking single days
    doesn't work. The clean approach: if a stock has ANY >100% one-day
    jump that isn't a recorded corp action, drop the whole stock from
    the universe (set its close row to NaN; vectorbt won't trade NaN).

    Threshold 1.0 = 100% one-day move. 50% catches too many legitimate
    small-cap moves; 100% is rare without corp action.
    """
    sanitized = close.copy().astype(np.float64)
    n_stocks, n_days = sanitized.shape
    corp_actions = corp_actions or set()

    prev = np.empty_like(sanitized)
    prev[:, 0] = sanitized[:, 0]
    prev[:, 1:] = sanitized[:, :-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = sanitized / prev
    big_jumps = np.isfinite(ratios) & (prev > 0) & (np.abs(ratios - 1.0) > jump_threshold)

    has_ca = np.zeros_like(big_jumps, dtype=bool)
    iid_to_idx = {str(instruments[s]): s for s in range(n_stocks)}
    date_to_idx = {dates[d]: d for d in range(n_days)}
    for iid, dt in corp_actions:
        s = iid_to_idx.get(iid)
        d = date_to_idx.get(dt)
        if s is not None and d is not None:
            has_ca[s, d] = True
            if d + 1 < n_days:
                has_ca[s, d + 1] = True

    suspect = big_jumps & ~has_ca
    bad_stock_mask = suspect.any(axis=1)
    bad_count = int(bad_stock_mask.sum())
    sanitized[bad_stock_mask, :] = np.nan

    if bad_count > 0:
        log.info(
            "close_adj_dropped_stocks",
            dropped=bad_count,
            of_total=n_stocks,
            drop_pct=round(100.0 * bad_count / max(1, n_stocks), 2),
            threshold=jump_threshold,
        )
    return sanitized.astype(np.float32)


def pivot_metrics(
    df: pd.DataFrame,
    instruments: list,
    dates: list,
) -> dict[str, np.ndarray]:
    """Pivot the long-format metrics DataFrame into a dict of (n_stocks, n_days) arrays.

    Returns a dict with keys: close, rs_pctile_1w, rs_pctile_1m, rs_pctile_3m,
    vol_ratio_63, ema_20_ratio, plus safe-pivoted optional columns (high, low,
    ret_12m, realized_vol_63, cts_stage, ppc, npc, contraction) when present.

    NOTE: RS percentiles are stored 0-1 in atlas_stock_metrics_daily but genome
    thresholds and the /100 normalization inside compute_conviction assume 0-100
    scale, so they're scaled here.
    """

    def _pivot(col: str) -> np.ndarray:
        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return pivoted.reindex(index=instruments, columns=dates).values.astype(np.float32)

    def _safe_pivot(col: str, default: float) -> np.ndarray:
        n_stocks_local = len(instruments)
        n_days_local = len(dates)
        if col not in df.columns:
            return np.full((n_stocks_local, n_days_local), default, dtype=np.float32)
        pivoted = df.pivot(index="instrument_id", columns="date", values=col)
        return (
            pivoted.reindex(index=instruments, columns=dates)
            .fillna(default)
            .values.astype(np.float32)
        )

    return {
        "close": _pivot("close"),
        "rs_1w": _pivot("rs_pctile_1w") * 100.0,
        "rs_1m": _pivot("rs_pctile_1m") * 100.0,
        "rs_3m": _pivot("rs_pctile_3m") * 100.0,
        "vol_ratio": _pivot("vol_ratio_63"),
        "ema_ratio": _pivot("ema_20_ratio"),
        "high": _safe_pivot("high", 0.0),
        "low": _safe_pivot("low", 0.0),
        "ret_12m": _safe_pivot("ret_12m", 0.0),
        "realized_vol_63": _safe_pivot("realized_vol_63", 0.0),
        "cts_stage": _safe_pivot("cts_stage", 2.0).astype(np.int8),
        "ppc": _safe_pivot("ppc", 0.0).astype(np.int8),
        "npc": _safe_pivot("npc", 0.0).astype(np.int8),
        "contraction": _safe_pivot("contraction", 0.0).astype(np.int8),
    }


def compute_natr_14(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """natr_14 = ATR(14) / close × 100 (vectorized).

    ATR = SMA(14) of TR; TR = max(H-L, |H-prev_close|, |L-prev_close|).
    Zero-division guarded: returns 0.0 when close <= 0.
    """
    prev_close = np.empty_like(close)
    prev_close[:, 0] = close[:, 0]
    prev_close[:, 1:] = close[:, :-1]
    tr = np.maximum.reduce(
        [
            high - low,
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ]
    )
    # .T.rolling(14).mean().T is equivalent to the deprecated rolling(axis=1).
    atr = pd.DataFrame(tr).T.rolling(14, min_periods=14).mean().T.to_numpy().astype(np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(close > 0, atr / close * 100, 0.0).astype(np.float32)


def compute_beta_alpha_63d(close: np.ndarray, nifty500_close: np.ndarray) -> np.ndarray:
    """beta_alpha_63d = stock 63d return − beta × benchmark 63d return.

    Beta = cov(stock_ret_1d, benchmark_ret_1d) / var(benchmark_ret_1d) over 63d.
    Guarded against zero benchmark variance.
    """
    stock_ret_1d = np.zeros_like(close)
    stock_ret_1d[:, 1:] = close[:, 1:] / np.where(close[:, :-1] > 0, close[:, :-1], 1) - 1
    n500_ret_1d = np.zeros_like(nifty500_close)
    n500_ret_1d[1:] = (
        nifty500_close[1:] / np.where(nifty500_close[:-1] > 0, nifty500_close[:-1], 1) - 1
    )
    bench_broadcast = np.broadcast_to(n500_ret_1d, stock_ret_1d.shape)
    # rolling(axis=1) is deprecated but the (n_stocks, n_days) → rolling-over-time
    # semantics with a paired benchmark DataFrame don't translate cleanly to
    # .T.rolling(...). Tracked for a focused refactor; FutureWarning is benign.
    sret_df = pd.DataFrame(stock_ret_1d)
    bret_df = pd.DataFrame(bench_broadcast)
    cov_63 = sret_df.rolling(63, axis=1, min_periods=63).cov(bret_df).to_numpy()
    var_63 = bret_df.rolling(63, axis=1, min_periods=63).var().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        beta_63 = np.where(np.abs(var_63) > 1e-12, cov_63 / var_63, 0.0)
    stock_63_ret = np.zeros_like(close)
    stock_63_ret[:, 63:] = close[:, 63:] / np.where(close[:, :-63] > 0, close[:, :-63], 1) - 1
    bench_63 = nifty500_close[63:] / np.where(nifty500_close[:-63] > 0, nifty500_close[:-63], 1) - 1
    bench_63_full = np.zeros_like(nifty500_close)
    bench_63_full[63:] = bench_63
    bench_63_bcast = np.broadcast_to(bench_63_full, close.shape)
    return (stock_63_ret - beta_63 * bench_63_bcast).astype(np.float32)


def compute_mom_low_vol(ret_12m: np.ndarray, realized_vol: np.ndarray) -> np.ndarray:
    """mom_low_vol = ret_12m × (1 − vol_rank). Cross-sectional vol rank per day."""
    vol_rank = pd.DataFrame(realized_vol).rank(axis=0, pct=True).fillna(0.5).to_numpy()
    return (ret_12m * (1.0 - vol_rank)).astype(np.float32)
