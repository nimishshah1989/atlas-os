import numpy as np

from atlas.trading.decision import apply_entry_rules, apply_exit_rules, compute_conviction
from atlas.trading.genome import GenomeFactory
from atlas.trading.perception import (
    MOM_ACCELERATING,
    MOM_NEUTRAL,
    REGIME_RISK_ON,
    RS_AVERAGE,
    RS_LEADER,
    RS_STRONG,
    VOL_HIGH,
    VOL_NORMAL,
)


def _genome():
    g = GenomeFactory.random()
    g.layer1.synergy_weight = 0.2
    g.layer1.penalty_weight = 0.1
    g.risk_on.min_conviction_to_enter = 0.55
    g.risk_on.exit_rs_drop_tiers = 2
    g.risk_on.min_hold_days = 5  # pin so holding_days=10 always satisfies the constraint
    return g


def test_conviction_high_rs_momentum_synergy():
    g = _genome()
    # High RS percentile + accelerating momentum → high conviction via synergy
    score = compute_conviction(
        rs_pctile_norm=0.90,
        rs_state=RS_LEADER,
        momentum_state=MOM_ACCELERATING,
        vol_state=VOL_NORMAL,
        days_in_state=10,
        direction=1,
        layer1=g.layer1,
    )
    assert score > 0.5


def test_conviction_penalized_by_vol():
    g = _genome()
    g.layer1.penalty_weight = 0.3
    score_normal_vol = compute_conviction(
        rs_pctile_norm=0.80,
        rs_state=RS_LEADER,
        momentum_state=MOM_NEUTRAL,
        vol_state=VOL_NORMAL,
        days_in_state=5,
        direction=0,
        layer1=g.layer1,
    )
    score_high_vol = compute_conviction(
        rs_pctile_norm=0.80,
        rs_state=RS_LEADER,
        momentum_state=MOM_NEUTRAL,
        vol_state=VOL_HIGH,
        days_in_state=5,
        direction=0,
        layer1=g.layer1,
    )
    assert score_high_vol < score_normal_vol


def test_entry_blocked_when_heat_cap_hit():
    g = _genome()
    conviction = np.array([0.8, 0.7])
    heat = 0.21  # 21% > 20% max_portfolio_heat
    mask = apply_entry_rules(conviction, regime=REGIME_RISK_ON, portfolio_heat=heat, genome=g)
    assert not mask.any()


def test_exit_on_rs_drop():
    g = _genome()
    g.risk_on.exit_rs_drop_tiers = 2
    # Drop 1 tier (Strong→Average) < required 2 tiers → no exit
    prev_rs = np.array([RS_STRONG])
    curr_rs = np.array([RS_AVERAGE])
    mask = apply_exit_rules(
        prev_rs_state=prev_rs,
        curr_rs_state=curr_rs,
        holding_days=np.array([10]),
        min_hold_days=g.risk_on.min_hold_days,
        exit_rs_drop_tiers=g.risk_on.exit_rs_drop_tiers,
    )
    assert not mask[0]

    # Drop 3 tiers (Leader→Weak) > threshold of 2 → exit
    prev_rs2 = np.array([RS_LEADER])
    curr_rs2 = np.array([1])  # RS_WEAK
    mask2 = apply_exit_rules(
        prev_rs_state=prev_rs2,
        curr_rs_state=curr_rs2,
        holding_days=np.array([10]),
        min_hold_days=g.risk_on.min_hold_days,
        exit_rs_drop_tiers=g.risk_on.exit_rs_drop_tiers,
    )
    assert mask2[0]
