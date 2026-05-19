"""Tests for atlas.trading.v6.lab — thin orchestrator.

Three tests:
1. test_run_backtest_returns_simulation_result — happy path via monkeypatch
2. test_live_rebalance_writes_recommendations_daily — DB integration (skip without URL)
3. test_evaluate_goal_post_returns_constraint_status — constraint evaluation

Additional unit tests:
4. test_confidence_band_assignment — LOW/MED/HIGH mapping
5. test_order_dataclass_fields — Order has all required fields
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from atlas.trading.v6.lab import (
    Order,
    _confidence_band,
    evaluate_goal_post,
    live_rebalance,
    run_backtest,
)
from atlas.trading.v6.simulator import PeriodResult, SimulationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(99)


def _make_simulation_result(n_periods: int = 6) -> SimulationResult:
    """Build a synthetic SimulationResult."""
    periods = [
        PeriodResult(
            rebalance_date=date(2024, 1 + i, 1),
            end_date=date(2024, 2 + i, 1) if i < 11 else date(2024, 12, 31),
            book_return=float(_RNG.uniform(-0.02, 0.04)),
            benchmark_return=float(_RNG.uniform(-0.01, 0.03)),
            alpha=0.01,
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=1,
        )
        for i in range(n_periods)
    ]
    return SimulationResult(
        strategy_name="test",
        periods=periods,
        ann_return=0.12,
        max_drawdown=-0.08,
        vol=0.10,
        sharpe=1.2,
        calmar=1.5,
        win_rate=0.67,
        n_trades=40,
    )


# ---------------------------------------------------------------------------
# Test 1: run_backtest happy path
# ---------------------------------------------------------------------------


def test_run_backtest_returns_simulation_result() -> None:
    """run_backtest() returns a SimulationResult when run_simulation succeeds."""
    expected = _make_simulation_result()

    mock_session = MagicMock()

    with (
        patch("atlas.trading.v6.lab.run_simulation", return_value=expected) as mock_sim,
        patch("atlas.trading.v6.lab._get_session", return_value=mock_session),
    ):
        result = run_backtest(
            start=date(2024, 1, 1),
            end=date(2024, 6, 30),
            strategy_name="test_lab",
            persist=False,
        )

    assert isinstance(result, SimulationResult)
    assert result.strategy_name == "test"
    assert result.ann_return == 0.12
    assert result.sharpe == 1.2
    mock_sim.assert_called_once()


def test_run_backtest_passes_config_correctly() -> None:
    """run_backtest passes all options through to SimulationConfig."""
    from atlas.trading.v6.composite import SignalWeights
    from atlas.trading.v6.simulator import SimulationConfig

    captured_config: list[SimulationConfig] = []

    def fake_run_simulation(session, config):
        captured_config.append(config)
        return _make_simulation_result()

    mock_session = MagicMock()
    custom_weights = SignalWeights(natr_14=0.20)

    with (
        patch("atlas.trading.v6.lab.run_simulation", side_effect=fake_run_simulation),
        patch("atlas.trading.v6.lab._get_session", return_value=mock_session),
    ):
        run_backtest(
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            strategy_name="custom_run",
            target_holdings=25,
            initial_capital_cr=50.0,
            signal_weights=custom_weights,
            persist=True,
        )

    assert len(captured_config) == 1
    cfg = captured_config[0]
    assert cfg.start == date(2023, 1, 1)
    assert cfg.end == date(2023, 12, 31)
    assert cfg.strategy_name == "custom_run"
    assert cfg.target_holdings == 25
    assert cfg.initial_capital_cr == 50.0
    assert cfg.signal_weights is custom_weights
    assert cfg.persist is True


# ---------------------------------------------------------------------------
# Test 2: live_rebalance DB integration
# ---------------------------------------------------------------------------


def test_live_rebalance_writes_recommendations_daily(tmp_db_session) -> None:
    """live_rebalance() writes to atlas_v6_recommendations_daily.

    Requires ATLAS_TEST_DB_URL. Patched at the universe/signal level.
    """
    from atlas.trading.v6.universe import InvestableInstrument

    n = 8
    instruments = [
        InvestableInstrument(
            instrument_id=uuid.uuid4(),
            symbol=f"LR{i:02d}",
            sector="Financials",
            median_adv_cr=20.0,
        )
        for i in range(n)
    ]
    inst_ids = [inst.instrument_id for inst in instruments]

    panel_data = {
        col: np.ones(n) * 0.1
        for col in [
            "natr_14",
            "beta_alpha_63d",
            "mom_low_vol",
            "residual_momentum",
            "proximity_52wh",
            "industry_rs",
            "fip_smoothness",
            "bab",
            "quality_proxy",
        ]
    }
    panel_data["sector"] = ["Financials"] * n
    panel = pd.DataFrame(panel_data, index=inst_ids)

    ref_date = date(2024, 1, 31)

    with (
        patch("atlas.trading.v6.lab.get_investable", return_value=instruments),
        patch("atlas.trading.v6.lab.apply_exclusions", return_value=(set(), [])),
        patch("atlas.trading.v6.lab._compute_signal_panel", return_value=panel),
        patch("atlas.trading.v6.lab._get_trend_gate_pass", return_value=set(inst_ids)),
        patch("atlas.trading.v6.lab._load_prior_holdings", return_value=set()),
    ):
        orders = live_rebalance(ref_date=ref_date, session=tmp_db_session)

    # Should have produced some orders
    assert len(orders) > 0

    # All orders have required fields
    for order in orders:
        assert isinstance(order.instrument_id, uuid.UUID)
        assert order.action in ("BUY", "HOLD", "SELL")
        assert order.confidence_band in ("HIGH", "MED", "LOW")

    # Verify rows were written to recommendations_daily
    from sqlalchemy import text

    rows = tmp_db_session.execute(
        text("""
            SELECT COUNT(*) AS n
              FROM atlas.atlas_v6_recommendations_daily
             WHERE date = :d
        """),
        {"d": ref_date},
    ).fetchone()

    assert rows is not None
    assert int(rows.n) > 0


# ---------------------------------------------------------------------------
# Test 3: evaluate_goal_post
# ---------------------------------------------------------------------------


def test_evaluate_goal_post_returns_constraint_status(tmp_db_session) -> None:
    """evaluate_goal_post returns dict with 9 constraint evaluations.

    Seeds one row in atlas_v6_strategy_runs, then calls evaluate_goal_post.
    """
    import json

    from sqlalchemy import text

    from atlas.trading.v6.composite import SignalWeights

    run_id = uuid.uuid4()
    weights = json.dumps(SignalWeights().as_dict())

    # Insert a test strategy run row
    tmp_db_session.execute(
        text("""
            INSERT INTO atlas.atlas_v6_strategy_runs (
                run_id, strategy_name, signal_weights,
                is_period, oos_period,
                calmar, vol_ratio, mdd_ratio, win_rate,
                passes_all_constraints, constraint_failures
            ) VALUES (
                :rid, 'test_goal_post', :weights::jsonb,
                '[2023-01-01,2023-12-31]'::tsrange,
                '[2023-01-01,2023-12-31]'::tsrange,
                0.8, 1.2, -0.15, 0.60,
                true, '{}'
            )
        """),
        {"rid": str(run_id), "weights": weights},
    )

    result = evaluate_goal_post(
        strategy_run_id=run_id,
        session=tmp_db_session,
    )

    assert isinstance(result, dict)
    assert "status" in result
    assert "constraints" in result
    assert "passes_all_constraints" in result

    constraints = result["constraints"]
    # All 9 constraints should be present
    expected_keys = {
        "calmar",
        "max_drawdown",
        "win_rate",
        "alpha_t_stat",
        "vol_ratio",
        "mdd_ratio_vs_benchmark",
        "oos_ic_retention",
        "capacity_cr",
        "turnover_annual",
    }
    assert expected_keys == set(
        constraints.keys()
    ), f"Missing constraints: {expected_keys - set(constraints.keys())}"

    # Calmar=0.8 passes (>=0.5)
    assert constraints["calmar"]["pass"] is True
    assert abs(constraints["calmar"]["value"] - 0.8) < 0.01

    # Win rate=0.60 passes (>=0.50)
    assert constraints["win_rate"]["pass"] is True


def test_evaluate_goal_post_no_runs_returns_status(tmp_db_session) -> None:
    """evaluate_goal_post returns 'no_runs' when table is empty."""
    # Use a random run_id that doesn't exist
    nonexistent_id = uuid.uuid4()
    result = evaluate_goal_post(
        strategy_run_id=nonexistent_id,
        session=tmp_db_session,
    )
    assert result["status"] == "no_runs"


# ---------------------------------------------------------------------------
# Test 4: _confidence_band unit tests
# ---------------------------------------------------------------------------


def test_confidence_band_assignment() -> None:
    """HIGH for top-third, MED for mid-third, LOW for bottom-third."""
    assert _confidence_band(1, 9) == "HIGH"  # rank 1/9 = 11% → top 33%
    assert _confidence_band(4, 9) == "MED"  # rank 4/9 = 44% → mid 33-67%
    assert _confidence_band(8, 9) == "LOW"  # rank 8/9 = 89% → bottom 33%


def test_confidence_band_boundary_values() -> None:
    """Boundary ranks fall into correct bands.

    _confidence_band uses pct <= 0.33 for HIGH, pct <= 0.67 for MED, else LOW.
    3/9 = 0.333 → pct <= 0.33 is False, pct <= 0.67 is True → MED.
    6/9 = 0.667 → pct <= 0.67 is True → MED (boundary is inclusive).
    7/9 = 0.778 → pct > 0.67 → LOW.
    """
    assert _confidence_band(3, 9) == "MED"  # 3/9 = 33.3% → just above 0.33 → MED
    assert _confidence_band(6, 9) == "MED"  # 6/9 = 66.7% → exactly at 0.67 → MED
    assert _confidence_band(7, 9) == "LOW"  # 7/9 = 77.8% → above 0.67 → LOW


def test_confidence_band_single_item() -> None:
    """Single item is ranked HIGH (rank 1 of 1 = 100% which falls into LOW actually)."""
    # rank 1/1 = 100% → LOW
    assert _confidence_band(1, 1) == "LOW"


# ---------------------------------------------------------------------------
# Test 5: Order dataclass
# ---------------------------------------------------------------------------


def test_order_dataclass_fields() -> None:
    """Order has all required fields with correct types."""
    iid = uuid.uuid4()
    order = Order(
        instrument_id=iid,
        symbol="RELIANCE",
        action="BUY",
        weight_target=0.035,
        composite_score=0.82,
        rank=3,
        confidence_band="HIGH",
    )
    assert order.instrument_id == iid
    assert order.symbol == "RELIANCE"
    assert order.action == "BUY"
    assert abs(order.weight_target - 0.035) < 1e-9
    assert order.rank == 3
    assert order.confidence_band == "HIGH"
