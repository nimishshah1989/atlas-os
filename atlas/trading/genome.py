"""Genome schema and factory for evolutionary strategy optimization.

NOTE: This module uses standard random (not crypto-secure) for non-cryptographic
genome seeding and Optuna trial sampling. S311 suppressions are intentional.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Search space definitions (Optuna ranges)
# ---------------------------------------------------------------------------

# NOTE: atlas_stock_metrics_daily only has rs_pctile_1w, rs_pctile_1m, rs_pctile_3m.
# 6M and 12M timeframes are NOT in the DB. Genome uses 3-timeframe blend only.
LAYER1_SEARCH_SPACE: dict[str, tuple] = {
    "rs_leader_cutoff_pct": ("int", 60, 80),
    "rs_strong_cutoff_pct": ("int", 45, 65),
    "rs_average_cutoff_pct": ("int", 25, 45),
    "rs_weak_cutoff_pct": ("int", 10, 25),
    "rs_w1w": ("float", 0.10, 0.70),
    "rs_w1m": ("float", 0.10, 0.60),
    "rs_w3m": ("float", 0.05, 0.50),
    "regime_risk_on_breadth_pct": ("int", 50, 70),
    "regime_constructive_breadth_pct": ("int", 35, 55),
    "regime_cautious_breadth_pct": ("int", 20, 40),
    "regime_risk_on_vix_ceiling": ("float", 14.0, 22.0),
    "momentum_accel_ema_ratio": ("float", 1.010, 1.040),
    "momentum_decel_ema_ratio": ("float", 0.975, 0.995),
    "vol_elevated_ratio": ("float", 1.2, 1.8),
    "vol_high_ratio": ("float", 1.5, 2.5),
    "state_velocity_lookback_days": ("int", 5, 20),
    "synergy_weight": ("float", 0.0, 0.3),
    "penalty_weight": ("float", 0.0, 0.3),
    # Conviction formula weights — unnormalized importance weights
    # decision.py uses relative scale, not sum=1
    "conviction_rs_weight": ("float", 0.40, 0.80),
    "conviction_mom_weight": ("float", 0.10, 0.40),
    "conviction_state_weight": ("float", 0.05, 0.25),
    "conviction_velocity_weight": ("float", 0.01, 0.15),
    # Genome-controlled allocation limits (enforced as min(genome, config_ceiling))
    "genome_max_position_pct": ("float", 0.03, 0.08),
    "genome_max_heat_pct": ("float", 0.12, 0.30),
    # Core 4 risk management (active risk per trade, not just statistical confidence).
    # Goal-post alignment: maximize alpha WHILE doing active risk management.
    "stop_loss_pct": ("float", 0.05, 0.20),  # 5-20% drop from entry triggers exit
    "risk_per_trade_pct": ("float", 0.005, 0.020),  # 0.5-2% of capital risked per trade
    "min_concurrent_positions": ("int", 5, 15),  # diversification floor (target)
    "max_concurrent_positions": ("int", 15, 30),  # hard cap, must > min (cascade)
}

# Regime-level search space. Consumed by DEAP evolver (Task 10) for mutation bounds.
# Not directly used by Optuna trial factory — each regime generates its own playbook.
REGIME_SEARCH_SPACE: dict[str, tuple] = {
    "min_conviction_to_enter": ("float", 0.35, 0.80),
    "base_position_pct": ("float", 2.0, 6.0),
    "exit_rs_drop_tiers": ("int", 1, 3),
    "profit_target_pct": ("float", 10.0, 30.0),
    "time_stop_days": ("int", 10, 45),
    "trailing_stop_pct": ("float", 5.0, 20.0),
    "min_hold_days": ("int", 3, 15),
    "max_sector_concentration_pct": ("int", 15, 35),
    "dd_halt_entry_pct": ("float", 8.0, 15.0),
    "dd_tighten_exit_pct": ("float", 14.0, 22.0),
    "dd_liquidate_pct": ("float", 19.0, 30.0),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Layer1Perception:
    rs_leader_cutoff_pct: int
    rs_strong_cutoff_pct: int
    rs_average_cutoff_pct: int
    rs_weak_cutoff_pct: int
    rs_timeframe_weights: dict[str, float]  # keys: 1w, 1m, 3m; sum=1.0
    regime_risk_on_breadth_pct: int
    regime_constructive_breadth_pct: int
    regime_cautious_breadth_pct: int
    regime_risk_on_vix_ceiling: float
    momentum_accel_ema_ratio: float
    momentum_decel_ema_ratio: float
    vol_elevated_ratio: float
    vol_high_ratio: float
    state_velocity_lookback_days: int
    synergy_weight: float
    penalty_weight: float
    # Genome-controlled conviction formula weights
    conviction_rs_weight: float
    conviction_mom_weight: float
    conviction_state_weight: float
    conviction_velocity_weight: float
    # Genome-controlled allocation limits (ceiling enforced via min(genome, config))
    genome_max_position_pct: float
    genome_max_heat_pct: float

    # Core 4 active risk management — stop-loss, risk-parity sizing, diversification.
    # Defaults preserve backward compat for existing test fixtures; new genomes
    # always sample these via Optuna or random factory.
    stop_loss_pct: float = 0.10
    risk_per_trade_pct: float = 0.010
    min_concurrent_positions: int = 8
    max_concurrent_positions: int = 20

    # Weinstein/CTS stage gates
    require_stage2_for_entry: bool = True
    stage3_blocks_entry: bool = True
    ppc_conviction_boost: float = 0.15
    npc_overrides_min_hold: bool = True
    contraction_entry_bonus: float = 0.10

    # RS hysteresis: exit thresholds (lower than entry cutoffs — dead-band prevents oscillation)
    rs_leader_exit_pct: float = 62.0
    rs_strong_exit_pct: float = 40.0

    def __post_init__(self) -> None:
        assert (
            self.rs_leader_cutoff_pct
            > self.rs_strong_cutoff_pct
            > self.rs_average_cutoff_pct
            > self.rs_weak_cutoff_pct
        ), "RS cutoffs must be strictly decreasing: leader > strong > average > weak"
        assert (
            self.vol_high_ratio > self.vol_elevated_ratio
        ), "vol_high_ratio must exceed vol_elevated_ratio"
        assert (
            self.momentum_accel_ema_ratio > self.momentum_decel_ema_ratio
        ), "momentum_accel_ema_ratio must exceed momentum_decel_ema_ratio"
        assert (
            self.regime_risk_on_breadth_pct
            > self.regime_constructive_breadth_pct
            > self.regime_cautious_breadth_pct
        ), "Breadth thresholds must be strictly decreasing: risk_on > constructive > cautious"
        assert (
            self.rs_leader_exit_pct < self.rs_leader_cutoff_pct
        ), "Leader exit threshold must be below leader entry cutoff (hysteresis dead-band)"
        assert (
            self.rs_strong_exit_pct < self.rs_strong_cutoff_pct
        ), "Strong exit threshold must be below strong entry cutoff (hysteresis dead-band)"
        assert 0.0 <= self.ppc_conviction_boost <= 0.5, "ppc_conviction_boost must be in [0, 0.5]"
        # Core 4 invariants — keep stops sane and diversification ordering correct.
        assert 0.03 <= self.stop_loss_pct <= 0.30, "stop_loss_pct must be in [3%, 30%]"
        assert 0.001 <= self.risk_per_trade_pct <= 0.05, "risk_per_trade_pct must be in [0.1%, 5%]"
        assert (
            self.max_concurrent_positions > self.min_concurrent_positions
        ), "max_concurrent_positions must exceed min_concurrent_positions (cascade)"
        assert self.min_concurrent_positions >= 2, "min_concurrent_positions must be >= 2"


@dataclass
class RegimePlaybook:
    min_conviction_to_enter: float
    base_position_pct: float
    exit_rs_drop_tiers: int
    exit_momentum_collapse: bool
    profit_target_pct: float | None
    time_stop_days: int | None
    trailing_stop_from_peak_pct: float | None
    min_hold_days: int
    max_sector_concentration_pct: int
    dd_halt_entry_pct: float
    dd_tighten_exit_pct: float
    dd_liquidate_pct: float


@dataclass
class Genome:
    genome_id: str
    parent_ids: list[str]
    born_at: datetime
    generation: int
    layer1: Layer1Perception
    risk_on: RegimePlaybook
    constructive: RegimePlaybook
    cautious: RegimePlaybook

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome_id": self.genome_id,
            "parent_ids": self.parent_ids,
            "born_at": self.born_at.isoformat(),
            "generation": self.generation,
            "layer1": asdict(self.layer1),
            "risk_on": asdict(self.risk_on),
            "constructive": asdict(self.constructive),
            "cautious": asdict(self.cautious),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Genome:
        born_at = datetime.fromisoformat(d["born_at"])
        if born_at.tzinfo is None:
            born_at = born_at.replace(tzinfo=UTC)
        return cls(
            genome_id=d["genome_id"],
            parent_ids=d.get("parent_ids", []),
            born_at=born_at,
            generation=d.get("generation", 0),
            layer1=Layer1Perception(**d["layer1"]),
            risk_on=RegimePlaybook(**d["risk_on"]),
            constructive=RegimePlaybook(**d["constructive"]),
            cautious=RegimePlaybook(**d["cautious"]),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _random_weights() -> dict[str, float]:
    # 3 timeframes only — atlas_stock_metrics_daily has rs_pctile_1w/1m/3m
    raw = [random.random() for _ in range(3)]
    total = sum(raw)
    vals = [v / total for v in raw]
    return {"1w": vals[0], "1m": vals[1], "3m": vals[2]}


def _random_playbook(
    has_profit_target: bool, has_time_stop: bool, has_trailing: bool
) -> RegimePlaybook:
    # Cascade drawdown thresholds to enforce halt < tighten < liquidate
    dd_halt = random.uniform(8.0, 15.0)
    dd_tighten = random.uniform(max(14.0, dd_halt + 0.5), 22.0)
    dd_liquidate = random.uniform(max(19.0, dd_tighten + 0.5), 30.0)

    return RegimePlaybook(
        min_conviction_to_enter=random.uniform(0.35, 0.80),
        base_position_pct=random.uniform(2.0, 6.0),
        exit_rs_drop_tiers=random.randint(1, 3),
        exit_momentum_collapse=random.random() > 0.3,
        profit_target_pct=(random.uniform(10.0, 30.0) if has_profit_target else None),
        time_stop_days=random.randint(10, 45) if has_time_stop else None,
        trailing_stop_from_peak_pct=(random.uniform(5.0, 20.0) if has_trailing else None),
        min_hold_days=random.randint(3, 15),
        max_sector_concentration_pct=random.randint(15, 35),
        dd_halt_entry_pct=dd_halt,
        dd_tighten_exit_pct=dd_tighten,
        dd_liquidate_pct=dd_liquidate,
    )


class GenomeFactory:
    @staticmethod
    def random() -> Genome:
        leader = random.randint(60, 80)
        strong = random.randint(45, min(65, leader - 1))
        average = random.randint(25, min(45, strong - 1))
        weak = random.randint(10, min(25, average - 1))

        # Cascade breadth thresholds: risk_on > constructive > cautious
        risk_on_breadth = random.randint(50, 70)
        constructive_breadth = random.randint(35, min(55, risk_on_breadth - 1))
        cautious_breadth = random.randint(20, min(40, constructive_breadth - 1))

        # Cascade vol ratios: elevated < high
        vol_elevated = random.uniform(1.2, 1.8)
        vol_high = random.uniform(max(1.5, vol_elevated + 0.05), 2.5)

        # RS exit thresholds must be strictly below entry cutoffs (hysteresis)
        leader_exit = random.randint(50, min(68, leader - 2))
        strong_exit = random.randint(32, min(48, strong - 2))

        layer1 = Layer1Perception(
            rs_leader_cutoff_pct=leader,
            rs_strong_cutoff_pct=strong,
            rs_average_cutoff_pct=average,
            rs_weak_cutoff_pct=weak,
            rs_timeframe_weights=_random_weights(),
            regime_risk_on_breadth_pct=risk_on_breadth,
            regime_constructive_breadth_pct=constructive_breadth,
            regime_cautious_breadth_pct=cautious_breadth,
            regime_risk_on_vix_ceiling=random.uniform(14.0, 22.0),
            momentum_accel_ema_ratio=random.uniform(1.010, 1.040),
            momentum_decel_ema_ratio=random.uniform(0.975, 0.995),
            vol_elevated_ratio=vol_elevated,
            vol_high_ratio=vol_high,
            state_velocity_lookback_days=random.randint(5, 20),
            synergy_weight=random.uniform(0.0, 0.3),
            penalty_weight=random.uniform(0.0, 0.3),
            conviction_rs_weight=random.uniform(0.40, 0.80),
            conviction_mom_weight=random.uniform(0.10, 0.40),
            conviction_state_weight=random.uniform(0.05, 0.25),
            conviction_velocity_weight=random.uniform(0.01, 0.15),
            genome_max_position_pct=random.uniform(0.03, 0.08),
            genome_max_heat_pct=random.uniform(0.12, 0.30),
            # Core 4 — cascade min < max via direct sample then bound
            stop_loss_pct=random.uniform(0.05, 0.20),
            risk_per_trade_pct=random.uniform(0.005, 0.020),
            min_concurrent_positions=random.randint(5, 15),
            max_concurrent_positions=random.randint(16, 30),
            require_stage2_for_entry=random.choice([True, False]),
            stage3_blocks_entry=True,  # always True — never enter declining stocks
            ppc_conviction_boost=random.uniform(0.05, 0.30),
            npc_overrides_min_hold=random.choice([True, False]),
            contraction_entry_bonus=random.uniform(0.0, 0.20),
            rs_leader_exit_pct=float(leader_exit),
            rs_strong_exit_pct=float(strong_exit),
        )
        return Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[],
            born_at=datetime.now(UTC),
            generation=0,
            layer1=layer1,
            risk_on=_random_playbook(False, False, False),
            constructive=_random_playbook(False, True, True),
            cautious=_random_playbook(True, True, True),
        )

    @staticmethod
    def from_optuna_trial(trial: Any) -> Genome:
        """Build a Genome from an Optuna trial using suggest_* calls."""
        leader = trial.suggest_int("rs_leader_cutoff_pct", 60, 80)
        strong = trial.suggest_int("rs_strong_cutoff_pct", 45, min(65, leader - 1))
        average = trial.suggest_int("rs_average_cutoff_pct", 25, min(45, strong - 1))
        weak = trial.suggest_int("rs_weak_cutoff_pct", 10, min(25, average - 1))

        w1 = trial.suggest_float("rs_w1w", 0.10, 0.70)
        w2 = trial.suggest_float("rs_w1m", 0.10, 0.60)
        w3 = trial.suggest_float("rs_w3m", 0.05, 0.50)
        total = w1 + w2 + w3
        weights = {"1w": w1 / total, "1m": w2 / total, "3m": w3 / total}

        # Cascade breadth thresholds: risk_on > constructive > cautious
        risk_on_breadth = trial.suggest_int("regime_risk_on_breadth_pct", 50, 70)
        constructive_breadth = trial.suggest_int(
            "regime_constructive_breadth_pct", 35, min(55, risk_on_breadth - 1)
        )
        cautious_breadth = trial.suggest_int(
            "regime_cautious_breadth_pct", 20, min(40, constructive_breadth - 1)
        )

        # Cascade vol ratios: elevated < high
        vol_elevated = trial.suggest_float("vol_elevated_ratio", 1.2, 1.8)
        vol_high = trial.suggest_float("vol_high_ratio", max(1.5, vol_elevated + 0.05), 2.5)

        require_stage2_for_entry = trial.suggest_categorical(
            "require_stage2_for_entry", [True, False]
        )
        ppc_conviction_boost = trial.suggest_float("ppc_conviction_boost", 0.05, 0.30)
        npc_overrides_min_hold = trial.suggest_categorical("npc_overrides_min_hold", [True, False])
        contraction_entry_bonus = trial.suggest_float("contraction_entry_bonus", 0.0, 0.20)
        rs_leader_exit_pct = trial.suggest_int("rs_leader_exit_pct", 50, min(68, leader - 2))
        rs_strong_exit_pct = trial.suggest_int("rs_strong_exit_pct", 32, min(48, strong - 2))

        layer1 = Layer1Perception(
            rs_leader_cutoff_pct=leader,
            rs_strong_cutoff_pct=strong,
            rs_average_cutoff_pct=average,
            rs_weak_cutoff_pct=weak,
            rs_timeframe_weights=weights,
            regime_risk_on_breadth_pct=risk_on_breadth,
            regime_constructive_breadth_pct=constructive_breadth,
            regime_cautious_breadth_pct=cautious_breadth,
            regime_risk_on_vix_ceiling=trial.suggest_float(
                "regime_risk_on_vix_ceiling", 14.0, 22.0
            ),
            momentum_accel_ema_ratio=trial.suggest_float("momentum_accel_ema_ratio", 1.010, 1.040),
            momentum_decel_ema_ratio=trial.suggest_float("momentum_decel_ema_ratio", 0.975, 0.995),
            vol_elevated_ratio=vol_elevated,
            vol_high_ratio=vol_high,
            state_velocity_lookback_days=trial.suggest_int("state_velocity_lookback_days", 5, 20),
            synergy_weight=trial.suggest_float("synergy_weight", 0.0, 0.3),
            penalty_weight=trial.suggest_float("penalty_weight", 0.0, 0.3),
            conviction_rs_weight=trial.suggest_float("conviction_rs_weight", 0.40, 0.80),
            conviction_mom_weight=trial.suggest_float("conviction_mom_weight", 0.10, 0.40),
            conviction_state_weight=trial.suggest_float("conviction_state_weight", 0.05, 0.25),
            conviction_velocity_weight=trial.suggest_float(
                "conviction_velocity_weight", 0.01, 0.15
            ),
            genome_max_position_pct=trial.suggest_float("genome_max_position_pct", 0.03, 0.08),
            genome_max_heat_pct=trial.suggest_float("genome_max_heat_pct", 0.12, 0.30),
            # Core 4 risk genes — Optuna explores the active-risk-mgmt search space.
            # max > min cascade enforced by sampling min first, then max above it.
            stop_loss_pct=trial.suggest_float("stop_loss_pct", 0.05, 0.20),
            risk_per_trade_pct=trial.suggest_float("risk_per_trade_pct", 0.005, 0.020),
            min_concurrent_positions=trial.suggest_int("min_concurrent_positions", 5, 15),
            max_concurrent_positions=trial.suggest_int(
                "max_concurrent_positions",
                # Ensure cascade: max strictly > min. Read the min already sampled this trial.
                # Optuna re-uses the same trial state for both suggests, so this works.
                min(16, trial.params["min_concurrent_positions"] + 1),
                30,
            ),
            require_stage2_for_entry=require_stage2_for_entry,
            stage3_blocks_entry=True,  # always True — never enter declining stocks
            ppc_conviction_boost=ppc_conviction_boost,
            npc_overrides_min_hold=npc_overrides_min_hold,
            contraction_entry_bonus=contraction_entry_bonus,
            rs_leader_exit_pct=float(rs_leader_exit_pct),
            rs_strong_exit_pct=float(rs_strong_exit_pct),
        )

        def _trial_playbook(
            prefix: str, has_profit: bool, has_time: bool, has_trail: bool
        ) -> RegimePlaybook:
            # Cascade drawdown thresholds to enforce halt < tighten < liquidate
            dd_halt = trial.suggest_float(f"{prefix}_dd_halt_pct", 8.0, 15.0)
            dd_tighten = trial.suggest_float(
                f"{prefix}_dd_tighten_pct", max(14.0, dd_halt + 0.5), 22.0
            )
            dd_liquidate = trial.suggest_float(
                f"{prefix}_dd_liquidate_pct", max(19.0, dd_tighten + 0.5), 30.0
            )

            return RegimePlaybook(
                min_conviction_to_enter=trial.suggest_float(f"{prefix}_min_conviction", 0.35, 0.80),
                base_position_pct=trial.suggest_float(f"{prefix}_base_position_pct", 2.0, 6.0),
                exit_rs_drop_tiers=trial.suggest_int(f"{prefix}_exit_rs_drop_tiers", 1, 3),
                exit_momentum_collapse=trial.suggest_categorical(
                    f"{prefix}_exit_momentum_collapse", [True, False]
                ),
                profit_target_pct=(
                    trial.suggest_float(f"{prefix}_profit_target_pct", 10.0, 30.0)
                    if has_profit
                    else None
                ),
                time_stop_days=(
                    trial.suggest_int(f"{prefix}_time_stop_days", 10, 45) if has_time else None
                ),
                trailing_stop_from_peak_pct=(
                    trial.suggest_float(f"{prefix}_trailing_stop_pct", 5.0, 20.0)
                    if has_trail
                    else None
                ),
                min_hold_days=trial.suggest_int(f"{prefix}_min_hold_days", 3, 15),
                max_sector_concentration_pct=trial.suggest_int(f"{prefix}_max_sector_pct", 15, 35),
                dd_halt_entry_pct=dd_halt,
                dd_tighten_exit_pct=dd_tighten,
                dd_liquidate_pct=dd_liquidate,
            )

        return Genome(
            genome_id=str(uuid.uuid4()),
            parent_ids=[],
            born_at=datetime.now(UTC),
            generation=0,
            layer1=layer1,
            risk_on=_trial_playbook("ro", False, False, False),
            constructive=_trial_playbook("co", False, True, True),
            cautious=_trial_playbook("ca", True, True, True),
        )
