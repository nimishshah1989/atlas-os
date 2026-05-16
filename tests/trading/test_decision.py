import numpy as np
import pytest

from atlas.trading.decision import (
    apply_entry_rules,
    apply_exit_rules,
    compute_conviction,
    compute_position_size,
)
from atlas.trading.genome import GenomeFactory
from atlas.trading.perception import (
    MOM_ACCELERATING,
    MOM_NEUTRAL,
    REGIME_RISK_OFF,
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
    g.layer1.conviction_rs_weight = 0.60
    g.layer1.conviction_mom_weight = 0.20
    g.layer1.conviction_state_weight = 0.15
    g.layer1.conviction_velocity_weight = 0.05
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


def test_entry_blocked_when_regime_risk_off():
    """All entries must be blocked when regime is REGIME_RISK_OFF, regardless of conviction."""
    g = _genome()
    conviction = np.array([0.9, 0.8, 0.7])
    mask = apply_entry_rules(conviction, regime=REGIME_RISK_OFF, portfolio_heat=0.0, genome=g)
    assert not mask.any()


def test_entry_blocked_when_drawdown_exceeds_halt():
    """All entries must be blocked when portfolio drawdown >= dd_halt_entry_pct."""
    g = _genome()
    # dd_halt_entry_pct is in percent (e.g. 15.0 means 15%) — drawdown arg is fraction
    halt_pct = g.risk_on.dd_halt_entry_pct  # e.g. 15.0
    drawdown_fraction = halt_pct / 100.0  # 0.15
    conviction = np.array([0.9, 0.8])
    mask = apply_entry_rules(
        conviction,
        regime=REGIME_RISK_ON,
        portfolio_heat=0.0,
        genome=g,
        portfolio_drawdown=drawdown_fraction,
    )
    assert not mask.any()


def test_position_size_scales_with_conviction():
    """Position size at entry threshold equals base_position_pct/100; high conviction is capped."""
    g = _genome()
    # Pin base_position_pct to 2.0 so base=0.02 is well below max_pos=0.05 (scale=1 won't clip)
    g.risk_on.base_position_pct = 2.0
    playbook = g.risk_on
    max_pos = 0.05

    # At exactly min_conviction_to_enter: excess=0, scale=1.0, size = base_position_pct/100
    size_at_min = compute_position_size(
        conviction=playbook.min_conviction_to_enter,
        playbook=playbook,
        max_position_pct=max_pos,
    )
    assert size_at_min == playbook.base_position_pct / 100.0

    # Very high conviction: should be capped at max_position_pct
    size_at_max = compute_position_size(
        conviction=1.0,
        playbook=playbook,
        max_position_pct=max_pos,
    )
    assert size_at_max <= max_pos


# ---------------------------------------------------------------------------
# New CTS + hysteresis tests
# ---------------------------------------------------------------------------


def test_entry_blocked_stage3():
    """Stage 3 stock is blocked regardless of conviction when require_stage2_for_entry=True."""
    g = _genome()
    object.__setattr__(g.layer1, "require_stage2_for_entry", True)
    stage = np.array([3, 3, 2, 2])
    conviction = np.array([0.9, 0.8, 0.9, 0.8])
    mask = apply_entry_rules(
        conviction,
        regime=REGIME_RISK_ON,
        portfolio_heat=0.1,
        genome=g,
        max_portfolio_heat_pct=0.30,
        stage=stage,
    )
    assert not mask[0]  # stage 3 blocked
    assert not mask[1]  # stage 3 blocked
    assert mask[2]  # stage 2 passes
    assert mask[3]  # stage 2 passes


def test_entry_stage3_blocked_via_stage3_blocks_entry():
    """Stage 3 stock blocked by stage3_blocks_entry when require_stage2_for_entry=False."""
    g = _genome()
    object.__setattr__(g.layer1, "require_stage2_for_entry", False)
    object.__setattr__(g.layer1, "stage3_blocks_entry", True)
    stage = np.array([1, 2, 3, 4])
    conviction = np.array([0.9, 0.9, 0.9, 0.9])
    mask = apply_entry_rules(
        conviction,
        regime=REGIME_RISK_ON,
        portfolio_heat=0.1,
        genome=g,
        max_portfolio_heat_pct=0.30,
        stage=stage,
    )
    assert mask[0]  # stage 1 allowed (< 3)
    assert mask[1]  # stage 2 allowed (< 3)
    assert not mask[2]  # stage 3 blocked
    assert not mask[3]  # stage 4 blocked


def test_npc_overrides_min_hold():
    """NPC signal exits even when min_hold_days not reached."""
    g = _genome()
    object.__setattr__(g.layer1, "npc_overrides_min_hold", True)
    prev_rs = np.array([4, 3], dtype=np.int8)
    curr_rs = np.array([4, 3], dtype=np.int8)  # no RS drop
    holding = np.array([2, 3])  # below any min_hold_days
    npc = np.array([1, 0], dtype=np.int8)  # stock 0 has NPC signal

    mask = apply_exit_rules(
        prev_rs,
        curr_rs,
        holding,
        min_hold_days=10,
        exit_rs_drop_tiers=2,
        npc=npc,
        npc_overrides_min_hold=True,
    )
    assert mask[0]  # NPC triggers exit despite only 2 days held
    assert not mask[1]  # no NPC, no RS drop — not exited


def test_npc_no_override_when_flag_false():
    """NPC signal does NOT override min_hold when npc_overrides_min_hold=False."""
    prev_rs = np.array([4], dtype=np.int8)
    curr_rs = np.array([4], dtype=np.int8)
    holding = np.array([2])
    npc = np.array([1], dtype=np.int8)

    mask = apply_exit_rules(
        prev_rs,
        curr_rs,
        holding,
        min_hold_days=10,
        exit_rs_drop_tiers=2,
        npc=npc,
        npc_overrides_min_hold=False,
    )
    assert not mask[0]  # NPC present but override disabled — no exit


def test_ppc_boosts_conviction():
    """PPC signal increases conviction by ppc_conviction_boost (when not clipped at 1.0).

    Use a low base rs_pctile so the pre-boost conviction is well below 1.0,
    ensuring the full ppc_conviction_boost is visible in the difference.
    """
    g = _genome()
    # Low RS percentile → low base conviction, headroom for PPC boost
    without_ppc = compute_conviction(
        0.1, RS_AVERAGE, MOM_NEUTRAL, VOL_NORMAL, 5, 0, g.layer1, ppc=0
    )
    with_ppc = compute_conviction(0.1, RS_AVERAGE, MOM_NEUTRAL, VOL_NORMAL, 5, 0, g.layer1, ppc=1)
    assert with_ppc > without_ppc
    # Both values well below 1.0 so the full boost is captured
    assert with_ppc - without_ppc == pytest.approx(g.layer1.ppc_conviction_boost, abs=1e-6)


def test_contraction_boosts_conviction():
    """Contraction signal increases conviction by contraction_entry_bonus (when not clipped).

    Use a low base rs_pctile so the pre-boost conviction is well below 1.0,
    ensuring the full contraction_entry_bonus is visible in the difference.
    """
    g = _genome()
    # Low RS percentile → low base conviction, headroom for contraction boost
    without = compute_conviction(
        0.1, RS_AVERAGE, MOM_NEUTRAL, VOL_NORMAL, 5, 0, g.layer1, contraction=0
    )
    with_c = compute_conviction(
        0.1, RS_AVERAGE, MOM_NEUTRAL, VOL_NORMAL, 5, 0, g.layer1, contraction=1
    )
    assert with_c > without
    assert with_c - without == pytest.approx(g.layer1.contraction_entry_bonus, abs=1e-6)


def test_conviction_capped_at_1():
    """Even with PPC + contraction boost, conviction must not exceed 1.0."""
    g = _genome()
    # High base conviction + full boosts must stay ≤ 1.0
    result = compute_conviction(
        1.0, RS_LEADER, MOM_ACCELERATING, VOL_NORMAL, 1, 1, g.layer1, ppc=1, contraction=1
    )
    assert result <= 1.0
