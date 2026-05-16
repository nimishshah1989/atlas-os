from __future__ import annotations

from datetime import date

from atlas.trading.genome import GenomeFactory
from atlas.trading.simulator import SimResult
from atlas.trading.tournament import TournamentEvaluator, _auto_name


def _sim_result(
    alpha: float = 0.05,
    ir: float = 0.5,
    hit_rate: float = 0.65,
    sortino: float = 0.9,
    calmar: float = 0.5,
    trades: int = 10,
    max_dd: float = 0.10,
    t_stat: float = 2.5,
) -> SimResult:
    return SimResult(
        sortino_oos=sortino,
        calmar_oos=calmar,
        sortino_insample=sortino + 0.1,
        max_drawdown=max_dd,
        total_trades=trades,
        turnover_pct=0.05,
        alpha_oos=alpha,
        benchmark_return_oos=0.10,
        tracking_error=abs(alpha) / max(ir, 1e-9),
        information_ratio=ir,
        hit_rate=hit_rate,
        alpha_t_stat=t_stat,
    )


def _evaluator() -> TournamentEvaluator:
    return TournamentEvaluator(
        stress_periods={
            "covid_2020": (date(2020, 2, 1), date(2020, 5, 31)),
            "bear_2022": (date(2022, 1, 1), date(2022, 6, 30)),
            "bull_2023": (date(2023, 1, 1), date(2023, 12, 31)),
        }
    )


def test_genome_failing_round1_alpha_zero_not_promoted() -> None:
    """Negative alpha in recent window fails Round 1 immediately."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        return _sim_result(alpha=-0.02)  # negative alpha → fail

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 1
    assert "alpha" in (result.fail_reason or "").lower()


def test_genome_failing_round1_low_hit_rate_not_promoted() -> None:
    """Positive alpha but hit_rate < 0.55 fails Round 1."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        return _sim_result(alpha=0.05, hit_rate=0.50)  # below 0.55 floor

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 1
    assert "hit_rate" in (result.fail_reason or "").lower()


def test_genome_failing_round1_low_ir_not_promoted() -> None:
    """Positive alpha + decent hit rate but IR < 0.3 fails Round 1."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        return _sim_result(alpha=0.05, hit_rate=0.65, ir=0.2)  # IR too low

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 1
    assert "ir" in (result.fail_reason or "").lower()


def test_genome_failing_round2_alpha_not_promoted() -> None:
    """Round 1 passes but Round 2 alpha is negative — consistency gate fails."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()
    call_count = {"n": 0}

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        # Round 1: pass. Round 2: negative alpha.
        return _sim_result(alpha=0.05 if call_count["n"] == 1 else -0.02)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 2


def test_genome_covid_drawdown_fail() -> None:
    """Rounds 1-2 pass but COVID drawdown exceeds 25% — Round 3 fails."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()
    call_count = {"n": 0}

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return _sim_result(alpha=0.05)  # Rounds 1+2 pass
        # COVID window: drawdown > 25% → fail
        return _sim_result(alpha=0.02, max_dd=0.30)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 3
    assert "covid" in (result.fail_reason or "").lower()


def test_genome_bear_alpha_fail() -> None:
    """COVID passes but 2022 bear window has negative alpha — Round 3 fails."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()
    call_count = {"n": 0}

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        # Rounds 1+2 + COVID pass; bear window (call 4) fails on alpha
        if call_count["n"] < 4:
            return _sim_result(alpha=0.05, max_dd=0.10)
        return _sim_result(alpha=-0.03, max_dd=0.10)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 3
    assert "bear" in (result.fail_reason or "").lower()


def test_genome_passing_all_rounds_promoted() -> None:
    """Healthy alpha + IR + hit rate + DD across all 3 rounds → promoted."""
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        return _sim_result(alpha=0.08, hit_rate=0.70, ir=0.8, max_dd=0.08)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert result.promoted
    assert result.failed_round is None
    assert result.fail_reason is None
    assert result.final_alpha > 0
    assert result.final_information_ratio >= 0.3
    assert result.final_hit_rate >= 0.55


def test_auto_name_reflects_genome() -> None:
    genome = GenomeFactory.random()
    name = _auto_name(genome)
    assert isinstance(name, str)
    assert len(name) > 0
    assert "-G" in name  # generation marker
