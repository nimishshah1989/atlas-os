"""SDE Phase 0 IC ranking and decision gate.

Splits the date range into a train/test slice, computes forward returns,
and ranks each factor by out-of-sample IC. The IC function is injected
(ic_fn) so this module carries no cross-context import — the spike script
passes in atlas.intelligence.validation.ic_engine.compute_ic_over_window.

Honesty note: with overlapping forward-return windows the per-date IC
series is autocorrelated, so the injected t-stat is optimistic. Phase 0
treats it as a coarse screen; the autocorrelation correction is a Phase 1
concern.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd
import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class FactorICRow:
    """One factor's IC measured on the train and test splits at one horizon."""

    factor: str
    horizon: int
    train_ic: float
    train_t: float
    test_ic: float
    test_t: float
    n_test: int


def time_split(
    dates: pd.Index | Sequence[pd.Timestamp], *, train_frac: float = 0.7
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Split a set of dates chronologically into (train, test) DatetimeIndexes."""
    uniq = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dates).unique()))
    cut = int(len(uniq) * train_frac)
    return uniq[:cut], uniq[cut:]


def forward_returns_wide(close_panel: pd.DataFrame, *, horizon: int) -> pd.DataFrame:
    """Wide forward-return DataFrame: index=date, columns=instrument_id.

    close_panel: long DataFrame with date, instrument_id, close.
    Value at (t, i) = close[t+horizon] / close[t] - 1.
    """
    wide = close_panel.pivot(index="date", columns="instrument_id", values="close")
    wide.index = pd.DatetimeIndex(wide.index)
    return wide.shift(-horizon) / wide - 1.0


def rank_factors(
    factors: dict[str, pd.DataFrame],
    close_panel: pd.DataFrame,
    *,
    horizons: Sequence[int],
    ic_fn: Callable[[pd.DataFrame, pd.DataFrame], object],
    mask: pd.Series | None = None,
    train_frac: float = 0.7,
) -> list[FactorICRow]:
    """Rank factors by absolute out-of-sample IC across horizons.

    factors: dict[name -> (date, instrument_id) MultiIndex 'factor' frame].
    ic_fn: callable(factor_frame, returns_wide) -> object with attributes
           mean_ic, ic_t_stat, n_observations.
    mask: optional (date, instrument_id) boolean Series; factor rows where
          the mask is False are dropped before IC computation.
    """
    rows: list[FactorICRow] = []
    for horizon in horizons:
        fwd = forward_returns_wide(close_panel, horizon=horizon)
        train_d, test_d = time_split(fwd.index, train_frac=train_frac)
        for name, frame in factors.items():
            if mask is not None:
                aligned = mask.reindex(frame.index).fillna(False)
                frame = frame[aligned]
            if frame.empty:
                continue
            fdates = frame.index.get_level_values("date")
            train_frame: pd.DataFrame = frame[fdates.isin(train_d)].copy()  # type: ignore[assignment]
            test_frame: pd.DataFrame = frame[fdates.isin(test_d)].copy()  # type: ignore[assignment]
            train_frame.attrs["sde_name"] = name
            test_frame.attrs["sde_name"] = name
            fwd_train: pd.DataFrame = fwd.loc[fwd.index.intersection(train_d)]  # type: ignore[assignment]
            fwd_test: pd.DataFrame = fwd.loc[fwd.index.intersection(test_d)]  # type: ignore[assignment]
            train_ic = ic_fn(train_frame, fwd_train)
            test_ic = ic_fn(test_frame, fwd_test)
            rows.append(
                FactorICRow(
                    factor=name,
                    horizon=horizon,
                    train_ic=float(train_ic.mean_ic),  # type: ignore[attr-defined]
                    train_t=float(train_ic.ic_t_stat),  # type: ignore[attr-defined]
                    test_ic=float(test_ic.mean_ic),  # type: ignore[attr-defined]
                    test_t=float(test_ic.ic_t_stat),  # type: ignore[attr-defined]
                    n_test=int(test_ic.n_observations),  # type: ignore[attr-defined]
                )
            )

    rows.sort(key=lambda r: abs(r.test_ic) if pd.notna(r.test_ic) else 0.0, reverse=True)
    log.info("sde_factors_ranked", n_rows=len(rows))
    return rows


def evaluate_gate(
    rows: Sequence[FactorICRow], *, min_ic: float = 0.03, min_t: float = 2.0
) -> dict[str, object]:
    """Decision gate. PROCEED if at least one factor/horizon has out-of-sample
    IC of the same sign as its train IC, with |test_ic| >= min_ic and
    |test_t| >= min_t. Otherwise STOP.
    """
    survivors = [
        r
        for r in rows
        if pd.notna(r.test_ic)
        and pd.notna(r.train_ic)
        and (r.test_ic > 0) == (r.train_ic > 0)
        and abs(r.test_ic) >= min_ic
        and abs(r.test_t) >= min_t
    ]
    return {"proceed": bool(survivors), "survivors": survivors}
