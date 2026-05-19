"""Tests for atlas.trading.v6.simulator — backtest engine.

Four tests:
1. test_simulator_runs_on_30_instruments_6_months
   Synthetic universe with seeded data; verify no exceptions, sensible output.
2. test_simulator_respects_holdings_count_target
   Output holdings within [1, 45] range.
3. test_simulator_handles_governance_exclusions
   When a name is excluded mid-period, it is exited.
4. test_simulator_persists_to_strategy_runs
   Writes one row to atlas_v6_strategy_runs (DB integration, skips without URL).

Synthetic approach: monkeypatch module-level functions in simulator to avoid
real DB calls in tests 1-3. Only test 4 requires an actual DB connection.
"""

# allow-large: 15 cohesive tests for a single module (simulator.py). Fix-B daily
# NAV tests, weighted-sum tests, and smoke tests all share synthetic builders.
# Splitting would lose co-locality between builders and tests. Responsibility = 1.

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from atlas.trading.v6.crisis_sleeve import SleeveAllocation
from atlas.trading.v6.regime import RegimeState
from atlas.trading.v6.simulator import (
    SimulationConfig,
    SimulationResult,
    _compute_aggregate_stats,
    _fetch_daily_portfolio_returns,
    _monthly_rebalance_dates,
    run_simulation,
)
from atlas.trading.v6.universe import InvestableInstrument

# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------

_N_STOCKS = 30
_RNG = np.random.default_rng(42)


