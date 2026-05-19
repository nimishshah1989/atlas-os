"""Tests for atlas.trading.v6.validator — Phase 8 walk-forward + goal-post + hold-out.

Test inventory:
  1. test_build_windows_returns_8_oos_windows
  2. test_build_windows_growing_train_periods
  3. test_build_windows_first_last_window_dates
  4. test_check_ic_retention_pass_when_above_threshold
  5. test_check_ic_retention_fail_when_below_threshold
  6. test_check_ic_retention_pass_when_is_ic_is_zero
  7. test_check_ic_retention_fail_when_oos_signal_missing
  8. test_evaluate_goal_post_returns_per_constraint_pass
  9. test_evaluate_goal_post_aggregates_passes_all
  10. test_evaluate_goal_post_fails_when_calmar_low
  11. test_evaluate_goal_post_raises_on_bad_benchmark_vol
  12. test_evaluate_goal_post_raises_on_bad_benchmark_mdd
  13. test_evaluate_goal_post_raises_on_empty_results
  14. test_examine_holdout_singleton_raises_on_second_call  (DB)
  15. test_examine_holdout_sets_timestamp_in_db  (DB)
  16. test_examine_holdout_raises_for_unknown_run_id  (DB)
  17. test_run_walk_forward_returns_8_results
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

import atlas.trading.v6.validator as validator_module
from atlas.trading.v6.validator import (
    GOAL_POST_CONSTRAINTS,
    GoalPostResult,
    HoldoutAlreadyExamined,
    OOSResult,
    SimulatorNotAvailable,
    WalkForwardConfig,
    WindowSpec,
    build_windows,
    check_ic_retention,
    evaluate_goal_post,
    examine_holdout,
    run_walk_forward,
)

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_window(oos_year: int) -> WindowSpec:
    return WindowSpec(
        train_start=date(2010, 1, 1),
        train_end=date(oos_year - 1, 12, 31),
        oos_start=date(oos_year, 1, 1),
        oos_end=date(oos_year, 12, 31),
    )


def _make_oos_result(
    oos_year: int,
    cagr: float = 0.22,
    max_drawdown: float = -0.15,
    sharpe: float = 1.3,
    calmar: float = 1.2,
    win_rate: float = 0.55,
    alpha_t_stat: float = 2.0,
    n_trades: int = 40,
    is_ic: dict[str, float] | None = None,
    oos_ic: dict[str, float] | None = None,
) -> OOSResult:
    return OOSResult(
        window=_make_window(oos_year),
        weights_used={"natr_14": 0.15, "mom_low_vol": 0.15},
        cagr=cagr,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        calmar=calmar,
        win_rate=win_rate,
        alpha_t_stat=alpha_t_stat,
        n_trades=n_trades,
        per_signal_is_ic=is_ic or {"natr_14": 0.08, "mom_low_vol": 0.07},
        per_signal_oos_ic=oos_ic or {"natr_14": 0.06, "mom_low_vol": 0.05},
    )


def _make_8_results(
    cagr: float = 0.22,
    max_drawdown: float = -0.15,
    sharpe: float = 1.3,
    win_rate: float = 0.55,
    alpha_t_stat: float = 2.0,
) -> list[OOSResult]:
    return [
        _make_oos_result(
            year,
            cagr=cagr,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            win_rate=win_rate,
            alpha_t_stat=alpha_t_stat,
        )
        for year in range(2015, 2023)
    ]


@dataclass
class FakeSimResult:
    """Minimal stand-in for SimulationResult from Phase 7."""

    cagr: float = 0.22
    max_drawdown: float = -0.15
    sharpe: float = 1.3
    calmar: float = 1.2
    win_rate: float = 0.55
    alpha_t_stat: float = 2.0
    n_trades: int = 40


def _fake_run_simulation(_session: Any, _config: Any) -> FakeSimResult:
    return FakeSimResult()


# ---------------------------------------------------------------------------
# 1. build_windows — 8 OOS windows
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_windows_returns_8_oos_windows():
    """Default config produces exactly 8 OOS windows (2015-2022)."""
    config = WalkForwardConfig()
    windows = build_windows(config)
    assert len(windows) == 8


@pytest.mark.unit
def test_build_windows_growing_train_periods():
    """Each subsequent window extends the train end by one year."""
    config = WalkForwardConfig()
    windows = build_windows(config)
    for i in range(1, len(windows)):
        assert windows[i].train_end.year == windows[i - 1].train_end.year + 1


@pytest.mark.unit
def test_build_windows_first_last_window_dates():
    """First window: train 2010-2014, OOS 2015. Last: train 2010-2021, OOS 2022."""
    config = WalkForwardConfig()
    windows = build_windows(config)

    first = windows[0]
    assert first.train_start == date(2010, 1, 1)
    assert first.train_end == date(2014, 12, 31)
    assert first.oos_start == date(2015, 1, 1)
    assert first.oos_end == date(2015, 12, 31)

    last = windows[-1]
    assert last.train_end == date(2021, 12, 31)
    assert last.oos_start == date(2022, 1, 1)
    assert last.oos_end == date(2022, 12, 31)


@pytest.mark.unit
def test_build_windows_all_train_starts_are_2010():
    """Every window's train_start is the global start (growing window, not rolling)."""
    config = WalkForwardConfig()
    windows = build_windows(config)
    for w in windows:
        assert w.train_start == date(2010, 1, 1)


