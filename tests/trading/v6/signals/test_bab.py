"""BAB — betting-against-beta inverse rank."""

from __future__ import annotations

import numpy as np

from atlas.trading.v6.signals.bab import compute_bab_rank


def test_bab_inverts_rank():
    """Lowest beta → highest BAB rank.

    Input: 3 stocks × 1 day.  axis=0 rank is cross-sectional (per day).
    """
    # Shape (3, 1): 3 stocks, 1 day.  Beta: 0.5, 1.0, 1.5
    beta = np.array([[0.5], [1.0], [1.5]])
    out = compute_bab_rank(beta)
    # Stock 0 (beta=0.5) should rank highest (≈1.0 - 0.33 = 0.67)
    # Stock 2 (beta=1.5) should rank lowest (≈1.0 - 1.00 = 0.00)
    assert out[0, 0] > out[1, 0] > out[2, 0]
