"""Tests for atlas.trading.v6.optimizer — Phase 10 Bayesian shrinkage.

Test naming: test_<function>_<scenario>_<expected>

Coverage targets
----------------
1. test_bayesian_shrinkage_pulls_toward_prior          — high lambda → output ≈ prior
2. test_bayesian_shrinkage_pulls_toward_observed       — low lambda → output ≈ observed IC
3. test_generate_candidate_grid_produces_7             — 7 lambdas → 7 candidates
4. test_estimate_signal_ic_handles_empty_runs          — empty DB → uniform IC
5. test_persist_best_weights_writes_atlas_signal_weights — DB integration (skip without DB)
6. test_bayesian_shrinkage_lambda_zero_equals_normalized_observed
7. test_bayesian_shrinkage_lambda_one_equals_prior
8. test_generate_candidate_grid_custom_lambdas
9. test_candidate_weights_shrinkage_lambda_stored_correctly
10. test_bayesian_shrinkage_raises_on_invalid_lambda
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from atlas.trading.v6.composite import SignalWeights
from atlas.trading.v6.optimizer import (
    _SIGNALS,
    _V6_REGIME,
    _V6_TIER,
    CandidateWeights,
    bayesian_shrinkage_weights,
    estimate_signal_ic_from_strategy_runs,
    generate_candidate_grid,
    persist_best_weights,
    rank_candidates,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def uniform_ic() -> dict[str, float]:
    """Uniform IC — all signals equal."""
    return {s: 1.0 for s in _SIGNALS}


@pytest.fixture
def biased_ic() -> dict[str, float]:
    """IC strongly biased toward natr_14."""
    d = {s: 0.1 for s in _SIGNALS}
    d["natr_14"] = 10.0  # dominant signal
    return d


@pytest.fixture
def default_prior() -> SignalWeights:
    return SignalWeights()


# ---------------------------------------------------------------------------
# 1. test_bayesian_shrinkage_pulls_toward_prior
# ---------------------------------------------------------------------------


def test_bayesian_shrinkage_pulls_toward_prior(biased_ic, default_prior):
    """High lambda → output should be close to the prior weights, not dominated by IC."""
    result = bayesian_shrinkage_weights(biased_ic, default_prior, shrinkage_lambda=0.99)
    prior_dict = default_prior.normalized()
    result_dict = result.normalized()

    # With lambda=0.99, the output should be very close to prior
    for sig in _SIGNALS:
        assert abs(result_dict[sig] - prior_dict[sig]) < 0.02, (
            f"Signal {sig}: result={result_dict[sig]:.4f}, prior={prior_dict[sig]:.4f} "
            f"— expected near prior with lambda=0.99"
        )


# ---------------------------------------------------------------------------
# 2. test_bayesian_shrinkage_pulls_toward_observed
# ---------------------------------------------------------------------------


def test_bayesian_shrinkage_pulls_toward_observed(biased_ic, default_prior):
    """Low lambda → natr_14 should dominate output because IC is biased toward it."""
    result = bayesian_shrinkage_weights(biased_ic, default_prior, shrinkage_lambda=0.01)
    result_dict = result.normalized()

    # natr_14 IC is 10x others → its normalized IC weight is ~50% of total
    # At lambda=0.01, result should be close to normalized IC
    # Result weight for natr_14 should be significantly above prior (0.15)
    assert result_dict["natr_14"] > 0.40, (
        f"Expected natr_14 weight > 0.40 (IC-driven) at lambda=0.01, "
        f"got {result_dict['natr_14']:.4f}"
    )


# ---------------------------------------------------------------------------
# 3. test_generate_candidate_grid_produces_7
# ---------------------------------------------------------------------------


def test_generate_candidate_grid_produces_7(uniform_ic, default_prior):
    """Default 7 lambdas → exactly 7 candidates."""
    candidates = generate_candidate_grid(uniform_ic, default_prior)
    assert len(candidates) == 7, f"Expected 7 candidates, got {len(candidates)}"


# ---------------------------------------------------------------------------
# 4. test_estimate_signal_ic_handles_empty_runs
# ---------------------------------------------------------------------------


def test_estimate_signal_ic_handles_empty_runs():
    """Empty DB result → returns uniform IC dict (all values 1.0)."""
    mock_session = MagicMock()
    mock_session.execute.return_value.fetchall.return_value = []

    result = estimate_signal_ic_from_strategy_runs(mock_session)

    assert set(result.keys()) == set(_SIGNALS), "Should return all signal names"
    for sig in _SIGNALS:
        assert result[sig] == 1.0, f"Signal {sig} should be 1.0 in uniform IC, got {result[sig]}"


# ---------------------------------------------------------------------------
# 5. test_persist_best_weights_writes_atlas_signal_weights (DB integration)
# ---------------------------------------------------------------------------


def test_persist_best_weights_writes_atlas_signal_weights(tmp_db_session):
    """DB integration: persist_best_weights writes one row per signal to atlas_signal_weights."""
    pytest.importorskip("sqlalchemy")  # already imported, but confirms DB is needed

    from sqlalchemy import text

    winner = CandidateWeights(
        weights=SignalWeights(),
        expected_calmar=1.5,
        expected_alpha_t=2.1,
        shrinkage_lambda=0.15,
    )

    version = f"phase10_test_{date.today().isoformat()}"
    effective = date(2026, 1, 1)

    persist_best_weights(
        session=tmp_db_session,
        winner=winner,
        effective_from=effective,
        weight_set_version=version,
    )

    # Verify rows written
    rows = tmp_db_session.execute(
        text("""
            SELECT signal_name, weight, tier, regime, approved_by, effective_from
            FROM atlas.atlas_signal_weights
            WHERE approved_by = :ver
              AND effective_to IS NULL
        """),
        {"ver": version},
    ).fetchall()

    assert len(rows) == len(
        _SIGNALS
    ), f"Expected {len(_SIGNALS)} rows in atlas_signal_weights, got {len(rows)}"
    for row in rows:
        assert row[2] == _V6_TIER, f"tier mismatch: {row[2]}"
        assert row[3] == _V6_REGIME, f"regime mismatch: {row[3]}"
        assert isinstance(row[1], Decimal), f"weight should be Decimal, got {type(row[1])}"
        assert row[4] == version


# ---------------------------------------------------------------------------
# 6. test_bayesian_shrinkage_lambda_zero_equals_normalized_observed
# ---------------------------------------------------------------------------


def test_bayesian_shrinkage_lambda_zero_equals_normalized_observed(biased_ic, default_prior):
    """lambda=0 → result normalized weights should exactly match normalized IC."""
    result = bayesian_shrinkage_weights(biased_ic, default_prior, shrinkage_lambda=0.0)
    result_norm = result.normalized()

    ic_total = sum(max(0.0, v) for v in biased_ic.values())
    ic_norm = {s: max(0.0, biased_ic.get(s, 0.0)) / ic_total for s in _SIGNALS}

    for sig in _SIGNALS:
        assert (
            abs(result_norm[sig] - ic_norm[sig]) < 1e-9
        ), f"Signal {sig}: lambda=0 result={result_norm[sig]:.6f} ≠ ic_norm={ic_norm[sig]:.6f}"


# ---------------------------------------------------------------------------
# 7. test_bayesian_shrinkage_lambda_one_equals_prior
# ---------------------------------------------------------------------------


def test_bayesian_shrinkage_lambda_one_equals_prior(biased_ic, default_prior):
    """lambda=1.0 → result normalized weights should exactly match prior normalized."""
    result = bayesian_shrinkage_weights(biased_ic, default_prior, shrinkage_lambda=1.0)
    result_norm = result.normalized()
    prior_norm = default_prior.normalized()

    for sig in _SIGNALS:
        assert (
            abs(result_norm[sig] - prior_norm[sig]) < 1e-9
        ), f"Signal {sig}: lambda=1 result={result_norm[sig]:.6f} ≠ prior={prior_norm[sig]:.6f}"


# ---------------------------------------------------------------------------
# 8. test_generate_candidate_grid_custom_lambdas
# ---------------------------------------------------------------------------


def test_generate_candidate_grid_custom_lambdas(uniform_ic, default_prior):
    """Custom lambda list → correct number of candidates with correct lambda values."""
    lambdas = [0.1, 0.5, 0.9]
    candidates = generate_candidate_grid(uniform_ic, default_prior, lambdas=lambdas)

    assert len(candidates) == 3
    for cand, expected_lam in zip(candidates, lambdas, strict=False):
        assert cand.shrinkage_lambda == expected_lam
        assert isinstance(cand.weights, SignalWeights)


# ---------------------------------------------------------------------------
# 9. test_candidate_weights_shrinkage_lambda_stored_correctly
# ---------------------------------------------------------------------------


def test_candidate_weights_shrinkage_lambda_stored_correctly(uniform_ic, default_prior):
    """Each CandidateWeights stores the correct shrinkage_lambda it was built with."""
    candidates = generate_candidate_grid(uniform_ic, default_prior)
    expected_lambdas = [0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 1.00]

    for cand, expected in zip(candidates, expected_lambdas, strict=False):
        assert (
            cand.shrinkage_lambda == expected
        ), f"Expected lambda={expected}, got {cand.shrinkage_lambda}"


# ---------------------------------------------------------------------------
# 10. test_bayesian_shrinkage_raises_on_invalid_lambda
# ---------------------------------------------------------------------------


def test_bayesian_shrinkage_raises_on_invalid_lambda(uniform_ic, default_prior):
    """lambda outside [0, 1] should raise ValueError."""
    with pytest.raises(ValueError, match="shrinkage_lambda must be in"):
        bayesian_shrinkage_weights(uniform_ic, default_prior, shrinkage_lambda=-0.1)

    with pytest.raises(ValueError, match="shrinkage_lambda must be in"):
        bayesian_shrinkage_weights(uniform_ic, default_prior, shrinkage_lambda=1.1)


# ---------------------------------------------------------------------------
# 11. test_estimate_signal_ic_with_mock_runs
# ---------------------------------------------------------------------------


def test_estimate_signal_ic_with_mock_runs(default_prior):
    """Non-empty runs → IC proxy proportional to calmar × weight."""
    mock_session = MagicMock()
    # Simulate 2 strategy runs
    weights_json_1 = json.dumps({s: (0.15 if s == "natr_14" else 0.10) for s in _SIGNALS})
    weights_json_2 = json.dumps({s: 0.11 for s in _SIGNALS})
    mock_session.execute.return_value.fetchall.return_value = [
        (weights_json_1, Decimal("1.5")),  # high calmar
        (weights_json_2, Decimal("0.5")),  # low calmar
    ]

    result = estimate_signal_ic_from_strategy_runs(mock_session)

    # All signals should be positive
    for sig in _SIGNALS:
        assert result[sig] > 0, f"Signal {sig} IC should be positive"

    # natr_14 got higher weight in run 1 (calmar=1.5) → should have higher IC proxy
    assert (
        result["natr_14"] > result["industry_rs"]
    ), "natr_14 had higher weight in high-calmar run; should have higher IC proxy"


# ---------------------------------------------------------------------------
# 12. test_estimate_signal_ic_all_zero_calmar_returns_uniform
# ---------------------------------------------------------------------------


def test_estimate_signal_ic_all_zero_calmar_returns_uniform():
    """All calmar=0 → IC proxy should fall back to uniform."""
    mock_session = MagicMock()
    weights_json = json.dumps({s: 0.11 for s in _SIGNALS})
    mock_session.execute.return_value.fetchall.return_value = [
        (weights_json, Decimal("0.0")),
        (weights_json, Decimal("0.0")),
    ]

    result = estimate_signal_ic_from_strategy_runs(mock_session)

    for sig in _SIGNALS:
        assert result[sig] == 1.0, f"Expected uniform IC=1.0 for {sig}, got {result[sig]}"


# ---------------------------------------------------------------------------
# 13. test_rank_candidates_sorts_by_calmar
# ---------------------------------------------------------------------------


def test_rank_candidates_sorts_by_calmar(uniform_ic, default_prior):
    """rank_candidates should return results sorted by calmar descending."""
    candidates = generate_candidate_grid(uniform_ic, default_prior, lambdas=[0.1, 0.5, 1.0])

    # Mock the simulator
    mock_session = MagicMock()
    call_count = [0]

    def mock_run_simulation(session, config):
        # Return different calmars based on call order
        calmars = [0.8, 1.5, 0.3]
        result = MagicMock()
        result.calmar = calmars[call_count[0] % len(calmars)]
        result.alpha_t_stat = 2.0
        result.sharpe = 1.0
        result.max_drawdown = -0.15
        result.ann_return = 0.12
        call_count[0] += 1
        return result

    original = None
    try:
        from atlas.trading.v6 import simulator as sim_mod

        original = sim_mod.run_simulation
        sim_mod.run_simulation = mock_run_simulation

        quick_window = (date(2024, 1, 1), date(2024, 12, 31))
        ranked = rank_candidates(candidates, mock_session, quick_window)
    finally:
        if original is not None:
            sim_mod.run_simulation = original

    # Should be sorted calmar desc: [1.5, 0.8, 0.3]
    calmar_vals = [stats.get("calmar", 0) for _, stats in ranked]
    assert calmar_vals == sorted(
        calmar_vals, reverse=True
    ), f"Expected descending calmar order: {calmar_vals}"
