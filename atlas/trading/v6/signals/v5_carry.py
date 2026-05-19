"""v5 signal carry — natr_14, beta_alpha_63d, mom_low_vol.

Functions copied verbatim from atlas/trading/data_loader.py (commit 5e1bd87).
Do NOT import from atlas.trading.data_loader — modulith isolation requires
bounded-context copy for v6.

Math is unchanged from v5. See atlas/trading/data_loader.py for original comments.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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
