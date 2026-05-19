"""Tests for atlas/trading/v6/signals/factor_returns.py

TDD: tests written first. Run these with ATLAS_TEST_DB_URL unset → skip DB tests.
Pure-logic tests run in all environments.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from atlas.trading.v6.signals.factor_returns import (
    _daily_tbill_rate,
    _mkt_excess_from_values,
    _smb_from_tiers,
    _wml_from_mom_series,
    compute_mkt_excess,
    compute_smb,
    compute_wml,
)

# ---------------------------------------------------------------------------
# Pure-logic helpers (no DB required)
# ---------------------------------------------------------------------------


class TestDailyTbillRate:
    def test_valid_decimal_annualized(self):
        """6% annual → 0.06/252 ≈ 0.000238095."""
        rate = _daily_tbill_rate(Decimal("0.06"))
        assert abs(rate - 0.06 / 252) < 1e-9

    def test_none_falls_back_to_zero_annualized(self):
        """NULL T-bill → 0.0 (spec says use 0 in practice)."""
        rate = _daily_tbill_rate(None)
        assert rate == 0.0

    def test_zero_decimal_returns_zero(self):
        rate = _daily_tbill_rate(Decimal("0"))
        assert rate == 0.0


class TestMktExcessFromValues:
    def test_positive_excess(self):
        """Nifty up 0.5%, T-bill 0.02%/day → excess ≈ 0.0048."""
        excess = _mkt_excess_from_values(nifty_ret=0.005, daily_tbill=0.0002)
        assert abs(excess - 0.0048) < 1e-8

    def test_negative_excess(self):
        """Nifty flat (0%), T-bill 0.02% → excess = -0.0002."""
        excess = _mkt_excess_from_values(nifty_ret=0.0, daily_tbill=0.0002)
        assert abs(excess - (-0.0002)) < 1e-8

    def test_null_nifty_returns_none(self):
        """Missing Nifty price → None (not zero)."""
        result = _mkt_excess_from_values(nifty_ret=None, daily_tbill=0.0002)
        assert result is None


class TestSmbFromTiers:
    def test_small_beats_large(self):
        """Small-tier avg return > Large-tier → positive SMB."""
        smb = _smb_from_tiers(
            small_returns=[0.02, 0.03, 0.01],
            large_returns=[0.005, 0.004],
        )
        assert smb > 0

    def test_large_beats_small(self):
        """Large-tier avg > small-tier → negative SMB."""
        smb = _smb_from_tiers(
            small_returns=[0.001, 0.002],
            large_returns=[0.03, 0.04, 0.05],
        )
        assert smb < 0

    def test_empty_small_returns_none(self):
        """Zero small-tier stocks on a date → None."""
        result = _smb_from_tiers(small_returns=[], large_returns=[0.01, 0.02])
        assert result is None

    def test_empty_large_returns_none(self):
        """Zero large-tier stocks on a date → None."""
        result = _smb_from_tiers(small_returns=[0.01, 0.02], large_returns=[])
        assert result is None

    def test_exact_arithmetic(self):
        """SMB = mean(small) - mean(large); verify exact value."""
        smb = _smb_from_tiers(
            small_returns=[0.0, 0.04],  # mean = 0.02
            large_returns=[0.01, 0.01],  # mean = 0.01
        )
        assert smb is not None
        assert abs(smb - 0.01) < 1e-10


class TestWmlFromMomSeries:
    def test_top_beats_bottom(self):
        """Winners > losers → positive WML."""
        # 20 stocks: 10 with high momentum, 10 with low
        mom = list(range(1, 21))  # 1..20, unit doesn't matter for test
        rets = [0.05 if m > 10 else -0.01 for m in mom]  # high mom = high ret
        wml = _wml_from_mom_series(mom_series=mom, ret_series=rets, decile_n=2)
        assert wml > 0

    def test_too_few_stocks_returns_none(self):
        """Fewer than 10 stocks (2× decile_n minimum) → None."""
        result = _wml_from_mom_series(
            mom_series=[0.1, 0.2, 0.3],
            ret_series=[0.01, 0.02, 0.03],
            decile_n=2,
        )
        assert result is None

    def test_exact_wml_value(self):
        """With 10 stocks and decile_n=1 (top-1 vs bottom-1), verify arithmetic."""
        mom_series = list(range(10))  # 0..9; 9 is winner, 0 is loser
        ret_series = [float(i) * 0.01 for i in range(10)]  # 0.00, 0.01, ..., 0.09
        wml = _wml_from_mom_series(mom_series, ret_series, decile_n=1)
        # top-1 momentum = index 9, ret = 0.09; bottom-1 = index 0, ret = 0.00
        assert wml is not None
        assert abs(wml - 0.09) < 1e-9

    def test_nan_mom_excluded(self):
        """Stocks with NaN momentum are excluded from WML computation."""
        mom_series = [float("nan"), 0.5, 0.4, 0.3, 0.2, 0.1, -0.1, -0.2, -0.3, -0.4, -0.5]
        ret_series = [0.99, 0.05, 0.04, 0.03, 0.02, 0.01, -0.01, -0.02, -0.03, -0.04, -0.05]
        # After dropping NaN: 10 stocks → valid
        wml = _wml_from_mom_series(mom_series, ret_series, decile_n=1)
        assert wml is not None


# ---------------------------------------------------------------------------
# DB integration tests (skipped when ATLAS_TEST_DB_URL is not set)
# ---------------------------------------------------------------------------


class TestComputeMktExcessDB:
    def test_returns_float_or_none(self, tmp_db_session):
        """compute_mkt_excess on any recent date returns float or None."""
        result = compute_mkt_excess(tmp_db_session, date(2024, 1, 15))
        assert result is None or isinstance(result, float)

    def test_non_extreme_value(self, tmp_db_session):
        """Market excess return on a trading day is within ±20%."""
        result = compute_mkt_excess(tmp_db_session, date(2024, 1, 15))
        if result is not None:
            assert -0.20 <= result <= 0.20


class TestComputeSmbDB:
    def test_returns_float_or_none(self, tmp_db_session):
        """compute_smb on any date returns float or None."""
        result = compute_smb(tmp_db_session, date(2024, 1, 15))
        assert result is None or isinstance(result, float)


class TestComputeWmlDB:
    def test_returns_float_or_none(self, tmp_db_session):
        """compute_wml on any date returns float or None."""
        result = compute_wml(tmp_db_session, date(2024, 1, 15))
        assert result is None or isinstance(result, float)