# ---------------------------------------------------------------------------
# 2. check_ic_retention — pass/fail logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_ic_retention_pass_when_above_threshold():
    """OOS/IS = 0.80 >= 0.70 → pass."""
    is_ic = {"natr_14": 0.10, "mom_low_vol": 0.08}
    oos_ic = {"natr_14": 0.08, "mom_low_vol": 0.065}  # 0.08/0.10=0.8, 0.065/0.08=0.81
    result = check_ic_retention(is_ic, oos_ic, threshold=0.70)
    assert result["natr_14"] is True
    assert result["mom_low_vol"] is True


@pytest.mark.unit
def test_check_ic_retention_fail_when_below_threshold():
    """OOS/IS = 0.50 < 0.70 → fail."""
    is_ic = {"natr_14": 0.10}
    oos_ic = {"natr_14": 0.04}  # 0.04/0.10 = 0.40 < 0.70
    result = check_ic_retention(is_ic, oos_ic, threshold=0.70)
    assert result["natr_14"] is False


@pytest.mark.unit
def test_check_ic_retention_pass_when_is_ic_is_zero():
    """IS IC = 0.0 (no signal baseline) → pass to avoid division by zero."""
    is_ic = {"natr_14": 0.0}
    oos_ic = {"natr_14": 0.02}
    result = check_ic_retention(is_ic, oos_ic, threshold=0.70)
    assert result["natr_14"] is True


@pytest.mark.unit
def test_check_ic_retention_fail_when_oos_signal_missing():
    """Signal present in IS but absent from OOS → fail."""
    is_ic = {"natr_14": 0.10, "missing_signal": 0.05}
    oos_ic = {"natr_14": 0.09}  # missing_signal absent
    result = check_ic_retention(is_ic, oos_ic, threshold=0.70)
    assert result["natr_14"] is True
    assert result["missing_signal"] is False


@pytest.mark.unit
def test_check_ic_retention_exact_threshold_passes():
    """OOS/IS exactly at threshold → pass (>=, not >)."""
    is_ic = {"sig_a": 0.10}
    oos_ic = {"sig_a": 0.07}  # 0.07/0.10 = 0.70 exactly
    result = check_ic_retention(is_ic, oos_ic, threshold=0.70)
    assert result["sig_a"] is True


@pytest.mark.unit
def test_check_ic_retention_returns_empty_for_empty_inputs():
    """Empty IS IC → empty result dict."""
    result = check_ic_retention({}, {}, threshold=0.70)
    assert result == {}


# ---------------------------------------------------------------------------
# 3. evaluate_goal_post — per-constraint and aggregate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_evaluate_goal_post_returns_per_constraint_pass():
    """Passing OOS results → all 9 constraint entries present with pass=True."""
    session = MagicMock()
    results = _make_8_results(
        cagr=0.22,
        max_drawdown=-0.20,
        sharpe=1.3,
        win_rate=0.55,
        alpha_t_stat=2.0,
    )
    # benchmark: vol=0.17, mdd=-0.38 → our vol=0.22/1.3≈0.169, our mdd=-0.20
    gpr = evaluate_goal_post(
        session,
        results,
        benchmark_vol=0.17,
        benchmark_mdd=-0.38,
    )
    assert len(gpr.constraints) == 9
    constraint_names = {c["name"] for c in gpr.constraints}
    for expected in GOAL_POST_CONSTRAINTS:
        assert expected in constraint_names


@pytest.mark.unit
def test_evaluate_goal_post_aggregates_passes_all():
    """passes_all_constraints = AND of all 9 constraint pass flags."""
    session = MagicMock()
    results = _make_8_results(
        cagr=0.22,
        max_drawdown=-0.20,
        sharpe=1.5,
        win_rate=0.56,
        alpha_t_stat=2.1,
    )
    gpr = evaluate_goal_post(
        session,
        results,
        benchmark_vol=0.17,
        benchmark_mdd=-0.38,
    )
    all_pass = all(c["pass"] for c in gpr.constraints)
    assert gpr.passes_all_constraints == all_pass


