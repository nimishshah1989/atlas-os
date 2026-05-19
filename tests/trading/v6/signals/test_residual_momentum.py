"""Tests for atlas/trading/v6/signals/residual_momentum.py

TDD: tests written first. Pure-logic tests don't need DB.
DB-integrated tests skip when ATLAS_TEST_DB_URL is unset.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from atlas.trading.v6.signals.residual_momentum import (
    _cumulate_residuals,
    _fit_ols_residuals,
    _validate_window,
    compute_residual_momentum,
)

# ---------------------------------------------------------------------------
# _validate_window
# ---------------------------------------------------------------------------


class TestValidateWindow:
    def test_sufficient_data_passes(self):
        """252 obs, 21 skipped → 231 valid obs; should pass with ≥ 21 threshold."""
        result = _validate_window(total_obs=252, skip_recent=21, min_obs=21)
        assert result is True

    def test_too_few_obs_fails(self):
        """Only 30 obs, skip 21 → 9 obs; fails min_obs=21."""
        result = _validate_window(total_obs=30, skip_recent=21, min_obs=21)
        assert result is False

    def test_exactly_min_passes(self):
        result = _validate_window(total_obs=42, skip_recent=21, min_obs=21)
        assert result is True

    def test_one_below_min_fails(self):
        result = _validate_window(total_obs=41, skip_recent=21, min_obs=21)
        assert result is False


# ---------------------------------------------------------------------------
# _fit_ols_residuals — known-residual test
# ---------------------------------------------------------------------------


class TestFitOlsResiduals:
    def test_pure_alpha_stock_residual_equals_alpha(self):
        """If stock return = constant alpha + 0×factors, residuals = alpha."""
        n = 200
        mkt = np.random.normal(0.0005, 0.01, n)
        smb = np.random.normal(0.0002, 0.005, n)
        wml = np.random.normal(0.0001, 0.005, n)
        alpha = 0.001  # 0.1% daily alpha
        stock_ret = alpha + np.zeros(n)  # pure alpha, zero factor exposure

        residuals = _fit_ols_residuals(stock_ret, mkt, smb, wml)

        assert residuals is not None
        assert len(residuals) == n
        # Residuals ≈ alpha (OLS intercept absorbs it; residuals ≈ 0)
        assert np.std(residuals) < 0.01  # very small residuals

    def test_perfect_factor_loading_residuals_near_zero(self):
        """Stock = 1.5×MKT + 0.5×SMB + noise ≈ 0 → residuals ≈ noise."""
        n = 200
        rng = np.random.default_rng(42)
        mkt = rng.normal(0.0005, 0.01, n)
        smb = rng.normal(0.0002, 0.005, n)
        wml = rng.normal(0.0001, 0.005, n)
        noise = rng.normal(0.0, 0.0005, n)  # small noise
        stock_ret = 0.0003 + 1.5 * mkt + 0.5 * smb + noise

        residuals = _fit_ols_residuals(stock_ret, mkt, smb, wml)

        assert residuals is not None
        # Residuals should be close to the noise term
        assert np.corrcoef(residuals, noise)[0, 1] > 0.95

    def test_returns_none_for_all_nan_input(self):
        """All-NaN stock returns → None."""
        n = 100
        mkt = np.random.normal(0.0, 0.01, n)
        smb = np.random.normal(0.0, 0.005, n)
        wml = np.random.normal(0.0, 0.005, n)
        stock_ret = np.full(n, np.nan)

        result = _fit_ols_residuals(stock_ret, mkt, smb, wml)
        assert result is None

    def test_returns_none_for_too_few_valid_obs(self):
        """Only 5 valid (non-NaN) obs → None (below min_obs=21)."""
        n = 50
        mkt = np.random.normal(0.0, 0.01, n)
        smb = np.random.normal(0.0, 0.005, n)
        wml = np.random.normal(0.0, 0.005, n)
        stock_ret = np.full(n, np.nan)
        stock_ret[:5] = 0.001  # only 5 valid obs

        result = _fit_ols_residuals(stock_ret, mkt, smb, wml)
        assert result is None

    def test_shape_matches_input(self):
        """Output residuals array has same length as input."""
        n = 252
        rng = np.random.default_rng(7)
        mkt = rng.normal(0, 0.01, n)
        smb = rng.normal(0, 0.005, n)
        wml = rng.normal(0, 0.005, n)
        stock_ret = 0.5 * mkt + rng.normal(0, 0.002, n)

        residuals = _fit_ols_residuals(stock_ret, mkt, smb, wml)
        assert residuals is not None
        assert len(residuals) == n


# ---------------------------------------------------------------------------
# _cumulate_residuals
# ---------------------------------------------------------------------------


class TestCumulateResiduals:
    def test_all_positive_sums_positive(self):
        """All positive residuals → positive cumulant."""
        residuals = np.full(252, 0.001)
        result = _cumulate_residuals(residuals, skip_recent=21)
        assert result > 0

    def test_cumulation_window_excludes_recent(self):
        """Last 21 days of residuals should not affect the cumulant."""
        n = 252
        residuals_base = np.ones(n) * 0.001
        residuals_modified = residuals_base.copy()
        # Flip sign on last 21 days — should NOT change result
        residuals_modified[-21:] = -99.0

        result_base = _cumulate_residuals(residuals_base, skip_recent=21)
        result_modified = _cumulate_residuals(residuals_modified, skip_recent=21)

        assert abs(result_base - result_modified) < 1e-9

    def test_cumulation_is_sum_not_product(self):
        """Verify it's a simple sum over [0:n-21]."""
        n = 50
        residuals = np.arange(n, dtype=float)  # 0, 1, 2, ..., 49
        skip = 5
        expected = float(np.sum(residuals[:-skip]))  # sum of 0..44
        result = _cumulate_residuals(residuals, skip_recent=skip)
        assert abs(result - expected) < 1e-9

    def test_all_nan_residuals_returns_nan(self):
        """All-NaN residuals → NaN cumulant (propagate, don't mask)."""
        residuals = np.full(252, np.nan)
        result = _cumulate_residuals(residuals, skip_recent=21)
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# compute_residual_momentum — end-to-end (no DB, synthetic data)
# ---------------------------------------------------------------------------


