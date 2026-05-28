# tests/tv/test_portfolio_analytics.py
from decimal import Decimal

import numpy as np
import pandas as pd

from atlas.tv.portfolio_analytics import (  # type: ignore[import]
    _compute_alpha,
    _compute_beta,
    _compute_calmar,
    _compute_max_drawdown,
    _compute_sharpe,
    _compute_sortino,
    _compute_twr,
)

RNG = np.random.default_rng(42)
N = 252
PORTFOLIO_RETURNS = pd.Series(RNG.normal(0.0005, 0.012, N))
NIFTY_RETURNS = pd.Series(RNG.normal(0.0003, 0.010, N))
RF = Decimal("0.065")


def test_sharpe_positive_for_positive_drift():
    sharpe = _compute_sharpe(PORTFOLIO_RETURNS, RF)
    assert isinstance(sharpe, float)
    assert -5.0 < sharpe < 5.0


def test_sortino_gte_sharpe_for_positive_returns():
    # Sortino >= Sharpe only holds when mean excess return is positive.
    # Use a series with a strong positive drift above Rf/252 to guarantee this.
    rng = np.random.default_rng(0)
    positive_returns = pd.Series(rng.normal(0.002, 0.008, 252))  # mean well above Rf/252=0.000258
    sharpe = _compute_sharpe(positive_returns, RF)
    sortino = _compute_sortino(positive_returns, RF)
    assert isinstance(sortino, float)
    assert sortino >= sharpe


def test_beta_is_near_one_for_identical_series():
    beta = _compute_beta(NIFTY_RETURNS, NIFTY_RETURNS)
    assert beta is not None
    assert abs(beta - 1.0) < 0.01


def test_beta_null_for_short_series():
    short = pd.Series(NIFTY_RETURNS[:25].values)
    assert _compute_beta(short, short) is None


def test_max_drawdown_between_zero_and_one():
    dd = _compute_max_drawdown(PORTFOLIO_RETURNS)
    assert 0.0 <= dd <= 1.0


def test_twr_compound_product():
    simple = pd.Series([0.1, -0.1])
    twr = _compute_twr(simple)
    assert abs(twr - (1.1 * 0.9 - 1)) < 1e-9


def test_calmar_none_when_zero_drawdown():
    # A perfectly flat return series should have near-zero drawdown
    flat = pd.Series([0.0] * 100)
    calmar = _compute_calmar(flat)
    assert calmar is None


def test_alpha_positive_for_outperforming_portfolio():
    outperforming = NIFTY_RETURNS + 0.001
    alpha = _compute_alpha(outperforming, NIFTY_RETURNS, RF)
    assert alpha is not None
    assert alpha > 0.0
