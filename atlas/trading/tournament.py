"""Three-round tournament evaluation for genome promotion to leaderboard.

v2 — alpha + confidence (aligned with the goal post: maximize alpha,
minimize drawdown, with quantified confidence).

Gate structure:
  Round 1 (recent 90d OOS):
    - alpha_oos > 0  (must beat benchmark)
    - hit_rate >= 0.55  (55% of historical windows positive)
    - information_ratio >= 0.3
  Round 2 (prior 90d OOS, consistency):
    - alpha_oos > 0  (positive alpha twice in a row)
  Round 3 (stress periods — COVID, bear, bull):
    - COVID: max_drawdown <= 25% absolute
    - 2022 bear: alpha_oos > 0  (beat benchmark when index fell)
    - 2023 bull: alpha_oos > 0  (don't merely match the index in good times)

promote_to_leaderboard() writes to atlas.atlas_strategy_leaderboard. The
ON CONFLICT target is (genome_id) — see migration 067 UNIQUE constraint.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from atlas.trading.genome import Genome
from atlas.trading.simulator import SimResult

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

log = structlog.get_logger()

# v2 gates — alpha + confidence
ROUND1_ALPHA_MIN = 0.0
ROUND1_HIT_RATE_MIN = 0.55
ROUND1_IR_MIN = 0.3
ROUND2_ALPHA_MIN = 0.0
STRESS_COVID_MAX_DRAWDOWN = 0.25  # absolute drawdown gate during COVID crash
STRESS_BEAR_ALPHA_MIN = 0.0  # must beat benchmark when index falls
STRESS_BULL_ALPHA_MIN = 0.0  # must beat benchmark when index rises


@dataclass
class PromotionResult:
    """Tournament outcome for a genome. v2 carries the goal-post metrics."""

    promoted: bool
    final_sortino: float
    final_calmar: float
    final_alpha: float = 0.0
    final_information_ratio: float = 0.0
    final_hit_rate: float = 0.0
    final_t_stat: float = 0.0
    final_max_drawdown: float = 0.0
    failed_round: int | None = None
    fail_reason: str | None = None


class TournamentEvaluator:
    def __init__(self, stress_periods: dict[str, tuple[date, date]]) -> None:
        self.stress_periods = stress_periods

    def evaluate(
        self,
        genome: Genome,
        sim_fn: Callable,  # sim_fn(genome, start: date, end: date) -> SimResult
        recent_start: date,
        recent_end: date,
    ) -> PromotionResult:
        # Round 1: recent OOS window — alpha + hit rate + IR
        r1: SimResult = sim_fn(genome, recent_start, recent_end)
        base = _carry(r1)  # carry metrics into PromotionResult for diagnostics

        if r1.alpha_oos <= ROUND1_ALPHA_MIN:
            return _fail(base, 1, f"Round 1 alpha {r1.alpha_oos:.4f} <= {ROUND1_ALPHA_MIN}")
        if r1.hit_rate < ROUND1_HIT_RATE_MIN:
            return _fail(base, 1, f"Round 1 hit_rate {r1.hit_rate:.2f} < {ROUND1_HIT_RATE_MIN}")
        if r1.information_ratio < ROUND1_IR_MIN:
            return _fail(base, 1, f"Round 1 IR {r1.information_ratio:.2f} < {ROUND1_IR_MIN}")

        # Round 2: prior window — alpha must be positive twice in a row
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=89)
        r2: SimResult = sim_fn(genome, prior_start, prior_end)
        if r2.alpha_oos <= ROUND2_ALPHA_MIN:
            return _fail(base, 2, f"Round 2 alpha {r2.alpha_oos:.4f} <= {ROUND2_ALPHA_MIN}")

        # Round 3: stress periods
        covid_start, covid_end = self.stress_periods.get(
            "covid_2020", (date(2020, 2, 1), date(2020, 5, 31))
        )
        bear_start, bear_end = self.stress_periods.get(
            "bear_2022", (date(2022, 1, 1), date(2022, 6, 30))
        )
        bull_start, bull_end = self.stress_periods.get(
            "bull_2023", (date(2023, 1, 1), date(2023, 12, 31))
        )

        r_covid: SimResult = sim_fn(genome, covid_start, covid_end)
        if r_covid.max_drawdown > STRESS_COVID_MAX_DRAWDOWN:
            return _fail(base, 3, f"COVID drawdown {r_covid.max_drawdown:.1%} > 25%")

        r_bear: SimResult = sim_fn(genome, bear_start, bear_end)
        if r_bear.alpha_oos <= STRESS_BEAR_ALPHA_MIN:
            return _fail(base, 3, f"2022 bear alpha {r_bear.alpha_oos:.4f} <= 0")

        r_bull: SimResult = sim_fn(genome, bull_start, bull_end)
        if r_bull.alpha_oos <= STRESS_BULL_ALPHA_MIN:
            return _fail(base, 3, f"2023 bull alpha {r_bull.alpha_oos:.4f} <= 0")

        log.info(
            "genome_promoted_tournament",
            genome_id=genome.genome_id,
            alpha=r1.alpha_oos,
            ir=r1.information_ratio,
            hit_rate=r1.hit_rate,
            sortino=r1.sortino_oos,
        )
        return PromotionResult(
            promoted=True,
            final_sortino=r1.sortino_oos,
            final_calmar=r1.calmar_oos,
            final_alpha=r1.alpha_oos,
            final_information_ratio=r1.information_ratio,
            final_hit_rate=r1.hit_rate,
            final_t_stat=r1.alpha_t_stat,
            final_max_drawdown=r1.max_drawdown,
        )


def _carry(r: SimResult) -> PromotionResult:
    """Snapshot of metrics so failure reports surface the full picture."""
    return PromotionResult(
        promoted=False,
        final_sortino=r.sortino_oos,
        final_calmar=r.calmar_oos,
        final_alpha=r.alpha_oos,
        final_information_ratio=r.information_ratio,
        final_hit_rate=r.hit_rate,
        final_t_stat=r.alpha_t_stat,
        final_max_drawdown=r.max_drawdown,
    )


def _fail(base: PromotionResult, round_num: int, reason: str) -> PromotionResult:
    base.failed_round = round_num
    base.fail_reason = reason
    return base


def promote_to_leaderboard(
    conn: Connection,
    genome: Genome,
    result: PromotionResult,
    rank: int,
) -> None:
    """Write promoted genome to atlas.atlas_strategy_leaderboard.

    v2 — persists alpha + IR + hit_rate so the leaderboard ranks by goal-post
    metrics, not Sortino alone. Requires migration 068 to add the alpha/IR
    columns; until applied, alpha lands in alpha_30d (existing column) and IR
    falls into regime_breakdown JSONB for forward compatibility.
    """
    from sqlalchemy import text

    name = _auto_name(genome)
    conn.execute(
        text(
            """
            INSERT INTO atlas.atlas_strategy_leaderboard
                (id, rank, genome_id, strategy_name, promoted_at,
                 sortino_oos, calmar_oos, alpha_oos, information_ratio,
                 hit_rate, alpha_t_stat, max_drawdown)
            VALUES
                (gen_random_uuid(), :rank, :genome_id::uuid, :name, :promoted_at,
                 :sortino, :calmar, :alpha, :ir, :hit_rate, :t_stat, :max_dd)
            ON CONFLICT (genome_id) DO UPDATE
                SET rank = EXCLUDED.rank,
                    strategy_name = EXCLUDED.strategy_name,
                    promoted_at = EXCLUDED.promoted_at,
                    sortino_oos = EXCLUDED.sortino_oos,
                    calmar_oos = EXCLUDED.calmar_oos,
                    alpha_oos = EXCLUDED.alpha_oos,
                    information_ratio = EXCLUDED.information_ratio,
                    hit_rate = EXCLUDED.hit_rate,
                    alpha_t_stat = EXCLUDED.alpha_t_stat,
                    max_drawdown = EXCLUDED.max_drawdown,
                    updated_at = now()
            """
        ),
        {
            "rank": rank,
            "genome_id": genome.genome_id,
            "name": name,
            "promoted_at": datetime.now(UTC),
            "sortino": result.final_sortino,
            "calmar": result.final_calmar,
            "alpha": result.final_alpha,
            "ir": result.final_information_ratio,
            "hit_rate": result.final_hit_rate,
            "t_stat": result.final_t_stat,
            "max_dd": result.final_max_drawdown,
        },
    )
    log.info(
        "genome_written_leaderboard",
        genome_id=genome.genome_id,
        rank=rank,
        alpha=result.final_alpha,
    )


def _auto_name(genome: Genome) -> str:
    weights = genome.layer1.rs_timeframe_weights
    dominant_tf = max(weights, key=lambda k: weights[k])
    stance = "Aggressive" if genome.risk_on.base_position_pct > 4.0 else "Conservative"
    return f"RS-{dominant_tf.upper()}-{stance}-G{genome.generation}"