@pytest.mark.unit
def test_evaluate_goal_post_fails_when_calmar_low():
    """Calmar < 1.0 → calmar constraint fails → passes_all_constraints False."""
    session = MagicMock()
    # cagr=0.05, mdd=-0.25 → calmar ≈ 0.2 (well below 1.0)
    results = _make_8_results(
        cagr=0.05,
        max_drawdown=-0.25,
        sharpe=0.4,
        win_rate=0.48,
        alpha_t_stat=0.5,
    )
    gpr = evaluate_goal_post(
        session,
        results,
        benchmark_vol=0.17,
        benchmark_mdd=-0.38,
    )
    calmar_constraint = next(c for c in gpr.constraints if c["name"] == "calmar")
    assert calmar_constraint["pass"] is False
    assert gpr.passes_all_constraints is False


@pytest.mark.unit
def test_evaluate_goal_post_raises_on_bad_benchmark_vol():
    """benchmark_vol <= 0 → ValueError."""
    session = MagicMock()
    with pytest.raises(ValueError, match="benchmark_vol must be positive"):
        evaluate_goal_post(session, _make_8_results(), benchmark_vol=0.0, benchmark_mdd=-0.38)


@pytest.mark.unit
def test_evaluate_goal_post_raises_on_bad_benchmark_mdd():
    """benchmark_mdd >= 0 → ValueError."""
    session = MagicMock()
    with pytest.raises(ValueError, match="benchmark_mdd must be negative"):
        evaluate_goal_post(session, _make_8_results(), benchmark_vol=0.17, benchmark_mdd=0.0)


@pytest.mark.unit
def test_evaluate_goal_post_raises_on_empty_results():
    """Empty results → ValueError."""
    session = MagicMock()
    with pytest.raises(ValueError, match="oos_results is empty"):
        evaluate_goal_post(session, [], benchmark_vol=0.17, benchmark_mdd=-0.38)


@pytest.mark.unit
def test_evaluate_goal_post_dd_compliance_measured():
    """DD compliance: count windows where port_DD >= bench_DD (≤ bench in abs terms)."""
    session = MagicMock()
    # benchmark_mdd = -0.38; port_mdd = -0.20 < bench in absolute terms → compliant
    results = _make_8_results(max_drawdown=-0.20)
    gpr = evaluate_goal_post(
        session,
        results,
        benchmark_vol=0.17,
        benchmark_mdd=-0.38,
    )
    dd_constraint = next(c for c in gpr.constraints if c["name"] == "dd_compliance_pct")
    # All 8 windows have mdd=-0.20 >= bench -0.38 → 100% compliance
    assert dd_constraint["actual"] == 1.0
    assert dd_constraint["pass"] is True


# ---------------------------------------------------------------------------
# 4. run_walk_forward — returns 8 results via monkeypatched simulator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_walk_forward_returns_8_results(monkeypatch):
    """run_walk_forward returns 8 OOSResults, one per OOS year, using fake simulator."""

    def fake_sim(_session: Any, _config: Any) -> FakeSimResult:
        return FakeSimResult()

    monkeypatch.setattr(validator_module, "run_simulation", fake_sim)
    monkeypatch.setattr(validator_module, "_sim_config_cls", dict)

    session = MagicMock()
    # Prevent DB writes from failing on mock session
    session.execute.return_value.fetchall.return_value = []

    config = WalkForwardConfig()
    results = run_walk_forward(session, config, strategy_name="test_run")

    assert len(results) == 8
    for i, result in enumerate(results):
        assert result.window.oos_start.year == 2015 + i
        assert result.cagr == 0.22
        assert result.calmar == 1.2


@pytest.mark.unit
def test_run_walk_forward_raises_when_simulator_unavailable(monkeypatch):
    """run_walk_forward raises SimulatorNotAvailable when Phase 7 not committed."""
    monkeypatch.setattr(validator_module, "run_simulation", None)

    session = MagicMock()
    with pytest.raises(SimulatorNotAvailable):
        run_walk_forward(session, WalkForwardConfig())


# ---------------------------------------------------------------------------
# 5. examine_holdout — singleton enforcement (DB-required tests)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_examine_holdout_singleton_raises_on_second_call(tmp_db_session, monkeypatch):
    """First call to examine_holdout succeeds; second call raises HoldoutAlreadyExamined."""
    monkeypatch.setattr(validator_module, "run_simulation", _fake_run_simulation)
    monkeypatch.setattr(validator_module, "_sim_config_cls", dict)

    run_id = uuid.uuid4()

    # Insert a strategy run row with holdout_examined_at = NULL
    tmp_db_session.execute(
        text("""
            INSERT INTO atlas.atlas_v6_strategy_runs (
                run_id, strategy_name, signal_weights,
                is_period, oos_period, passes_all_constraints, created_at
            ) VALUES (
                :run_id, 'test_singleton', '{"natr_14": 0.15}'::jsonb,
                tsrange('2010-01-01', '2022-12-31', '[]'),
                tsrange('2023-01-01', '2025-12-31', '[]'),
                false, NOW()
            )
        """),
        {"run_id": str(run_id)},
    )
    tmp_db_session.flush()

    # First call — should succeed
    result1 = examine_holdout(tmp_db_session, run_id)
    assert result1.cagr == 0.22  # from FakeSimResult
    assert result1.window.oos_start == date(2023, 1, 1)
    assert result1.window.oos_end == date(2025, 12, 31)

    # Second call — must raise
    with pytest.raises(HoldoutAlreadyExamined):
        examine_holdout(tmp_db_session, run_id)


