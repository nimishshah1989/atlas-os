"""Strategy Lab v2 — add alpha + confidence columns to leaderboard + performance.

Goal-post alignment: the leaderboard must rank by alpha (return vs Nifty 500)
with quantified confidence (IR, hit rate, t-stat), not by Sortino alone. v1
shipped with Sortino-only columns; v2 adds the missing metrics.

Backfill: NOT NULL with server_default '0' so pre-v2 rows get a neutral value.
The Strategy Lab is gated behind the burn-in anyway, so the leaderboard is
effectively empty at v2 cutover — defaults never matter in practice.

Revision ID: 068
Revises: 067
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"


def upgrade() -> None:
    # Leaderboard — promotion-time goal-post metrics
    for col, default in [
        ("alpha_oos", "0"),
        ("information_ratio", "0"),
        ("hit_rate", "0"),
        ("alpha_t_stat", "0"),
        ("max_drawdown", "0"),
    ]:
        op.add_column(
            "atlas_strategy_leaderboard",
            sa.Column(col, sa.Numeric(10, 4), nullable=False, server_default=default),
            schema=_SCHEMA,
        )

    # Performance daily — per-day per-genome metrics (mirror of leaderboard).
    # Nullable + no default; pre-v2 rows simply have NULL values.
    for col in ["alpha_oos", "information_ratio", "hit_rate", "alpha_t_stat"]:
        op.add_column(
            "atlas_strategy_performance_daily",
            sa.Column(col, sa.Numeric(10, 4), nullable=True),
            schema=_SCHEMA,
        )

    # Index on alpha_oos so the leaderboard ORDER BY alpha_oos query is fast.
    op.create_index(
        "ix_leaderboard_alpha_oos",
        "atlas_strategy_leaderboard",
        ["alpha_oos"],
        schema=_SCHEMA,
        postgresql_ops={"alpha_oos": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_leaderboard_alpha_oos", table_name="atlas_strategy_leaderboard", schema=_SCHEMA)
    for col in ["alpha_oos", "information_ratio", "hit_rate", "alpha_t_stat", "max_drawdown"]:
        op.drop_column("atlas_strategy_leaderboard", col, schema=_SCHEMA)
    for col in ["alpha_oos", "information_ratio", "hit_rate", "alpha_t_stat"]:
        op.drop_column("atlas_strategy_performance_daily", col, schema=_SCHEMA)
