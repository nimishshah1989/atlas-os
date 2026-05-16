from __future__ import annotations

from datetime import date

from atlas.trading.genome import GenomeFactory
from atlas.trading.simulator import SimResult
from atlas.trading.tournament import TournamentEvaluator, _auto_name


def _sim_result(
    sortino: float,
    calmar: float = 0.5,
    trades: int = 10,
    max_dd: float = 0.10,
) -> SimResult:
    return SimResult(
        sortino_oos=sortino,
        calmar_oos=calmar,
        sortino_insample=sortino + 0.1,
        max_drawdown=max_dd,
        total_trades=trades,
        turnover_pct=0.05,
    )


def _evaluator() -> TournamentEvaluator:
    return TournamentEvaluator(
        stress_periods={
            "covid_2020": (date(2020, 2, 1), date(2020, 5, 31)),
            "bear_2022": (date(2022, 1, 1), date(2022, 6, 30)),
            "bull_2023": (date(2023, 1, 1), date(2023, 12, 31)),
        }
    )


def test_genome_failing_round1_not_promoted() -> None:
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        return _sim_result(sortino=0.3)  # < 0.7 threshold → fail Round 1

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 1
    assert result.fail_reason is not None


def test_genome_failing_round2_not_promoted() -> None:
    evaluator = _evaluator()
    genome = GenomeFactory.random()
    call_count = {"n": 0}

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        return _sim_result(sortino=0.9 if call_count["n"] == 1 else 0.3)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 2


def test_genome_covid_stress_fail() -> None:
    evaluator = _evaluator()
    genome = GenomeFactory.random()
    call_count = {"n": 0}

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return _sim_result(sortino=0.9)  # Rounds 1 + 2 pass
        # COVID period: drawdown > 25% → fail
        return _sim_result(sortino=0.5, max_dd=0.30)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert not result.promoted
    assert result.failed_round == 3


def test_genome_passing_all_rounds_promoted() -> None:
    evaluator = _evaluator()
    genome = GenomeFactory.random()

    def sim_fn(*_):  # type: ignore[no-untyped-def]
        return _sim_result(sortino=0.9, calmar=1.2, max_dd=0.08)

    result = evaluator.evaluate(
        genome, sim_fn, recent_start=date(2024, 9, 1), recent_end=date(2024, 12, 31)
    )
    assert result.promoted
    assert result.failed_round is None
    assert result.fail_reason is None
    assert result.final_sortino >= 0.7


def test_auto_name_reflects_genome() -> None:
    genome = GenomeFactory.random()
    name = _auto_name(genome)
    assert isinstance(name, str)
    assert len(name) > 0
    assert "-G" in name  # generation marker