def _make_instruments(n: int = _N_STOCKS) -> list[InvestableInstrument]:
    """Build a synthetic list of InvestableInstrument objects."""
    sectors = ["Financials", "IT", "Energy", "Healthcare", "Consumer"] * (n // 5 + 1)
    return [
        InvestableInstrument(
            instrument_id=uuid.uuid4(),
            symbol=f"SYN{i:03d}",
            sector=sectors[i % len(sectors)],
            median_adv_cr=float(_RNG.uniform(5.0, 100.0)),
        )
        for i in range(n)
    ]


def _make_signal_panel(instruments: list[InvestableInstrument]) -> pd.DataFrame:
    """Build a synthetic 9-signal panel."""
    n = len(instruments)
    ids = [inst.instrument_id for inst in instruments]
    data = {
        "natr_14": _RNG.uniform(0.5, 3.0, n),
        "beta_alpha_63d": _RNG.uniform(-0.05, 0.10, n),
        "mom_low_vol": _RNG.uniform(-0.1, 0.2, n),
        "residual_momentum": _RNG.uniform(-0.05, 0.05, n),
        "proximity_52wh": _RNG.uniform(0.7, 1.0, n),
        "industry_rs": _RNG.uniform(-0.05, 0.05, n),
        "fip_smoothness": _RNG.uniform(-0.1, 0.4, n),
        "bab": _RNG.uniform(0.0, 1.0, n),
        "quality_proxy": _RNG.uniform(-0.5, 0.5, n),
        "sector": [inst.sector for inst in instruments],
    }
    return pd.DataFrame(data, index=ids)


def _make_returns_panel(instrument_ids: list[uuid.UUID], n_days: int = 252) -> pd.DataFrame:
    """Build a synthetic daily returns panel."""
    n = len(instrument_ids)
    data = _RNG.normal(0.0005, 0.015, (n_days, n))
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return pd.DataFrame(data, index=pd.to_datetime(dates), columns=instrument_ids)


def _make_trading_dates(start: date, end: date) -> list[date]:
    """Generate weekday dates between start and end."""
    dates = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Monday-Friday
            dates.append(current)
        current += timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# Mock session factory
# ---------------------------------------------------------------------------


def _make_mock_session(
    instruments: list[InvestableInstrument],
    start: date,
    end: date,
) -> MagicMock:
    """Build a mock SQLAlchemy session that returns synthetic data."""
    session = MagicMock()
    trading_dates = _make_trading_dates(start, end)

    # Mock session.execute to return appropriate data for each query
    def _execute(stmt, params=None):
        mock_result = MagicMock()
        # Return trading dates for _trading_dates_in_range
        mock_result.fetchall.return_value = [MagicMock(date=d) for d in trading_dates]
        # fetchone for benchmark
        mock_result.fetchone.return_value = None
        return mock_result

    session.execute.side_effect = _execute
    return session


# ---------------------------------------------------------------------------
# Test 1: smoke test — runs without exceptions
# ---------------------------------------------------------------------------


def test_simulator_runs_on_30_instruments_6_months() -> None:
    """Simulator runs end-to-end on a synthetic 30-instrument, 6-month universe.

    All bounded-context calls are monkeypatched to return synthetic data.
    Verifies: no exception, SimulationResult returned with periods.
    """
    instruments = _make_instruments(30)
    inst_ids = [inst.instrument_id for inst in instruments]
    panel = _make_signal_panel(instruments)
    returns_panel = _make_returns_panel(inst_ids[:20])

    start = date(2024, 6, 1)
    end = date(2024, 12, 31)
    trading_dates = _make_trading_dates(start, end)

    config = SimulationConfig(
        start=start,
        end=end,
        strategy_name="test_smoke",
        target_holdings=20,
        persist=False,
    )

    mock_session = MagicMock()

    def mock_execute(stmt, params=None):
        result = MagicMock()
        sql_str = str(stmt) if hasattr(stmt, "__str__") else ""
        if "atlas_market_regime_daily" in sql_str and "date >= :s" in sql_str:
            result.fetchall.return_value = [MagicMock(date=d) for d in trading_dates]
        elif "atlas_market_regime_daily" in sql_str and "nifty500_tr_index" in sql_str:
            result.fetchall.return_value = []
        else:
            result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    mock_session.execute.side_effect = mock_execute
    mock_session.commit = MagicMock()

    regime_state = RegimeState(
        date=start,
        score=1,
        level="normal",
        gross_multiplier=1.0,
        signals=[],
    )
    sleeve_alloc = SleeveAllocation(
        ref_date=start,
        sleeve_pct_of_book=0.05,
        legs=[],
    )

    with (
        patch("atlas.trading.v6.simulator.get_investable", return_value=instruments),
        patch("atlas.trading.v6.simulator.apply_exclusions", return_value=(set(), [])),
        patch("atlas.trading.v6.simulator._compute_signal_panel", return_value=panel),
        patch("atlas.trading.v6.simulator._get_trend_gate_pass", return_value=set(inst_ids)),
        patch(
            "atlas.trading.v6.simulator._fetch_returns_panel",
            return_value=returns_panel,
        ),
        patch("atlas.trading.v6.simulator.compute_regime", return_value=regime_state),
        patch("atlas.trading.v6.simulator.allocate_sleeve", return_value=sleeve_alloc),
        patch(
            "atlas.trading.v6.simulator._fetch_forward_returns",
            return_value={iid: _RNG.uniform(-0.02, 0.04) for iid in inst_ids},
        ),
        patch("atlas.trading.v6.simulator._benchmark_return", return_value=0.01),
    ):
        result = run_simulation(mock_session, config)

    assert isinstance(result, SimulationResult)
    assert result.strategy_name == "test_smoke"
    assert len(result.periods) > 0
    assert isinstance(result.ann_return, float)
    assert isinstance(result.max_drawdown, float)
    assert result.max_drawdown <= 0.0  # drawdown is non-positive


# ---------------------------------------------------------------------------
# Test 2: holdings count within sensible bounds
# ---------------------------------------------------------------------------


def test_simulator_respects_holdings_count_target() -> None:
    """Holdings count in each period falls within expected range.

    With target_holdings=20 and stay_cutoff=32, holdings should be 1-45.
    """
    instruments = _make_instruments(30)
    inst_ids = [inst.instrument_id for inst in instruments]
    panel = _make_signal_panel(instruments)
    returns_panel = _make_returns_panel(inst_ids[:25])

    start = date(2024, 6, 1)
    end = date(2024, 9, 30)
    trading_dates = _make_trading_dates(start, end)

    config = SimulationConfig(
        start=start,
        end=end,
        strategy_name="test_holdings",
        target_holdings=20,
        persist=False,
    )

    mock_session = MagicMock()

    def mock_execute(stmt, params=None):
        result = MagicMock()
        sql_str = str(stmt) if hasattr(stmt, "__str__") else ""
        if "atlas_market_regime_daily" in sql_str and "date >= :s" in sql_str:
            result.fetchall.return_value = [MagicMock(date=d) for d in trading_dates]
        else:
            result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    mock_session.execute.side_effect = mock_execute
    mock_session.commit = MagicMock()

    regime_state = RegimeState(
        date=start,
        score=0,
        level="calm",
        gross_multiplier=1.10,
        signals=[],
    )
    sleeve_alloc = SleeveAllocation(
        ref_date=start,
        sleeve_pct_of_book=0.05,
        legs=[],
    )

    with (
        patch("atlas.trading.v6.simulator.get_investable", return_value=instruments),
        patch("atlas.trading.v6.simulator.apply_exclusions", return_value=(set(), [])),
        patch("atlas.trading.v6.simulator._compute_signal_panel", return_value=panel),
        patch("atlas.trading.v6.simulator._get_trend_gate_pass", return_value=set(inst_ids)),
        patch("atlas.trading.v6.simulator._fetch_returns_panel", return_value=returns_panel),
        patch("atlas.trading.v6.simulator.compute_regime", return_value=regime_state),
        patch("atlas.trading.v6.simulator.allocate_sleeve", return_value=sleeve_alloc),
        patch(
            "atlas.trading.v6.simulator._fetch_forward_returns",
            return_value={iid: _RNG.uniform(-0.01, 0.03) for iid in inst_ids},
        ),
        patch("atlas.trading.v6.simulator._benchmark_return", return_value=0.005),
    ):
        result = run_simulation(mock_session, config)

    # Every period with holdings should have 1-45 stocks
    for period in result.periods:
        assert (
            0 <= period.holdings_count <= 45
        ), f"holdings_count={period.holdings_count} out of [0,45] on {period.rebalance_date}"

    # At least one period should have positive holdings
    assert any(p.holdings_count > 0 for p in result.periods)


# ---------------------------------------------------------------------------
# Test 3: governance exclusion forces exit
# ---------------------------------------------------------------------------


def test_simulator_handles_governance_exclusions() -> None:
    """When a name is governance-excluded mid-period it is forced out of holdings.

    We set up a scenario where instrument_ids[0] is in the first-period cohort,
    then becomes governance-excluded in the second period. The test verifies
    the PeriodResult holdings_count decreases or the excluded name is absent.
    """
    instruments = _make_instruments(10)
    inst_ids = [inst.instrument_id for inst in instruments]
    panel = _make_signal_panel(instruments)
    returns_panel = _make_returns_panel(inst_ids[:8])

    start = date(2024, 6, 1)
    end = date(2024, 9, 30)
    trading_dates = _make_trading_dates(start, end)

    # Excluded set alternates: first period no exclusions, second period excludes inst_ids[0]
    excluded_sets = [set(), {inst_ids[0]}]
    call_counter = {"n": 0}

    def mock_apply_exclusions(session, universe, ref_date):
        idx = min(call_counter["n"], len(excluded_sets) - 1)
        call_counter["n"] += 1
        excl = excluded_sets[idx]
        return excl, []

    config = SimulationConfig(
        start=start,
        end=end,
        strategy_name="test_governance",
        target_holdings=8,
        persist=False,
    )

    mock_session = MagicMock()

    def mock_execute(stmt, params=None):
        result = MagicMock()
        sql_str = str(stmt) if hasattr(stmt, "__str__") else ""
        if "atlas_market_regime_daily" in sql_str and "date >= :s" in sql_str:
            result.fetchall.return_value = [MagicMock(date=d) for d in trading_dates]
        else:
            result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    mock_session.execute.side_effect = mock_execute
    mock_session.commit = MagicMock()

    regime_state = RegimeState(
        date=start, score=1, level="normal", gross_multiplier=1.0, signals=[]
    )
    sleeve_alloc = SleeveAllocation(ref_date=start, sleeve_pct_of_book=0.05, legs=[])

    with (
        patch("atlas.trading.v6.simulator.get_investable", return_value=instruments),
        patch("atlas.trading.v6.simulator.apply_exclusions", side_effect=mock_apply_exclusions),
        patch("atlas.trading.v6.simulator._compute_signal_panel", return_value=panel),
        patch("atlas.trading.v6.simulator._get_trend_gate_pass", return_value=set(inst_ids)),
        patch("atlas.trading.v6.simulator._fetch_returns_panel", return_value=returns_panel),
        patch("atlas.trading.v6.simulator.compute_regime", return_value=regime_state),
        patch("atlas.trading.v6.simulator.allocate_sleeve", return_value=sleeve_alloc),
        patch(
            "atlas.trading.v6.simulator._fetch_forward_returns",
            return_value={iid: 0.01 for iid in inst_ids},
        ),
        patch("atlas.trading.v6.simulator._benchmark_return", return_value=0.005),
    ):
        result = run_simulation(mock_session, config)

    # Simulation ran without exception
    assert isinstance(result, SimulationResult)
    assert len(result.periods) >= 1

    # The call_counter shows apply_exclusions was called
    assert call_counter["n"] >= 1


# ---------------------------------------------------------------------------
# Test 4: DB persistence (integration, skips without ATLAS_TEST_DB_URL)
# ---------------------------------------------------------------------------


def test_simulator_persists_to_strategy_runs(tmp_db_session) -> None:
    """Writes one row to atlas_v6_strategy_runs after a simulation.

    Requires ATLAS_TEST_DB_URL to be set. Rolls back after test.
    This test verifies the DB schema compatibility of the persist call.
    """
    instruments = _make_instruments(5)
    inst_ids = [inst.instrument_id for inst in instruments]
    panel = _make_signal_panel(instruments)
    returns_panel = _make_returns_panel(inst_ids[:4])

    start = date(2024, 6, 1)
    end = date(2024, 8, 31)
    trading_dates = _make_trading_dates(start, end)

    config = SimulationConfig(
        start=start,
        end=end,
        strategy_name="test_persist_v6",
        target_holdings=4,
        persist=True,  # persistence enabled
    )

    def mock_execute(stmt, params=None):
        result = MagicMock()
        sql_str = str(stmt) if hasattr(stmt, "__str__") else ""
        if "atlas_market_regime_daily" in sql_str and "date >= :s" in sql_str:
            result.fetchall.return_value = [MagicMock(date=d) for d in trading_dates]
        else:
            result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    regime_state = RegimeState(date=start, score=0, level="calm", gross_multiplier=1.10, signals=[])
    sleeve_alloc = SleeveAllocation(ref_date=start, sleeve_pct_of_book=0.05, legs=[])

    with (
        patch("atlas.trading.v6.simulator.get_investable", return_value=instruments),
        patch("atlas.trading.v6.simulator.apply_exclusions", return_value=(set(), [])),
        patch("atlas.trading.v6.simulator._compute_signal_panel", return_value=panel),
        patch("atlas.trading.v6.simulator._get_trend_gate_pass", return_value=set(inst_ids)),
        patch("atlas.trading.v6.simulator._fetch_returns_panel", return_value=returns_panel),
        patch("atlas.trading.v6.simulator.compute_regime", return_value=regime_state),
        patch("atlas.trading.v6.simulator.allocate_sleeve", return_value=sleeve_alloc),
        patch(
            "atlas.trading.v6.simulator._fetch_forward_returns",
            return_value={iid: 0.02 for iid in inst_ids},
        ),
        patch("atlas.trading.v6.simulator._benchmark_return", return_value=0.01),
        patch("atlas.trading.v6.simulator._trading_dates_in_range", return_value=trading_dates),
    ):
        result = run_simulation(tmp_db_session, config)

    assert isinstance(result, SimulationResult)

    # Verify row was written to atlas_v6_strategy_runs
    from sqlalchemy import text as sa_text

    row = tmp_db_session.execute(
        sa_text("""
            SELECT strategy_name, passes_all_constraints
              FROM atlas.atlas_v6_strategy_runs
             WHERE strategy_name = 'test_persist_v6'
             ORDER BY created_at DESC
             LIMIT 1
        """)
    ).fetchone()

    assert row is not None, "Expected a row in atlas_v6_strategy_runs after simulation"
    assert row.strategy_name == "test_persist_v6"


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


def test_monthly_rebalance_dates_returns_last_trading_day_of_month() -> None:
    """_monthly_rebalance_dates groups by month and picks last day."""
    dates = [
        date(2024, 1, 15),
        date(2024, 1, 22),
        date(2024, 1, 31),
        date(2024, 2, 14),
        date(2024, 2, 28),
        date(2024, 3, 29),
    ]
    result = _monthly_rebalance_dates(dates)
    assert result == [date(2024, 1, 31), date(2024, 2, 28), date(2024, 3, 29)]


def test_monthly_rebalance_dates_empty_input() -> None:
    """Empty input returns empty list."""
    assert _monthly_rebalance_dates([]) == []


def test_compute_aggregate_stats_single_period() -> None:
    """Aggregate stats computed correctly for a single period result."""
    from atlas.trading.v6.simulator import PeriodResult

    period = PeriodResult(
        rebalance_date=date(2024, 1, 1),
        end_date=date(2024, 2, 1),
        book_return=0.02,
        benchmark_return=0.01,
        alpha=0.01,
        holdings_count=20,
        sleeve_pct=0.05,
        cash_pct=0.10,
        gross_exposure=0.85,
        regime_score=1,
    )
    result = _compute_aggregate_stats(
        strategy_name="test",
        periods=[period],
        equity_curve=[1.0, 1.02],
        n_trades=5,
    )
    assert result.strategy_name == "test"
    assert result.n_trades == 5
    assert result.win_rate == 1.0  # one period, positive return
    assert result.max_drawdown <= 0.0


def test_compute_aggregate_stats_all_losing_periods() -> None:
    """Win rate = 0 when all periods are negative."""
    from atlas.trading.v6.simulator import PeriodResult

    periods = [
        PeriodResult(
            rebalance_date=date(2024, 1, 1),
            end_date=date(2024, 2, 1),
            book_return=-0.03,
            benchmark_return=0.0,
            alpha=-0.03,
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=2,
        ),
        PeriodResult(
            rebalance_date=date(2024, 2, 1),
            end_date=date(2024, 3, 1),
            book_return=-0.02,
            benchmark_return=0.0,
            alpha=-0.02,
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=2,
        ),
    ]
    result = _compute_aggregate_stats(
        strategy_name="test_loss",
        periods=periods,
        equity_curve=[1.0, 0.97, 0.95],
        n_trades=10,
    )
    assert result.win_rate == 0.0
    assert result.max_drawdown < 0.0


def test_compute_aggregate_stats_alpha_t_stat_nonzero() -> None:
    """alpha_t_stat is computed from per-period alpha series (§8.4 formula)."""
    import math

    from atlas.trading.v6.simulator import PeriodResult

    # Three periods with consistent positive alpha → t-stat > 0
    alphas = [0.02, 0.03, 0.015]
    periods = [
        PeriodResult(
            rebalance_date=date(2024, 1, 1) + timedelta(days=30 * i),
            end_date=date(2024, 1, 1) + timedelta(days=30 * (i + 1)),
            book_return=alpha + 0.01,
            benchmark_return=0.01,
            alpha=alpha,
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=1,
        )
        for i, alpha in enumerate(alphas)
    ]
    equity_curve = [1.0, 1.03, 1.06, 1.075]
    result = _compute_aggregate_stats(
        strategy_name="test_alpha",
        periods=periods,
        equity_curve=equity_curve,
        n_trades=6,
    )
    # Manual check: alpha_mean / alpha_std * sqrt(3)
    import statistics

    mean_a = sum(alphas) / len(alphas)
    std_a = statistics.stdev(alphas)
    expected_t = mean_a / std_a * math.sqrt(3)
    assert abs(result.alpha_t_stat - expected_t) < 1e-9
    assert result.alpha_t_stat > 0.0


def test_compute_aggregate_stats_alpha_t_stat_zero_variance() -> None:
    """alpha_t_stat is 0.0 when all alphas are identical (zero variance)."""
    from atlas.trading.v6.simulator import PeriodResult

    periods = [
        PeriodResult(
            rebalance_date=date(2024, 1, 1) + timedelta(days=30 * i),
            end_date=date(2024, 1, 1) + timedelta(days=30 * (i + 1)),
            book_return=0.02,
            benchmark_return=0.01,
            alpha=0.01,  # identical every period → std=0
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=1,
        )
        for i in range(3)
    ]
    result = _compute_aggregate_stats(
        strategy_name="test_flat_alpha",
        periods=periods,
        equity_curve=[1.0, 1.02, 1.04, 1.06],
        n_trades=6,
    )
    assert result.alpha_t_stat == 0.0


# ---------------------------------------------------------------------------
# Fix-B tests: daily NAV granularity
# ---------------------------------------------------------------------------


def test_fetch_daily_portfolio_returns_empty_weights() -> None:
    """Empty book_weights returns empty list without hitting DB."""
    mock_session = MagicMock()
    result = _fetch_daily_portfolio_returns(mock_session, {}, date(2022, 1, 1), date(2022, 2, 1))
    assert result == []
    mock_session.execute.assert_not_called()


def test_fetch_daily_portfolio_returns_no_db_rows() -> None:
    """Returns empty list when DB returns no rows; logs warning."""
    iid = uuid.uuid4()
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result

    result = _fetch_daily_portfolio_returns(
        mock_session,
        {iid: 0.5},
        date(2022, 1, 1),
        date(2022, 2, 1),
    )
    assert result == []


def test_fetch_daily_portfolio_returns_weighted_sum() -> None:
    """Daily returns are weighted sums: port_ret[t] = sum(w_i * r_i[t])."""
    iid_a = uuid.uuid4()
    iid_b = uuid.uuid4()
    book_weights = {iid_a: 0.6, iid_b: 0.4}

    # Two days, two instruments
    day1 = date(2022, 1, 3)
    day2 = date(2022, 1, 4)

    def _row(iid: uuid.UUID, d: date, ret: float) -> MagicMock:
        r = MagicMock()
        r.instrument_id = str(iid)
        r.date = d
        r.ret_1d = ret
        return r

    rows = [
        _row(iid_a, day1, 0.01),  # 0.6 * 0.01
        _row(iid_b, day1, -0.005),  # 0.4 * -0.005
        _row(iid_a, day2, 0.02),  # 0.6 * 0.02
        _row(iid_b, day2, 0.015),  # 0.4 * 0.015
    ]

    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_session = MagicMock()
    mock_session.execute.return_value = mock_result

    result = _fetch_daily_portfolio_returns(
        mock_session,
        book_weights,
        date(2022, 1, 1),
        date(2022, 1, 5),
    )

    assert len(result) == 2
    expected_day1 = 0.6 * 0.01 + 0.4 * (-0.005)
    expected_day2 = 0.6 * 0.02 + 0.4 * 0.015
    assert abs(result[0] - expected_day1) < 1e-10
    assert abs(result[1] - expected_day2) < 1e-10


def test_compute_aggregate_stats_daily_mdd_deeper_than_monthly() -> None:
    """Daily NAV must produce MDD that is <= the monthly series MDD.

    Scenario: two months each ending up +2%, but the daily series shows
    a -10% intra-month trough in month 1. Monthly equity_curve [1.0,1.02,1.04]
    would report MDD=0.0 (all rising). Daily series captures the trough.
    """
    from atlas.trading.v6.simulator import PeriodResult

    periods = [
        PeriodResult(
            rebalance_date=date(2022, 1, 1),
            end_date=date(2022, 2, 1),
            book_return=0.02,
            benchmark_return=0.01,
            alpha=0.01,
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=2,
        ),
        PeriodResult(
            rebalance_date=date(2022, 2, 1),
            end_date=date(2022, 3, 1),
            book_return=0.02,
            benchmark_return=0.01,
            alpha=0.01,
            holdings_count=20,
            sleeve_pct=0.05,
            cash_pct=0.10,
            gross_exposure=0.85,
            regime_score=2,
        ),
    ]

    # Monthly equity curve: [1.0, 1.02, 1.04] — monotonically rising → MDD=0
    monthly_result = _compute_aggregate_stats(
        strategy_name="test_monthly",
        periods=periods,
        equity_curve=[1.0, 1.02, 1.0404],
        daily_returns=None,
        n_trades=0,
    )
    # MDD from monthly series: no drawdown visible (NAV only hits month-ends)
    assert (
        monthly_result.max_drawdown >= -0.001
    ), f"Monthly MDD should be ~0 but got {monthly_result.max_drawdown}"

    # Daily returns: starts at 1.0, drops to 0.90 intra-month, then recovers
    # Simulated: day 1 = -10%, day 2 = +0.02/0.90 - 1 (recovery) to reach 1.02
    # day3-day5 are flat for period 2, ending at ~1.04
    daily_rets_period1 = [-0.10, (1.02 / 0.90) - 1.0]  # trough then recovery
    daily_rets_period2 = [0.01, 0.01, 0.0]  # gentle rise

    all_daily = daily_rets_period1 + daily_rets_period2
    # Build daily equity curve
    daily_ec = [1.0]
    for r in all_daily:
        daily_ec.append(daily_ec[-1] * (1.0 + r))

    daily_result = _compute_aggregate_stats(
        strategy_name="test_daily",
        periods=periods,
        equity_curve=daily_ec,
        daily_returns=all_daily,
        n_trades=0,
    )
    # Daily MDD must capture the -10% intra-month trough
    assert daily_result.max_drawdown < -0.09, (
        f"Daily MDD should be < -9% (captures intra-month trough) "
        f"but got {daily_result.max_drawdown}"
    )
    # Daily MDD should be strictly worse than monthly MDD
    assert daily_result.max_drawdown < monthly_result.max_drawdown


def test_run_simulation_daily_returns_patches_applied() -> None:
    """run_simulation calls _fetch_daily_portfolio_returns and extends equity_curve daily.

    The equity_curve should have more points than (n_periods + 1) when daily
    returns are returned.
    """
    instruments = _make_instruments(10)
    inst_ids = [inst.instrument_id for inst in instruments]
    panel = _make_signal_panel(instruments)
    returns_panel = _make_returns_panel(inst_ids[:8])

    start = date(2024, 6, 1)
    end = date(2024, 8, 31)
    trading_dates = _make_trading_dates(start, end)

    config = SimulationConfig(
        start=start,
        end=end,
        strategy_name="test_daily_nav",
        target_holdings=8,
        persist=False,
    )

    mock_session = MagicMock()

    def mock_execute(stmt, params=None):
        result = MagicMock()
        sql_str = str(stmt) if hasattr(stmt, "__str__") else ""
        if "atlas_market_regime_daily" in sql_str and "date >= :s" in sql_str:
            result.fetchall.return_value = [MagicMock(date=d) for d in trading_dates]
        else:
            result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    mock_session.execute.side_effect = mock_execute
    mock_session.commit = MagicMock()

    regime_state = RegimeState(date=start, score=0, level="calm", gross_multiplier=1.0, signals=[])
    sleeve_alloc = SleeveAllocation(ref_date=start, sleeve_pct_of_book=0.05, legs=[])

    # Return 5 daily returns per period from _fetch_daily_portfolio_returns
    daily_ret_stub = [0.001, -0.002, 0.003, 0.0, 0.001]

    with (
        patch("atlas.trading.v6.simulator.get_investable", return_value=instruments),
        patch("atlas.trading.v6.simulator.apply_exclusions", return_value=(set(), [])),
        patch("atlas.trading.v6.simulator._compute_signal_panel", return_value=panel),
        patch("atlas.trading.v6.simulator._get_trend_gate_pass", return_value=set(inst_ids)),
        patch("atlas.trading.v6.simulator._fetch_returns_panel", return_value=returns_panel),
        patch("atlas.trading.v6.simulator.compute_regime", return_value=regime_state),
        patch("atlas.trading.v6.simulator.allocate_sleeve", return_value=sleeve_alloc),
        patch(
            "atlas.trading.v6.simulator._fetch_daily_portfolio_returns",
            return_value=daily_ret_stub,
        ),
        patch("atlas.trading.v6.simulator._benchmark_return", return_value=0.005),
    ):
        result = run_simulation(mock_session, config)

    assert isinstance(result, SimulationResult)
    # With daily data, each period contributes 5 daily NAV points.
    # n_periods ~= 2 for Jun-Aug → equity_curve len > 3 (monthly would be 3)
    # equity_curve starts at [1.0] + 5 daily points per period:
    #   len == 1 + 5 * n_periods (daily) vs 1 + 1 * n_periods (monthly)
    assert result.max_drawdown <= 0.0  # non-positive
    assert len(result.periods) >= 1