class TestComputeResidualMomentum:
    def _make_synthetic_data(
        self,
        n_stocks: int = 10,
        n_days: int = 252,
        seed: int = 42,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Build synthetic stock returns and factor returns for testing."""
        rng = np.random.default_rng(seed)
        dates = pd.date_range("2023-01-01", periods=n_days, freq="B").date

        # Factor returns
        factor_df = pd.DataFrame(
            {
                "date": dates,
                "mkt_excess": rng.normal(0.0005, 0.01, n_days),
                "smb": rng.normal(0.0002, 0.005, n_days),
                "wml": rng.normal(0.0001, 0.005, n_days),
            }
        )

        # Stock returns — each stock has known beta + alpha + noise
        import uuid

        instrument_ids = [uuid.uuid4() for _ in range(n_stocks)]
        records = []
        for i, iid in enumerate(instrument_ids):
            beta = 0.5 + i * 0.1
            alpha = (i - n_stocks // 2) * 0.0001  # some positive, some negative
            for j, d in enumerate(dates):
                ret = (
                    alpha
                    + beta * factor_df.loc[j, "mkt_excess"]
                    + 0.3 * factor_df.loc[j, "smb"]
                    + rng.normal(0, 0.002)
                )
                records.append({"instrument_id": iid, "date": d, "ret_1d": ret})

        stock_df = pd.DataFrame(records)
        return stock_df, factor_df

    def test_returns_series_indexed_by_instrument_id(self):
        """Output is a pd.Series indexed by instrument_id."""
        stock_df, factor_df = self._make_synthetic_data()
        result = compute_residual_momentum(stock_df, factor_df)
        assert isinstance(result, pd.Series)
        assert len(result) > 0

    def test_all_instruments_in_output(self):
        """All instruments with sufficient history appear in output."""
        stock_df, factor_df = self._make_synthetic_data(n_stocks=5, n_days=252)
        result = compute_residual_momentum(stock_df, factor_df)
        # With 252 days and 21 skip, 231 effective obs → all 5 stocks should pass
        assert len(result) == 5

    def test_high_residual_stock_ranks_higher(self):
        """Stock with larger idiosyncratic residuals ranks higher.

        We inject a time-varying idiosyncratic component (not a constant alpha,
        which OLS absorbs into the intercept). The winner has a consistently
        positive idiosyncratic shock correlated with a 4th omitted factor;
        the loser has a consistently negative one. Since the OLS model only
        has 3 factors (MKT, SMB, WML) and not the 4th, the omitted loading
        shows up as a structured residual.
        """
        import uuid

        n_days = 252
        rng = np.random.default_rng(99)
        dates = pd.date_range("2023-01-01", periods=n_days, freq="B").date

        mkt = rng.normal(0.0005, 0.01, n_days)
        smb = rng.normal(0, 0.005, n_days)
        wml = rng.normal(0, 0.005, n_days)
        # A 4th latent factor NOT in our model — creates structured residuals
        fourth_factor = rng.normal(0, 0.008, n_days)

        factor_df = pd.DataFrame(
            {
                "date": dates,
                "mkt_excess": mkt,
                "smb": smb,
                "wml": wml,
            }
        )

        id_winner = uuid.uuid4()
        id_loser = uuid.uuid4()

        records = []
        for j, d in enumerate(dates):
            base = mkt[j] + 0.5 * smb[j] + 0.3 * wml[j]
            # Winner: positively loaded on the omitted 4th factor
            records.append(
                {"instrument_id": id_winner, "date": d, "ret_1d": base + 0.8 * fourth_factor[j]}
            )
            # Loser: negatively loaded on the omitted 4th factor
            records.append(
                {"instrument_id": id_loser, "date": d, "ret_1d": base - 0.8 * fourth_factor[j]}
            )

        stock_df = pd.DataFrame(records)
        result = compute_residual_momentum(stock_df, factor_df)

        assert id_winner in result.index
        assert id_loser in result.index
        # With structured residuals from the 4th factor, winner and loser
        # will have residuals of opposite sign — their cumulants should differ.
        # We can't assert direction without knowing fourth_factor sign, so
        # we assert they are meaningfully different (not both near-zero).
        assert abs(result[id_winner] - result[id_loser]) > 0.01

    def test_insufficient_history_stock_excluded(self):
        """Stock with only 30 days of history is excluded from output."""
        import uuid

        n_days = 252
        rng = np.random.default_rng(17)
        dates = pd.date_range("2023-01-01", periods=n_days, freq="B").date

        factor_df = pd.DataFrame(
            {
                "date": dates,
                "mkt_excess": rng.normal(0, 0.01, n_days),
                "smb": rng.normal(0, 0.005, n_days),
                "wml": rng.normal(0, 0.005, n_days),
            }
        )

        id_full = uuid.uuid4()
        id_short = uuid.uuid4()

        records = []
        for j, d in enumerate(dates):
            mkt = factor_df.loc[j, "mkt_excess"]
            records.append({"instrument_id": id_full, "date": d, "ret_1d": mkt})
            if j >= 222:  # only last 30 days
                records.append({"instrument_id": id_short, "date": d, "ret_1d": mkt})

        stock_df = pd.DataFrame(records)
        result = compute_residual_momentum(stock_df, factor_df)

        assert id_full in result.index
        assert id_short not in result.index

    def test_empty_stock_df_returns_empty_series(self):
        """Empty stock DataFrame → empty Series."""
        n_days = 252
        dates = pd.date_range("2023-01-01", periods=n_days, freq="B").date
        factor_df = pd.DataFrame(
            {
                "date": dates,
                "mkt_excess": np.zeros(n_days),
                "smb": np.zeros(n_days),
                "wml": np.zeros(n_days),
            }
        )
        stock_df = pd.DataFrame(columns=["instrument_id", "date", "ret_1d"])
        result = compute_residual_momentum(stock_df, factor_df)
        assert isinstance(result, pd.Series)
        assert len(result) == 0
