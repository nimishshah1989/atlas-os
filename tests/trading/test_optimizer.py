from atlas.trading.optimizer import OptunaStudy


def test_study_create_and_optimize():
    study = OptunaStudy(study_name="test_atlas_lab", storage=None)  # in-memory storage

    call_count = {"n": 0}

    def mock_objective(genome):
        call_count["n"] += 1
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0  # fake score

    study.run_trials(n_trials=5, objective_fn=mock_objective)
    assert call_count["n"] == 5
    assert study.best_genome() is not None
    best = study.best_genome()
    assert 60 <= best.layer1.rs_leader_cutoff_pct <= 80


def test_parameter_importance_keys():
    study = OptunaStudy(study_name="test_atlas_lab_imp", storage=None)

    def mock_objective(genome):
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0

    study.run_trials(n_trials=10, objective_fn=mock_objective)
    importance = study.get_parameter_importance()
    assert isinstance(importance, dict)
    assert len(importance) > 0