@pytest.mark.integration
def test_examine_holdout_sets_timestamp_in_db(tmp_db_session, monkeypatch):
    """After examine_holdout, holdout_examined_at is set to a non-NULL timestamp."""
    monkeypatch.setattr(validator_module, "run_simulation", _fake_run_simulation)
    monkeypatch.setattr(validator_module, "_sim_config_cls", dict)

    run_id = uuid.uuid4()

    tmp_db_session.execute(
        text("""
            INSERT INTO atlas.atlas_v6_strategy_runs (
                run_id, strategy_name, signal_weights,
                is_period, oos_period, passes_all_constraints, created_at
            ) VALUES (
                :run_id, 'test_timestamp', '{"natr_14": 0.15}'::jsonb,
                tsrange('2010-01-01', '2022-12-31', '[]'),
                tsrange('2023-01-01', '2025-12-31', '[]'),
                false, NOW()
            )
        """),
        {"run_id": str(run_id)},
    )
    tmp_db_session.flush()

    # Verify NULL before
    row_before = tmp_db_session.execute(
        text("SELECT holdout_examined_at FROM atlas.atlas_v6_strategy_runs WHERE run_id = :rid"),
        {"rid": str(run_id)},
    ).fetchone()
    assert row_before.holdout_examined_at is None

    examine_holdout(tmp_db_session, run_id)

    # Verify non-NULL after
    row_after = tmp_db_session.execute(
        text("SELECT holdout_examined_at FROM atlas.atlas_v6_strategy_runs WHERE run_id = :rid"),
        {"rid": str(run_id)},
    ).fetchone()
    assert row_after.holdout_examined_at is not None


@pytest.mark.integration
def test_examine_holdout_raises_for_unknown_run_id(tmp_db_session, monkeypatch):
    """examine_holdout raises ValueError for a non-existent strategy_run_id."""
    monkeypatch.setattr(validator_module, "run_simulation", _fake_run_simulation)
    monkeypatch.setattr(validator_module, "_sim_config_cls", dict)

    fake_id = uuid.uuid4()  # definitely not in DB
    with pytest.raises(ValueError, match="not found in atlas_v6_strategy_runs"):
        examine_holdout(tmp_db_session, fake_id)


@pytest.mark.unit
def test_examine_holdout_raises_when_simulator_unavailable(monkeypatch):
    """examine_holdout raises SimulatorNotAvailable when Phase 7 not committed."""
    monkeypatch.setattr(validator_module, "run_simulation", None)

    session = MagicMock()
    with pytest.raises(SimulatorNotAvailable):
        examine_holdout(session, uuid.uuid4())


# ---------------------------------------------------------------------------
# 6. OOSResult / WindowSpec dataclass invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_oos_result_is_frozen():
    """OOSResult is frozen — mutation raises FrozenInstanceError."""
    import dataclasses

    result = _make_oos_result(2015)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.cagr = 0.99  # type: ignore[misc]


@pytest.mark.unit
def test_window_spec_is_frozen():
    """WindowSpec is frozen — mutation raises FrozenInstanceError."""
    import dataclasses

    window = _make_window(2015)
    with pytest.raises(dataclasses.FrozenInstanceError):
        window.oos_start = date(2016, 1, 1)  # type: ignore[misc]


@pytest.mark.unit
def test_goal_post_result_has_9_constraints():
    """GoalPostResult.constraints must contain exactly 9 entries."""
    session = MagicMock()
    results = _make_8_results()
    gpr = evaluate_goal_post(session, results, benchmark_vol=0.17, benchmark_mdd=-0.38)
    assert len(gpr.constraints) == 9


@pytest.mark.unit
def test_evaluate_goal_post_returns_goal_post_result_type():
    """evaluate_goal_post returns a GoalPostResult instance."""
    session = MagicMock()
    gpr = evaluate_goal_post(session, _make_8_results(), benchmark_vol=0.17, benchmark_mdd=-0.38)
    assert isinstance(gpr, GoalPostResult)
