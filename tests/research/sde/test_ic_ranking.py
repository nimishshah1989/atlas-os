"""Tests for SDE Phase 0 IC ranking and decision gate."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from atlas.research.sde.ic_ranking import (
    FactorICRow,
    evaluate_gate,
    forward_returns_wide,
    rank_factors,
    time_split,
)


def test_time_split_70_30() -> None:
    dates = pd.bdate_range("2022-01-03", periods=100)
    train, test = time_split(dates, train_frac=0.7)
    assert len(train) == 70
    assert len(test) == 30
    assert train[-1] < test[0]


def test_forward_returns_wide_computes_simple_return() -> None:
    close_panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=4).tolist(),
            "instrument_id": ["aaa"] * 4,
            "close": [10.0, 11.0, 12.0, 13.0],
        }
    )
    fwd = forward_returns_wide(close_panel, horizon=1)
    # forward 1-day return at row 0 = 11/10 - 1 = 0.1
    assert abs(fwd.iloc[0]["aaa"] - 0.1) < 1e-9


def test_rank_factors_orders_by_abs_test_ic() -> None:
    # Two factors; fake ic_fn returns a fixed IC per factor via call order.
    idx = pd.MultiIndex.from_product(
        [pd.bdate_range("2022-01-03", periods=10), ["aaa"]],
        names=["date", "instrument_id"],
    )
    factors = {
        "weak": pd.DataFrame({"factor": range(10)}, index=idx),
        "strong": pd.DataFrame({"factor": range(10)}, index=idx),
    }
    close_panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=10).tolist(),
            "instrument_id": ["aaa"] * 10,
            "close": [10.0 + i for i in range(10)],
        }
    )
    ic_by_factor = {"weak": 0.01, "strong": 0.20}
    calls: list[str] = []

    def fake_ic_fn(factor_frame: pd.DataFrame, returns_wide: pd.DataFrame):
        # factor_frame carries the factor name via attrs set in rank_factors.
        name = factor_frame.attrs["sde_name"]
        calls.append(name)
        return SimpleNamespace(mean_ic=ic_by_factor[name], ic_t_stat=3.0, n_observations=5)

    rows = rank_factors(factors, close_panel, horizons=[1], ic_fn=fake_ic_fn, train_frac=0.7)
    assert rows[0].factor == "strong"
    assert rows[1].factor == "weak"


def test_evaluate_gate_proceeds_on_strong_factor() -> None:
    rows = [
        FactorICRow("x", 63, train_ic=0.05, train_t=3.0, test_ic=0.04, test_t=2.5, n_test=20),
    ]
    result = evaluate_gate(rows, min_ic=0.03, min_t=2.0)
    assert result["proceed"] is True


def test_evaluate_gate_stops_on_weak_or_sign_flipped() -> None:
    rows = [
        FactorICRow("a", 63, train_ic=0.05, train_t=3.0, test_ic=0.01, test_t=0.5, n_test=20),
        FactorICRow("b", 63, train_ic=0.05, train_t=3.0, test_ic=-0.04, test_t=2.5, n_test=20),
    ]
    result = evaluate_gate(rows, min_ic=0.03, min_t=2.0)
    assert result["proceed"] is False
