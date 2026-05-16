"""Three-round tournament evaluation for genome promotion to leaderboard.

Round 1: last 90-day OOS window → Sortino >= 0.7
Round 2: prior 90-day window → Sortino >= 0.5 (consistency)
Round 3: named stress periods (COVID crash, 2022 bear, 2023 bull)

promote_to_leaderboard() writes to atlas_strategy_leaderboard using the
fixed UUID PK schema (migration 067). The ON CONFLICT target is (genome_id).
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

ROUND1_SORTINO_THRESHOLD = 0.7
ROUND2_SORTINO_THRESHOLD = 0.5
STRESS_COVID_MAX_DRAWDOWN = 0.25  # 25% max drawdown during COVID crash
STRESS_BEAR_MIN_SORTINO = 0.0  # must not lose money in 2022 bear
STRESS_BULL_MIN_SORTINO = 0.8  # must compound well in 2023 bull


@dataclass
class PromotionResult:
    promoted: bool
    final_sortino: float
    final_calmar: float
    failed_round: int | None
    fail_reason: str | None


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
        # Round 1: recent OOS window
        r1: SimResult = sim_fn(genome, recent_start, recent_end)
        if r1.sortino_oos < ROUND1_SORTINO_THRESHOLD:
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=1,
                fail_reason=f"Round 1 Sortino {r1.sortino_oos:.2f} < {ROUND1_SORTINO_THRESHOLD}",
            )

        # Round 2: prior 90-day window (consistency gate)
        prior_end = recent_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=89)
        r2: SimResult = sim_fn(genome, prior_start, prior_end)
        if r2.sortino_oos < ROUND2_SORTINO_THRESHOLD:
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=2,
                fail_reason=f"Round 2 Sortino {r2.sortino_oos:.2f} < {ROUND2_SORTINO_THRESHOLD}",
            )

        # Round 3: stress tests
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
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=3,
                fail_reason=f"COVID stress: drawdown {r_covid.max_drawdown:.1%} > 25%",
            )

        r_bear: SimResult = sim_fn(genome, bear_start, bear_end)
        if r_bear.sortino_oos < STRESS_BEAR_MIN_SORTINO:
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=3,
                fail_reason=f"Bear stress: Sortino {r_bear.sortino_oos:.2f} < 0",
            )

        r_bull: SimResult = sim_fn(genome, bull_start, bull_end)
        if r_bull.sortino_oos < STRESS_BULL_MIN_SORTINO:
            return PromotionResult(
                promoted=False,
                final_sortino=r1.sortino_oos,
                final_calmar=r1.calmar_oos,
                failed_round=3,
                fail_reason=f"Bull stress: Sortino {r_bull.sortino_oos:.2f} < 1.0",
            )

        log.info(
            "genome_promoted_tournament",
            genome_id=genome.genome_id,
            sortino=r1.sortino_oos,
            calmar=r1.calmar_oos,
        )
        return PromotionResult(
            promoted=True,
            final_sortino=r1.sortino_oos,
            final_calmar=r1.calmar_oos,
            failed_round=None,
            fail_reason=None,
        )


def promote_to_leaderboard(
    conn: Connection,
    genome: Genome,
    result: PromotionResult,
    rank: int,
) -> None:
    """Write promoted genome to atlas_strategy_leaderboard (UUID PK schema)."""
    from sqlalchemy import text

    name = _auto_name(genome)
    conn.execute(
        text(
            """
            INSERT INTO atlas.atlas_strategy_leaderboard
                (id, rank, genome_id, strategy_name, promoted_at, sortino_oos, calmar_oos)
            VALUES
                (gen_random_uuid(), :rank, :genome_id::uuid, :name, :promoted_at, :sortino, :calmar)
            ON CONFLICT (genome_id) DO UPDATE
                SET rank = EXCLUDED.rank,
                    strategy_name = EXCLUDED.strategy_name,
                    promoted_at = EXCLUDED.promoted_at,
                    sortino_oos = EXCLUDED.sortino_oos,
                    calmar_oos = EXCLUDED.calmar_oos,
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
        },
    )
    log.info("genome_written_leaderboard", genome_id=genome.genome_id, rank=rank)


def _auto_name(genome: Genome) -> str:
    weights = genome.layer1.rs_timeframe_weights
    dominant_tf = max(weights, key=lambda k: weights[k])
    stance = "Aggressive" if genome.risk_on.base_position_pct > 4.0 else "Conservative"
    return f"RS-{dominant_tf.upper()}-{stance}-G{genome.generation}"
