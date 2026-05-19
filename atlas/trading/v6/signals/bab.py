"""BAB — betting-against-beta tilt (Frazzini-Pedersen 2014)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_bab_rank(beta: np.ndarray) -> np.ndarray:
    """Cross-sectional inverse rank of beta. Low-beta names → high rank.

    Input shape: (n_stocks, n_days) or (n_stocks,) for a single cross-section.
    Returns same shape as input.
    """
    rank = pd.DataFrame(beta).rank(axis=0, pct=True).fillna(0.5).to_numpy()
    return (1.0 - rank).astype(np.float32)
