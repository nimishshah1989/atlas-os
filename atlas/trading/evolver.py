"""DEAP-inspired genome evolver: crossover, mutation, and survivor selection.

Operates on Genome dataclasses from atlas.trading.genome. No DB access.
All search-space bounds are genetic operator bounds, not trading thresholds.
NOTE: Uses standard random (not crypto-secure) for non-cryptographic genome
evolution. S311 suppressions throughout are intentional.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from atlas.trading.genome import Genome, Layer1Perception, RegimePlaybook

log = structlog.get_logger(__name__)

# Search-space bounds for the genetic operators
_L1_FLOAT_BOUNDS: dict[str, tuple[float, float]] = {
    "regime_risk_on_vix_ceiling": (14.0, 22.0),
    "momentum_accel_ema_ratio": (1.005, 1.03),
    "momentum_decel_ema_ratio": (0.97, 0.995),
    "vol_elevated_ratio": (1.2, 1.8),
    "vol_high_ratio": (1.5, 2.5),
    "synergy_weight": (0.0, 0.3),
    "penalty_weight": (0.0, 0.3),
    "genome_max_position_pct": (0.03, 0.08),
    "genome_max_heat_pct": (0.12, 0.30),
    "conviction_rs_weight": (0.40, 0.80),
    "conviction_mom_weight": (0.10, 0.40),
    "conviction_state_weight": (0.05, 0.25),
    "conviction_velocity_weight": (0.01, 0.15),
    "ppc_conviction_boost": (0.05, 0.30),
    "contraction_entry_bonus": (0.0, 0.20),
}

_REGIME_FLOAT_BOUNDS: dict[str, tuple[float, float]] = {
    "min_conviction_to_enter": (0.35, 0.80),
    "base_position_pct": (2.0, 6.0),
    "dd_halt_entry_pct": (8.0, 15.0),
    "dd_tighten_exit_pct": (14.0, 22.0),
    "dd_liquidate_pct": (19.0, 30.0),
}

_REGIME_FLOAT_OPTIONAL: dict[str, tuple[float, float]] = {
    "profit_target_pct": (10.0, 30.0),
    "trailing_stop_from_peak_pct": (5.0, 20.0),
}

_L1_INT_RANGES: list[tuple[str, int, int]] = [
    ("rs_leader_cutoff_pct", 60, 80),
    ("rs_strong_cutoff_pct", 45, 65),
    ("rs_average_cutoff_pct", 25, 45),
    ("rs_weak_cutoff_pct", 10, 25),
    ("regime_risk_on_breadth_pct", 50, 70),
    ("regime_constructive_breadth_pct", 35, 55),
    ("regime_cautious_breadth_pct", 20, 40),
    ("state_velocity_lookback_days", 5, 20),
]


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _blend(a: float, b: float, noise: float = 0.05) -> float:
    mid = (a + b) / 2.0
    return mid + random.uniform(-abs(b - a) * noise, abs(b - a) * noise)  # noqa: S311


def _normalize_weights(w: dict[str, float]) -> dict[str, float]:
    total = sum(w.values())
    if total <= 0.0:
        return {"1w": 1 / 3, "1m": 1 / 3, "3m": 1 / 3}
    return {k: v / total for k, v in w.items()}


def _enforce_l1_invariants(d: dict[str, Any]) -> dict[str, Any]:
    """Enforce all Layer1Perception cascade invariants. Mutates d in-place."""
    # RS cutoff cascade: leader > strong > average > weak
    leader = int(_clamp(d["rs_leader_cutoff_pct"], 60, 80))
    strong = int(_clamp(d["rs_strong_cutoff_pct"], 45, min(65, leader - 1)))
    average = int(_clamp(d["rs_average_cutoff_pct"], 25, min(45, strong - 1)))
    weak = int(_clamp(d["rs_weak_cutoff_pct"], 10, min(25, average - 1)))
    if strong >= leader:
        strong = leader - 1
    if average >= strong:
        average = strong - 1
    if weak >= average:
        weak = average - 1
    weak = max(10, weak)
    average = max(weak + 1, min(average, 45))
    strong = max(average + 1, min(strong, 65))
    leader = max(strong + 1, min(leader, 80))
    d.update(
        rs_leader_cutoff_pct=leader,
        rs_strong_cutoff_pct=strong,
        rs_average_cutoff_pct=average,
        rs_weak_cutoff_pct=weak,
    )

    # Breadth cascade: risk_on > constructive > cautious
    ron_b = int(_clamp(d["regime_risk_on_breadth_pct"], 50, 70))
    con_b = int(_clamp(d["regime_constructive_breadth_pct"], 35, min(55, ron_b - 1)))
    cau_b = int(_clamp(d["regime_cautious_breadth_pct"], 20, min(40, con_b - 1)))
    if con_b >= ron_b:
        con_b = ron_b - 1
    if cau_b >= con_b:
        cau_b = con_b - 1
    cau_b = max(20, cau_b)
    con_b = max(cau_b + 1, min(con_b, 55))
    ron_b = max(con_b + 1, min(ron_b, 70))
    d.update(
        regime_risk_on_breadth_pct=ron_b,
        regime_constructive_breadth_pct=con_b,
        regime_cautious_breadth_pct=cau_b,
    )

    # Vol cascade: vol_high > vol_elevated
    vol_elevated = _clamp(d["vol_elevated_ratio"], 1.2, 1.8)
    vol_high = _clamp(d["vol_high_ratio"], 1.5, 2.5)
    if vol_high <= vol_elevated:
        vol_high = _clamp(vol_elevated + 0.05, 1.5, 2.5)
    d["vol_elevated_ratio"] = vol_elevated
    d["vol_high_ratio"] = vol_high

    # Momentum: accel > decel
    accel = _clamp(d["momentum_accel_ema_ratio"], 1.005, 1.03)
    decel = _clamp(d["momentum_decel_ema_ratio"], 0.97, 0.995)
    if accel <= decel:
        accel = _clamp(decel + 0.005, 1.005, 1.03)
    d["momentum_accel_ema_ratio"] = accel
    d["momentum_decel_ema_ratio"] = decel

    # RS exit thresholds: exit < entry cutoff
    leader_exit = _clamp(d["rs_leader_exit_pct"], 50.0, min(68.0, float(leader) - 2.0))
    strong_exit = _clamp(d["rs_strong_exit_pct"], 32.0, min(48.0, float(strong) - 2.0))
    if leader_exit >= float(leader):
        leader_exit = float(leader) - 2.0
    if strong_exit >= float(strong):
        strong_exit = float(strong) - 2.0
    d["rs_leader_exit_pct"] = leader_exit
    d["rs_strong_exit_pct"] = strong_exit

    d["ppc_conviction_boost"] = _clamp(d.get("ppc_conviction_boost", 0.15), 0.0, 0.5)
    d["stage3_blocks_entry"] = True
    return d


def _enforce_playbook_invariants(d: dict[str, Any]) -> dict[str, Any]:
    """Enforce RegimePlaybook drawdown cascade in-place."""
    halt = _clamp(d["dd_halt_entry_pct"], 8.0, 15.0)
    tighten = _clamp(d["dd_tighten_exit_pct"], 14.0, 22.0)
    liquidate = _clamp(d["dd_liquidate_pct"], 19.0, 30.0)
    if tighten <= halt:
        tighten = halt + 0.5
    if liquidate <= tighten:
        liquidate = tighten + 0.5
    d["dd_halt_entry_pct"] = halt
    d["dd_tighten_exit_pct"] = _clamp(tighten, 14.0, 22.0)
    d["dd_liquidate_pct"] = _clamp(liquidate, 19.0, 30.0)
    return d


def _crossover_playbook(a: RegimePlaybook, b: RegimePlaybook) -> RegimePlaybook:
    d: dict[str, Any] = {}
    for key, (lo, hi) in _REGIME_FLOAT_BOUNDS.items():
        d[key] = _clamp(_blend(getattr(a, key), getattr(b, key)), lo, hi)
    for key, (lo, hi) in _REGIME_FLOAT_OPTIONAL.items():
        va, vb = getattr(a, key), getattr(b, key)
        if va is None and vb is None:
            d[key] = None
        elif va is None:
            d[key] = vb
        elif vb is None:
            d[key] = va
        else:
            d[key] = _clamp(_blend(va, vb), lo, hi)
    d["exit_rs_drop_tiers"] = random.choice([a.exit_rs_drop_tiers, b.exit_rs_drop_tiers])  # noqa: S311
    d["exit_momentum_collapse"] = random.choice(  # noqa: S311
        [a.exit_momentum_collapse, b.exit_momentum_collapse]
    )
    d["time_stop_days"] = random.choice([a.time_stop_days, b.time_stop_days])  # noqa: S311
    d["min_hold_days"] = round(
        _clamp(_blend(float(a.min_hold_days), float(b.min_hold_days)), 3, 15)
    )
    sector_blend = _blend(
        float(a.max_sector_concentration_pct), float(b.max_sector_concentration_pct)
    )
    d["max_sector_concentration_pct"] = round(_clamp(sector_blend, 15, 35))
    _enforce_playbook_invariants(d)
    return RegimePlaybook(**d)


def _crossover_l1(a: Layer1Perception, b: Layer1Perception) -> Layer1Perception:
    d: dict[str, Any] = {}
    for key, (lo, hi) in _L1_FLOAT_BOUNDS.items():
        d[key] = _clamp(_blend(getattr(a, key), getattr(b, key)), lo, hi)
    for key, lo, hi in _L1_INT_RANGES:
        d[key] = round(_clamp(_blend(float(getattr(a, key)), float(getattr(b, key))), lo, hi))
    d["rs_timeframe_weights"] = _normalize_weights(
        {
            k: (a.rs_timeframe_weights.get(k, 0.0) + b.rs_timeframe_weights.get(k, 0.0)) / 2.0
            for k in ("1w", "1m", "3m")
        }
    )
    d["rs_leader_exit_pct"] = _blend(a.rs_leader_exit_pct, b.rs_leader_exit_pct)
    d["rs_strong_exit_pct"] = _blend(a.rs_strong_exit_pct, b.rs_strong_exit_pct)
    d["require_stage2_for_entry"] = bool(
        random.choice([a.require_stage2_for_entry, b.require_stage2_for_entry])  # noqa: S311
    )
    d["npc_overrides_min_hold"] = bool(
        random.choice([a.npc_overrides_min_hold, b.npc_overrides_min_hold])  # noqa: S311
    )
    d["stage3_blocks_entry"] = True
    _enforce_l1_invariants(d)
    return Layer1Perception(**d)


def _mutate_playbook_dict(d: dict[str, Any], sigma: float) -> dict[str, Any]:
    for key, (lo, hi) in _REGIME_FLOAT_BOUNDS.items():
        d[key] = _clamp(d[key] + random.gauss(0.0, (hi - lo) * sigma), lo, hi)
    for key, (lo, hi) in _REGIME_FLOAT_OPTIONAL.items():
        if d[key] is not None:
            d[key] = _clamp(d[key] + random.gauss(0.0, (hi - lo) * sigma), lo, hi)
    d["min_hold_days"] = round(_clamp(d["min_hold_days"] + random.gauss(0.0, 2.0 * sigma), 3, 15))
    d["max_sector_concentration_pct"] = round(
        _clamp(d["max_sector_concentration_pct"] + random.gauss(0.0, 5.0 * sigma), 15, 35)
    )
    _enforce_playbook_invariants(d)
    return d


def _mutate_l1_dict(d: dict[str, Any], sigma: float) -> dict[str, Any]:
    for key, (lo, hi) in _L1_FLOAT_BOUNDS.items():
        d[key] = _clamp(d[key] + random.gauss(0.0, (hi - lo) * sigma), lo, hi)
    for key, lo, hi in _L1_INT_RANGES:
        d[key] = round(_clamp(d[key] + random.gauss(0.0, (hi - lo) * sigma), lo, hi))
    if random.random() < 0.20:  # noqa: S311
        d["require_stage2_for_entry"] = not bool(d["require_stage2_for_entry"])
    if random.random() < 0.20:  # noqa: S311
        d["npc_overrides_min_hold"] = not bool(d["npc_overrides_min_hold"])
    w = d["rs_timeframe_weights"]
    d["rs_timeframe_weights"] = _normalize_weights(
        {k: max(0.01, v + random.gauss(0.0, 0.05 * sigma + 0.01)) for k, v in w.items()}
    )
    _enforce_l1_invariants(d)
    return d


class Evolver:
    """DEAP-inspired evolutionary operators for Genome objects.

    crossover(): arithmetic blend of two parents, two children.
    mutate(): Gaussian perturbation of all tunable params.
    select_survivors(): rank by combined sortino + calmar, return top-N.
    """

    def crossover(self, parent_a: Genome, parent_b: Genome) -> tuple[Genome, Genome]:
        now = datetime.now(UTC)
        pid_a, pid_b = parent_a.genome_id, parent_b.genome_id
        next_gen = max(parent_a.generation, parent_b.generation) + 1

        child_a = Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[pid_a, pid_b],
            born_at=now,
            generation=next_gen,
            layer1=_crossover_l1(parent_a.layer1, parent_b.layer1),
            risk_on=_crossover_playbook(parent_a.risk_on, parent_b.risk_on),
            constructive=_crossover_playbook(parent_a.constructive, parent_b.constructive),
            cautious=_crossover_playbook(parent_a.cautious, parent_b.cautious),
        )
        # Second child: swap parents so blend is symmetric but independently noisy
        child_b = Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[pid_b, pid_a],
            born_at=now,
            generation=next_gen,
            layer1=_crossover_l1(parent_b.layer1, parent_a.layer1),
            risk_on=_crossover_playbook(parent_b.risk_on, parent_a.risk_on),
            constructive=_crossover_playbook(parent_b.constructive, parent_a.constructive),
            cautious=_crossover_playbook(parent_b.cautious, parent_a.cautious),
        )
        log.debug(
            "crossover_complete",
            child_a=child_a.genome_id,
            child_b=child_b.genome_id,
            generation=next_gen,
        )
        return child_a, child_b

    def mutate(self, genome: Genome, sigma: float = 0.10) -> Genome:
        d = genome.to_dict()
        d["layer1"] = _mutate_l1_dict(d["layer1"], sigma)
        for regime_key in ("risk_on", "constructive", "cautious"):
            d[regime_key] = _mutate_playbook_dict(d[regime_key], sigma)
        d["genome_id"] = str(uuid.uuid4())
        d["parent_ids"] = [genome.genome_id]
        d["born_at"] = datetime.now(UTC).isoformat()
        d["generation"] = genome.generation + 1
        mutated = Genome.from_dict(d)
        log.debug("mutate_complete", new_id=mutated.genome_id, sigma=sigma)
        return mutated

    def select_survivors(
        self,
        genomes_with_scores: list[tuple[Genome, float, float, float]],
        target_pool: int,
    ) -> list[Genome]:
        """Rank by alpha + IR (the v2 goal-post metrics, not Sortino+Calmar).

        Tuple shape: (genome, alpha_oos, information_ratio, sortino_oos).
        Survivors are the top-N by (alpha + IR) — alpha is the maximization
        target, IR penalizes alpha that came from a few lucky windows. Genome
        with high alpha AND high IR has consistent excess return, which is
        what we want to breed forward.
        """
        if not genomes_with_scores:
            return []
        ranked = sorted(genomes_with_scores, key=lambda t: t[1] + t[2], reverse=True)
        survivors = [g for g, *_ in ranked[:target_pool]]
        log.debug("select_survivors", kept=len(survivors), from_pool=len(genomes_with_scores))
        return survivors
