"""Price-based quality proxy (v0.1 placeholder).

Per spec §5.4:
    quality_proxy = -0.5 × rank(realized_vol_63)
                  - 0.3 × rank(max_drawdown_252d)
                  + 0.2 × rank(ret_consistency_252d)

where ret_consistency = ret_12m / |worst_quarter_return|.

All ranks are cross-sectional percentile ranks (0 to 1) per time period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_quality_proxy(
    realized_vol_63: np.ndarray,
    max_drawdown_252d: np.ndarray,
    ret_12m: np.ndarray,
    worst_quarter_ret: np.ndarray,
) -> np.ndarray:
    """Compute cross-sectional quality proxy score.

    All inputs shape: (n_stocks, n_days) or (n_stocks,) for single cross-section.

    Returns array of same shape as inputs. Higher = higher quality.

    NULLs in input propagate as NaN in output.
    """
    # Compute ret_consistency = ret_12m / |worst_quarter_ret|
    # Guard zero worst_quarter_ret to avoid inf
    abs_worst = np.abs(worst_quarter_ret)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret_consistency = np.where(abs_worst > 1e-8, ret_12m / abs_worst, 0.0)

    # Cross-sectional percentile ranks per day (axis=0)
    def _pct_rank(arr: np.ndarray) -> np.ndarray:
        return pd.DataFrame(arr).rank(axis=0, pct=True).fillna(0.5).to_numpy()

    rank_vol = _pct_rank(realized_vol_63)
    rank_dd = _pct_rank(max_drawdown_252d)
    rank_consistency = _pct_rank(ret_consistency)

    score = -0.5 * rank_vol - 0.3 * rank_dd + 0.2 * rank_consistency
    return score.astype(np.float32)
