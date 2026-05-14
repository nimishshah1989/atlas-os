from atlas.trading.genome import Genome, GenomeFactory


def test_random_genome_is_valid():
    g = GenomeFactory.random()
    assert 60 <= g.layer1.rs_leader_cutoff_pct <= 80
    assert g.layer1.rs_leader_cutoff_pct > g.layer1.rs_strong_cutoff_pct
    weights = g.layer1.rs_timeframe_weights
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert 2.0 <= g.risk_on.base_position_pct <= 6.0
    # 6 new genome-controlled fields
    assert 0.40 <= g.layer1.conviction_rs_weight <= 0.80
    assert 0.10 <= g.layer1.conviction_mom_weight <= 0.40
    assert 0.05 <= g.layer1.conviction_state_weight <= 0.25
    assert 0.01 <= g.layer1.conviction_velocity_weight <= 0.15
    assert 0.03 <= g.layer1.genome_max_position_pct <= 0.08
    assert 0.12 <= g.layer1.genome_max_heat_pct <= 0.30


def test_genome_json_roundtrip():
    g = GenomeFactory.random()
    data = g.to_dict()
    g2 = Genome.from_dict(data)
    assert g2.genome_id == g.genome_id
    assert g2.layer1.rs_leader_cutoff_pct == g.layer1.rs_leader_cutoff_pct
    assert g2.risk_on.min_conviction_to_enter == g.risk_on.min_conviction_to_enter
    assert g2.layer1.conviction_rs_weight == g.layer1.conviction_rs_weight
    assert g2.layer1.genome_max_position_pct == g.layer1.genome_max_position_pct


def test_optuna_trial_produces_valid_genome():
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")

    def _obj(trial):
        g = GenomeFactory.from_optuna_trial(trial)
        assert 60 <= g.layer1.rs_leader_cutoff_pct <= 80
        assert 0.40 <= g.layer1.conviction_rs_weight <= 0.80
        assert 0.03 <= g.layer1.genome_max_position_pct <= 0.08
        return 0.5

    study.optimize(_obj, n_trials=3)
    assert study.best_value == 0.5
