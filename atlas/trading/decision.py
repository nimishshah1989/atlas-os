"""Layer 2: conviction scoring and entry/exit signal generation.

Conviction formula (spec §6.2):
    base = weighted_sum(rs_pctile_norm, momentum_state, rs_state, velocity_bonus)
           using genome-controlled layer1 weights
    synergy = rs_pctile_norm × momentum_state_norm   (RS × momentum interaction)
    penalty = vol_ratio_norm × rs_pctile_norm        (high vol discounts RS)
    conviction = clip(base × (1 + synergy_weight × synergy) × (1 - penalty_weight × penalty), 0, 1)
"""

from __future__ import annotations

import numpy as np

from atlas.trading.genome import Genome, Layer1Perception, RegimePlaybook
from atlas.trading.perception import (
    MOM_ACCELERATING,
    MOM_DECELERATING,
    MOM_NEUTRAL,
    REGIME_CONSTRUCTIVE,
    REGIME_RISK_OFF,
    REGIME_RISK_ON,
    RS_AVERAGE,
    RS_LAGGARD,
    RS_LEADER,
    RS_STRONG,
    RS_WEAK,
    VOL_ELEVATED,
    VOL_HIGH,
    VOL_NORMAL,
)

# Normalize state integers to [0, 1] for scoring
_RS_NORM = {RS_LAGGARD: 0.0, RS_WEAK: 0.2, RS_AVERAGE: 0.4, RS_STRONG: 0.7, RS_LEADER: 1.0}
_MOM_NORM = {MOM_DECELERATING: 0.0, MOM_NEUTRAL: 0.5, MOM_ACCELERATING: 1.0}
_VOL_NORM = {VOL_NORMAL: 0.0, VOL_ELEVATED: 0.5, VOL_HIGH: 1.0}


def compute_conviction(
    rs_pctile_norm: float,  # 0–1 (raw percentile / 100)
    rs_state: int,
    momentum_state: int,
    vol_state: int,
    days_in_state: int,
    direction: int,  # -1, 0, 1
    layer1: Layer1Perception,
) -> float:
    """Compute conviction score 0–1 for a single stock on a single day.

    Uses genome-controlled layer1 weights for all signal components.
    Weights are on an unnormalized relative scale; clip(0, 1) is the intended
    normalization boundary.
    """
    rs_norm = rs_pctile_norm
    mom_norm = _MOM_NORM[momentum_state]
    vol_norm = _VOL_NORM[vol_state]
    rs_state_norm = _RS_NORM[rs_state]

    # Velocity bonus: fresh breakout (direction=1, few days in state) > mature leader
    velocity_bonus = direction * max(0.0, 1.0 - days_in_state / 30.0)

    # Base score: genome-controlled weighted blend
    base = (
        layer1.conviction_rs_weight * rs_norm
        + layer1.conviction_mom_weight * mom_norm
        + layer1.conviction_state_weight * rs_state_norm
        + layer1.conviction_velocity_weight * max(0.0, velocity_bonus)
    )

    # Interaction terms (spec §6.2)
    synergy = rs_norm * mom_norm
    penalty = vol_norm * rs_norm

    conviction = (
        base * (1.0 + layer1.synergy_weight * synergy) * (1.0 - layer1.penalty_weight * penalty)
    )
    return float(np.clip(conviction, 0.0, 1.0))


def _get_playbook(genome: Genome, regime: int) -> RegimePlaybook:
    if regime == REGIME_RISK_ON:
        return genome.risk_on
    if regime == REGIME_CONSTRUCTIVE:
        return genome.constructive
    return genome.cautious  # CAUTIOUS or RISK_OFF handled upstream


def apply_entry_rules(
    conviction: np.ndarray,
    regime: int,
    portfolio_heat: float,
    genome: Genome,
    portfolio_drawdown: float = 0.0,
    max_portfolio_heat_pct: float = 0.20,
) -> np.ndarray:
    """Return boolean mask of stocks eligible for entry today.

    Blocks all entries if regime is Risk-Off, heat cap exceeded, or drawdown >= halt threshold.
    """
    if regime == REGIME_RISK_OFF:
        return np.zeros(len(conviction), dtype=bool)

    playbook = _get_playbook(genome, regime)

    if portfolio_heat >= max_portfolio_heat_pct:
        return np.zeros(len(conviction), dtype=bool)

    if portfolio_drawdown >= playbook.dd_halt_entry_pct / 100.0:
        return np.zeros(len(conviction), dtype=bool)

    return conviction >= playbook.min_conviction_to_enter


def apply_exit_rules(
    prev_rs_state: np.ndarray,
    curr_rs_state: np.ndarray,
    holding_days: np.ndarray,
    min_hold_days: int,
    exit_rs_drop_tiers: int,
) -> np.ndarray:
    """Return boolean mask of positions that should be exited today.

    Exits when RS state drops by >= exit_rs_drop_tiers tiers, after min_hold_days constraint.
    """
    rs_drop = prev_rs_state.astype(np.int8) - curr_rs_state.astype(np.int8)
    held_long_enough = holding_days >= min_hold_days
    return (rs_drop >= exit_rs_drop_tiers) & held_long_enough


def compute_position_size(
    conviction: float,
    playbook: RegimePlaybook,
    max_position_pct: float = 0.05,
) -> float:
    """Return position size as fraction of portfolio.

    Base size = playbook.base_position_pct / 100.
    Scaled by conviction above entry threshold, capped at max_position_pct.
    """
    base = playbook.base_position_pct / 100.0
    excess = conviction - playbook.min_conviction_to_enter
    scale = 1.0 + min(excess * 2.0, 1.0)
    return min(base * scale, max_position_pct)
