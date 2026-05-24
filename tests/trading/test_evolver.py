from __future__ import annotations

from atlas.trading.evolver import Evolver
from atlas.trading.genome import GenomeFactory


def test_crossover_offspring_in_range():
    evolver = Evolver()
    parent_a = GenomeFactory.random()
    parent_b = GenomeFactory.random()
    child_a, child_b = evolver.crossover(parent_a, parent_b)
    assert 60 <= child_a.layer1.rs_leader_cutoff_pct <= 80
    assert 60 <= child_b.layer1.rs_leader_cutoff_pct <= 80
    assert 2.0 <= child_a.risk_on.base_position_pct <= 6.0
    # CTS invariants must hold
    assert child_a.layer1.rs_leader_exit_pct < child_a.layer1.rs_leader_cutoff_pct
    assert child_a.layer1.rs_strong_exit_pct < child_a.layer1.rs_strong_cutoff_pct
    assert isinstance(child_a.layer1.require_stage2_for_entry, bool)
    assert child_a.layer1.stage3_blocks_entry is True  # always True


def test_mutate_changes_params():
    evolver = Evolver()
    genome = GenomeFactory.random()
    mutated = evolver.mutate(genome, sigma=0.15)
    # Mutated genome must still be within search-space bounds
    assert 60 <= mutated.layer1.rs_leader_cutoff_pct <= 80
    # CTS invariants must hold after mutation
    assert mutated.layer1.rs_leader_exit_pct < mutated.layer1.rs_leader_cutoff_pct
    assert mutated.layer1.rs_strong_exit_pct < mutated.layer1.rs_strong_cutoff_pct


def test_mutate_preserves_types():
    evolver = Evolver()
    genome = GenomeFactory.random()
    mutated = evolver.mutate(genome, sigma=0.15)
    assert isinstance(mutated.layer1.require_stage2_for_entry, bool)
    assert mutated.layer1.stage3_blocks_entry is True


def test_select_survivors_keeps_pareto_front():
    evolver = Evolver()
    genomes_with_scores = [
        (GenomeFactory.random(), float(i) * 0.1, float(i) * 0.05) for i in range(10)
    ]
    survivors = evolver.select_survivors(genomes_with_scores, target_pool=6)
    assert len(survivors) == 6


def test_select_survivors_empty():
    evolver = Evolver()
    assert evolver.select_survivors([], target_pool=10) == []
