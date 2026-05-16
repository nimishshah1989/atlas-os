"""Integration test for promote_to_leaderboard upsert path.

Code review B1 flagged that `tournament.promote_to_leaderboard` issues
`ON CONFLICT (genome_id) DO UPDATE` but migration 067 originally only had a
non-unique index on `genome_id`. This test guards against regression by
exercising the upsert twice with the same genome_id and verifying the row
is updated rather than duplicated or rejected.

Run: pytest tests/integration/trading/ -v --tb=short
Requires: real DB connection with migration 067 applied (EC2 or VPN).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.trading.genome import GenomeFactory
from atlas.trading.tournament import PromotionResult, promote_to_leaderboard

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    return get_engine()


def _seed_genome_row(conn, genome_id: str) -> None:
    """Insert a minimal atlas_strategy_genomes row so the FK from leaderboard resolves."""
    conn.execute(
        text(
            """
            INSERT INTO atlas.atlas_strategy_genomes
                (id, generation, status, genome_json, born_at, created_at)
            VALUES
                (CAST(:id AS uuid), 0, 'promoted',
                 CAST('{}' AS jsonb), :now, :now)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": genome_id, "now": datetime.now(UTC)},
    )


def _make_result(sortino: float, calmar: float) -> PromotionResult:
    return PromotionResult(
        promoted=True,
        final_sortino=sortino,
        final_calmar=calmar,
        failed_round=None,
        fail_reason=None,
    )


def test_promote_to_leaderboard_upsert_is_idempotent(engine):
    """Second promotion of the same genome_id must update rank/scores, not duplicate."""
    genome = GenomeFactory.random()
    # Force a fresh id so the test never collides with prod data even if the
    # transaction rollback fixture were ever removed.
    genome.genome_id = str(uuid4())

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            _seed_genome_row(conn, genome.genome_id)

            # First promotion — should INSERT.
            promote_to_leaderboard(conn, genome, _make_result(0.85, 1.10), rank=3)
            count_after_first = conn.execute(
                text(
                    "SELECT COUNT(*) FROM atlas.atlas_strategy_leaderboard "
                    "WHERE genome_id = CAST(:id AS uuid)"
                ),
                {"id": genome.genome_id},
            ).scalar()
            assert count_after_first == 1

            # Second promotion with different rank + scores — should UPDATE, not duplicate.
            promote_to_leaderboard(conn, genome, _make_result(0.95, 1.40), rank=1)
            row = (
                conn.execute(
                    text(
                        "SELECT rank, sortino_oos, calmar_oos "
                        "FROM atlas.atlas_strategy_leaderboard "
                        "WHERE genome_id = CAST(:id AS uuid)"
                    ),
                    {"id": genome.genome_id},
                )
                .mappings()
                .one()
            )
            count_after_second = conn.execute(
                text(
                    "SELECT COUNT(*) FROM atlas.atlas_strategy_leaderboard "
                    "WHERE genome_id = CAST(:id AS uuid)"
                ),
                {"id": genome.genome_id},
            ).scalar()

            assert count_after_second == 1, "upsert duplicated row instead of updating"
            assert row["rank"] == 1
            assert float(row["sortino_oos"]) == pytest.approx(0.95)
            assert float(row["calmar_oos"]) == pytest.approx(1.40)
        finally:
            trans.rollback()


def test_leaderboard_unique_constraint_present(engine):
    """The UNIQUE constraint underpinning the upsert must exist on genome_id."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'atlas.atlas_strategy_leaderboard'::regclass
                  AND contype = 'u'
                  AND conname = 'uq_leaderboard_genome_id'
                """
            )
        ).first()
    assert row is not None, (
        "uq_leaderboard_genome_id is missing — promote_to_leaderboard upsert "
        "will fail. Re-apply migration 067 or chain a follow-up migration."
    )
