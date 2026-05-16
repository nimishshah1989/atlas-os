from atlas.trading.optimizer import OptunaStudy


def test_study_create_and_optimize():
    study = OptunaStudy(study_name="test_atlas_lab", storage=None)  # in-memory storage

    call_count = {"n": 0}

    def mock_objective(genome):
        call_count["n"] += 1
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0  # fake score

    study.run_trials(n_trials=5, objective_fn=mock_objective)
    assert call_count["n"] == 5
    best = study.best_genome()
    assert best is not None
    assert 60 <= best.layer1.rs_leader_cutoff_pct <= 80


def test_parameter_importance_keys():
    study = OptunaStudy(study_name="test_atlas_lab_imp", storage=None)

    def mock_objective(genome):
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0

    study.run_trials(n_trials=10, objective_fn=mock_objective)
    importance = study.get_parameter_importance()
    assert isinstance(importance, dict)
    assert len(importance) > 0


def test_best_genome_empty_study_returns_none():
    study = OptunaStudy(study_name="test_atlas_empty", storage=None)
    assert study.best_genome() is None


def test_run_trials_n_jobs_parallel_completes_all():
    """n_jobs=4 should still execute exactly n_trials of the objective.

    Regression for the parallelization patch that runs Optuna trials in a
    thread pool. The objective callback must be called once per trial even
    under concurrent execution; list.append is atomic in CPython so the
    counter is safe without an explicit lock.
    """
    import threading

    study = OptunaStudy(study_name="test_atlas_parallel", storage=None)
    call_count = {"n": 0}
    counter_lock = threading.Lock()

    def mock_objective(genome):
        with counter_lock:
            call_count["n"] += 1
        return float(genome.layer1.rs_leader_cutoff_pct) / 100.0

    study.run_trials(n_trials=8, objective_fn=mock_objective, n_jobs=4)
    assert call_count["n"] == 8
    assert study.best_genome() is not None
