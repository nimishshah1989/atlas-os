"""52WH proximity (George-Hwang 2004), FIP smoothness (Gray-Vogel 2014),
industry-decomposed RS (Moskowitz-Grinblatt 1999).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_52wh_proximity(close: np.ndarray, window: int = 252) -> np.ndarray:
    """proximity[i,t] = close[i,t] / max(close[i, t-window+1 : t+1]).

    Range: (0, 1]. 1.0 means at the high.
    """
    rolling_max = (
        (pd.DataFrame(close).T.rolling(window, min_periods=20).max().T)
        .to_numpy()
        .astype(np.float32)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(rolling_max > 0, close / rolling_max, 0.0).astype(np.float32)


def compute_fip_smoothness(close: np.ndarray, window: int = 252) -> np.ndarray:
    """fip[i,t] = (n_up_days - n_down_days) / window over trailing window.

    Range: [-1, 1]. +1 means all up days; -1 means all down; 0 means balanced.
    Combined with sign(ret_12m_1m) downstream to fade "smooth losers".
    """
    daily_ret = np.zeros_like(close)
    daily_ret[:, 1:] = close[:, 1:] / np.where(close[:, :-1] > 0, close[:, :-1], 1) - 1
    sign = np.sign(daily_ret)
    rolling_sum = (
        (pd.DataFrame(sign).T.rolling(window, min_periods=window // 2).sum().T)
        .to_numpy()
        .astype(np.float32)
    )
    return (rolling_sum / window).astype(np.float32)


def compute_industry_rs(stock_3m_ret: np.ndarray, sector_3m_ret: np.ndarray) -> np.ndarray:
    """industry_rs = stock 3m return - sector 3m return.

    Shapes must be broadcastable.
    """
    return (stock_3m_ret - sector_3m_ret).astype(np.float32)
