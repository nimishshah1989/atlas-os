"""Per-stock residual momentum via 3-factor OLS residualization.

Method: Blitz-Huij-Martens (2011), "Residual momentum", Journal of Empirical Finance.

Steps (per spec §5.3 Step 2):
  1. For each stock i on date t:
     - Pull trailing 252d daily returns aligned to factor dates
     - OLS regress: r_i = alpha + beta_mkt×MKT + beta_smb×SMB + beta_wml×WML + epsilon
  2. Cumulate epsilon over [t-252 : t-21] window (12-minus-1 momentum window;
     the most recent 21 trading days are excluded to avoid short-term reversal).
  3. Return pd.Series indexed by instrument_id with cumulative residual per stock.

The design matrix is built once from factor_df; only the stock return vector
changes per instrument, so no redundant matrix construction in the inner loop.
"""

from __future__ import annotations

import math
import uuid

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()

# OLS window constants (spec §5.3)
_LOOKBACK_DAYS = 252  # total trailing window
_SKIP_RECENT = 21  # exclude last 21 trading days (reversal avoidance)
_MIN_VALID_OBS = 21  # minimum non-NaN obs to attempt OLS fit


# ---------------------------------------------------------------------------
# Pure helpers (no DB; fully testable)
# ---------------------------------------------------------------------------


def _validate_window(total_obs: int, skip_recent: int, min_obs: int) -> bool:
    """True if we have at least min_obs non-skipped observations."""
    return (total_obs - skip_recent) >= min_obs


def _fit_ols_residuals(
    stock_ret: np.ndarray,
    mkt: np.ndarray,
    smb: np.ndarray,
    wml: np.ndarray,
    min_obs: int = _MIN_VALID_OBS,
) -> np.ndarray | None:
    """OLS: stock_ret = alpha + b1×MKT + b2×SMB + b3×WML + epsilon.

    Args:
        stock_ret: Daily returns array, shape (n,). May contain NaN for missing days.
        mkt:       Market-excess factor, shape (n,).
        smb:       Size factor, shape (n,).
        wml:       Momentum factor, shape (n,).
        min_obs:   Minimum non-NaN observations; returns None if below.

    Returns:
        Residual array shape (n,) with NaN at original NaN positions,
        or None if insufficient valid observations.
    """
    n = len(stock_ret)
    valid_mask = ~np.isnan(stock_ret)
    n_valid = int(np.sum(valid_mask))

    if n_valid < min_obs:
        return None

    # Build design matrix [1, MKT, SMB, WML] for valid rows only
    # N806: matrix variable intentionally uppercase per math convention (X = design matrix)
    design_matrix = np.column_stack(
        [
            np.ones(n_valid),
            mkt[valid_mask],
            smb[valid_mask],
            wml[valid_mask],
        ]
    )
    y_valid = stock_ret[valid_mask]

    # OLS via least-squares — no inversion blowup (lstsq is numerically stable)
    coeffs, _lstsq_res, _rank, _sv = np.linalg.lstsq(design_matrix, y_valid, rcond=None)

    # Residuals = actual - fitted (for valid obs only; NaN elsewhere)
    residuals = np.full(n, np.nan)
    residuals[valid_mask] = y_valid - (design_matrix @ coeffs)

    return residuals


def _cumulate_residuals(
    residuals: np.ndarray,
    skip_recent: int = _SKIP_RECENT,
) -> float:
    """Sum residuals over [0 : n-skip_recent] (excludes last skip_recent days).

    Returns NaN when all residuals in the window are NaN.
    """
    window = residuals[:-skip_recent] if skip_recent > 0 else residuals
    with np.errstate(all="ignore"):
        total = float(np.nansum(window))
        n_valid = int(np.sum(~np.isnan(window)))
    if n_valid == 0:
        return float("nan")
    return total


# ---------------------------------------------------------------------------
# Public compute function (no DB — accepts pre-loaded DataFrames)
# ---------------------------------------------------------------------------


def compute_residual_momentum(
    stock_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    lookback_days: int = _LOOKBACK_DAYS,
    skip_recent: int = _SKIP_RECENT,
    min_obs: int = _MIN_VALID_OBS,
) -> pd.Series:
    """Compute 12-1 residual momentum for all stocks in stock_returns.

    Args:
        stock_returns:  DataFrame with columns [instrument_id, date, ret_1d].
                        Should contain ~252+ trading days per stock.
        factor_returns: DataFrame with columns [date, mkt_excess, smb, wml].
                        Must cover the same date range as stock_returns.
        lookback_days:  Number of trailing days for regression (default 252).
        skip_recent:    Days to exclude from residual sum (default 21, reversal).
        min_obs:        Minimum non-NaN obs per stock to include (default 21).

    Returns:
        pd.Series indexed by instrument_id, values = cumulative residual (12-1).
        Stocks with insufficient history are excluded.
    """
    if stock_returns.empty:
        log.debug("residual_momentum.empty_stock_df")
        return pd.Series(dtype=float)

    # Ensure date columns are comparable type
    stock_returns = stock_returns.copy()
    factor_returns = factor_returns.copy()

    # Join stock returns with factor returns on date
    merged = stock_returns.merge(
        factor_returns[["date", "mkt_excess", "smb", "wml"]],
        on="date",
        how="inner",
    )

    if merged.empty:
        log.warning("residual_momentum.no_factor_overlap")
        return pd.Series(dtype=float)

    # Sort for consistent window ordering
    merged = merged.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # Build factor arrays aligned to the merged date index
    # We iterate per instrument; factor arrays are the same rows each time
    results: dict[uuid.UUID, float] = {}

    n_total = 0
    n_excluded = 0
    n_all_nan = 0

    for instrument_id, grp in merged.groupby("instrument_id", sort=False):
        grp = grp.sort_values("date")

        if len(grp) < (min_obs + skip_recent):
            n_excluded += 1
            continue

        n_total += 1

        stock_ret = grp["ret_1d"].to_numpy(dtype=float)
        mkt = grp["mkt_excess"].to_numpy(dtype=float)
        smb = grp["smb"].to_numpy(dtype=float)
        wml = grp["wml"].to_numpy(dtype=float)

        residuals = _fit_ols_residuals(stock_ret, mkt, smb, wml, min_obs=min_obs)
        if residuals is None:
            n_all_nan += 1
            continue

        cumulant = _cumulate_residuals(residuals, skip_recent=skip_recent)
        if math.isnan(cumulant):
            n_all_nan += 1
            continue

        results[instrument_id] = cumulant

    log.info(
        "residual_momentum.computed",
        total_attempted=n_total,
        excluded_short_history=n_excluded,
        excluded_all_nan=n_all_nan,
        output_count=len(results),
    )

    return pd.Series(results, dtype=float)
